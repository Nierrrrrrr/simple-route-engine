# Transaction contract

MariaDB InnoDB, READ COMMITTED, explicit Spring JDBC + TransactionTemplate.
Global lock order: **scheduler_pool → execution → incident/admission_request → step**.
Step-only transactions never acquire the pool after taking execution/step locks.
No HTTP, Kubernetes, Ansible, sleeps or long polling inside a transaction.

| Operation | Atomic database work | Outside transaction |
|---|---|---|
| initial admission | pool FOR UPDATE; principal+scope+key unique decision; exact published definition/hash/version; eligibility/FIFO/WRR; insert QUEUED or acquire permit + generation; event | response with stored decision |
| NOW rejection | store immutable ADMISSION_REJECTED decision; no runnable execution/queue/action; no cursor advance | 409; another attempt needs a new key |
| scheduler tick | pool; select oldest eligible critical else persisted WRR candidate; incident revalidation; acquire and increment permit generation; cursor + event | dispatch later |
| recovery | pool/execution/incident lock; validate reason/action/output/direction/current incident; original priority; one pending decision; atomic permit if NOW accepted | no submission until commit |
| claim | conditional due row + lease_generation/state_version update with DB clock; attempt + intent + identity | adapter submit/observe |
| completion | compare lease_generation, permit_generation, state_version; check affected rows; persist output/decision + next due node + event | notify scheduling loop |
| safe boundary/release | pool then execution; confirm all external work/notifications settled; CAS permit_held and generation; state + release + event together | none |
| configure | pool; validate T/R/weights and live U/N; reject shrink violating U<=T or N<=T-R; version + cursor reset only if weights change + audit | none |

Unique request key is `(principal, endpoint/operation scope, Idempotency-Key)` with canonical body hash.
Same key/body returns the original accepted/queued/rejected decision; differing body returns 409.
Unique route version `(route_id, version)`, node ID per definition, attempt identity and event ordering are explicit keys.
Routes are soft-disabled; published snapshots are immutable and reference immutable playbook/artifact digest and credential refs.
Admission binds version immediately, including queued/recovery paths; unsupported engine semantics fail closed.

Pool operations serialize capacity decisions in MariaDB across independent JVMs; JVM locks do not establish admission safety.
Worker lease is renewable ownership, not capacity. Expiry starts reconcile and never releases permit.
DB clock governs production lease expiry; injectable test Clock controls domain retry times and six-hour tests.
Deadlock/lock timeout returns 503; caller retries the whole transaction using the same request identity. There is no hidden retry that could turn uncertain commit into a different decision.
Commit uncertainty/DB outage returns 503 + request identity, never a definite capacity reject. Stop new submit/admission
until DB is authoritative again; retain known external identities for later reconciliation.

## Actual M1 transactions

RouteRegistry uses TransactionTemplate with READ COMMITTED and a 10-second timeout. Registry mutations
lock the route row, check state_version/affected rows, update state and call AuditLog.append in the same
transaction. They never acquire pool/execution locks or perform external I/O. M2 admission must extend
this safely with pool-first ordering and a locked route eligibility check. getVersion remains usable after
route disable/delete. Published mutation and event UPDATE/DELETE are blocked by V1 SQL triggers.
Admission runtime is implemented in M2. M3 adds step/attempt runtime; operator recovery remains M5.

## Implemented M2 boundaries

AdmissionService.submit/tick/configure/capacity/stop all take scheduler_pool id=1 FOR UPDATE first.
Initial submit then locks the route via RouteRegistry.lockForNewExecution before checking enabled/deleted
and selecting its exact PUBLISHED version. Registry-only transactions never subsequently acquire pool.
Tick takes pool -> execution -> admission row. All use READ COMMITTED with a 10-second transaction
budget and three-second InnoDB lock wait; external HTTP is never inside these transactions.

V2 adds admission_requests.queue_sequence AUTO_INCREMENT UNIQUE. Pool-serialized creation gives a
monotonic FIFO tie-break independent of timestamp precision and random UUIDs. Only successful acquire
changes the cursor. CRITICAL leaves it unchanged. NOW is an ephemeral candidate behind existing class
heads; rejection stores only admission_requests + audit. QUEUE always stores a durable waiting execution;
AdmissionScheduler wakes every 250ms, at most 32 separate single-admission transactions per wake.
response_json is the immutable initial decision; current decision and execution state may advance.

configure rejects live U/N violations, resets cursor=0 only when weights change, increments configVersion,
and writes the complete config to append-only pool_config_history with actor/reason/request ID in the
same transaction as execution_events. Accepted ranges are T 1..100000, R 0..T, each weight 1..100.

stop is an internal seam with no HTTP release endpoint. It fences permit generation and state version,
checks step/attempt convergence, and atomically records safe state + permit release. Unknown/active attempts
prevent release. Duplicate same-generation completed release is idempotent; lease expiry cannot release.
M3 coordinates claims/results with this same lock order and convergence seam.

## Implemented M3 boundaries

EngineService.claim locks pool, execution and existing incident rows, initializes the finite tree, resolves selected leaf input
once, writes INTENT_COMMITTED with operation identity, increments lease_generation and commits.
execute rechecks permit/step lease/version and invokes submit or observe outside the transaction.
Expired RUNNING, WAITING_EXTERNAL or IN_DOUBT claims retain attempt/identity, advancing only lease.
complete checks permit_generation, step state_version/lease_generation and DB lease expiry, and checks
affected rows. It writes result, resolves existing IN_DOUBT incident, expands next pending nodes/joins,
appends audit and recomputes safe state in the same transaction. Known failure creates an incident and
optional bounded notification. No release occurs until all initialized steps/attempts settle.

V3 stores retry policy/count/first_attempt_at/next_action_at. DB UTC governs ownership and observation;
injected Clock governs retry domain budget. All engine DATETIME reads/writes explicitly map UTC
LocalDateTime, never the default JVM timezone. Development file I/O and crash-hook waits are outside
transactions. Production has no hook bean and recovers exclusively from durable database rows.

V4 incident identity is immutable and references the exact persisted attempt, direction, operation ID,
operation generation and permit generation. Completion and pre-I/O ownership checks require that same
identity in addition to lease/version checks. IN_DOUBT resolution cannot match only step_run_id.
UNKNOWN opens at most one incident per attempt/kind; a legitimate new attempt can open a new incident.
Both open/resolve audit changes commit with the result and next pending work. Legacy V3 incident rows
retain original status/audit and have legacy_unbound=true with all identity fields NULL; no inference or
automatic resolution of those historical rows is permitted. See ADR0006.

## Existing versus newly inserted engine incidents (ADR0007)

EngineService.execution is the shared ordered acquisition entrance: pool FOR UPDATE, execution FOR UPDATE,
then SELECT existing engine_incidents for that execution ORDER BY id FOR UPDATE. This precedes every
step/attempt write in claim, structural advancement, completion and elapsed-budget failure. Pre-I/O
ownership validation uses the same entrance. Exact incident/attempt/operation/direction/generation CAS
and all atomic result/next-work/audit behavior remain unchanged.

A fresh incident UUID does not name an existing row to pre-lock. Its insertion validates the already held
execution and step/attempt parents within the step tier; all relevant existing incidents were locked
before entering that tier. Repeated UNKNOWN with an existing incident still acquires it first, even if
no incident INSERT/UPDATE follows. Budget failure acquires resolved history before adding a new known
failure incident. Reacquiring an already-held pool/execution during safe release is not a new reverse lock.

## M4 durable adapter plan and cancellation

V5 preserves V1-V4 and adds step_attempts.adapter_plan, executions.cancel_requested and adapter_stops.
OperationAdapter.plan uses only already-loaded nonsecret catalog data. claim persists the catalog hash,
stable namespace/name/kind and generation with the attempt before external submit. Reclaim reads that
same plan and observes; a missing plan or changed catalog fails closed. FoundationIT requires migrations
1 through 7; EngineHistoryIT retains all prior history/audit assertions plus null-plan and false-cancel defaults.

EngineService.requestCancel takes pool -> execution -> existing incidents before recording cancel intent.
settle stops PENDING/RETRY_WAIT leaves and standalone notifications that have no active operation.
Existing active/unknown attempts still observe or cancel under their original identity and keep the
permit until all work is known settled. Each notification stop and state mutation includes audit in
the same transaction. M5 public commands use the same locking and convergence rules.

KubernetesAdapter writes its operation-bound stop intent in a short standalone DB statement outside
the engine result transaction, before any Kubernetes deletion. Concurrent callers cannot change its
recorded UID/reason. Resource deletion and Pod observation are outside transactions. The subsequent
engine completion still uses the exact operation, direction, lease, version and permit checks.
An accepted deletion or Deployment ProgressDeadlineExceeded alone does not permit release.

V6 stores nonsecret adapter_bindings during the same transaction as publication/default/audit. The
existing published-row DB trigger rejects mutation of this column. Claims only read that immutable
version row under the existing pool/execution/incidents/step protocol and compare pure local bindings;
no catalog file, credential, Kubernetes or HTTP I/O enters a transaction. Absent/drifted semantics produce
UNKNOWN/IN_DOUBT with held permit before any submit. Existing operation plans are not rewritten.
A fresh published version binds changed configuration explicitly; historical versions remain NULL.

## M5 transaction boundaries
AdmissionService.recover/tick use the same scheduler_pool row and admission_requests queue_sequence/cursor as initial admission. Pool -> execution -> all existing incidents -> admission request -> step applies throughout. RecoveryPolicy.validate has no external I/O. Queue persistence, pending_recovery_id, RECOVERY_QUEUED and audit share one commit. Admission revalidation/acquisition, incident consumption, step decision and audit share another. A stale incident withdraws the queue decision without acquiring or spending WRR weight. Rejected NOW writes only its immutable request decision/audit.
RecoveryPolicy.apply keeps V4 identity columns unchanged. V7 is additive; historical rollback snapshots and active targets stay NULL. Engine claim captures rollback input before forward submission using already persisted permitted inputs/prior outputs. External calls remain outside transactions.
OperatorService stores cancel/resolve immutable decisions in operator_commands, scoped by principal + endpoint + execution (+ incident for resolve). Recovery scope is principal + POST /executions/{id}/recoveries. The action/body belongs to the hash: changing action under the same key conflicts. DB uncertainty never becomes an admission rejection. Replay normalizes JSON through the same serialization as the stored decision. Optional output NULL has one canonical meaning before and after queue persistence.


M5 dispatch/cancel ordering: a fresh operation is dispatched at the claim transaction's durable INTENT_COMMITTED commit under pool -> execution locks. A later cancel commit prevents any new fresh claim, including pending parallel siblings and subsequent sequence work. An operation claimed before cancellation may still submit afterward with its saved identity. It retains the original permit and is subsequently cancelled/observed; a DELETE202 or WAITING result never proves termination. Only terminal evidence plus convergence of every started operation releases the permit. No cross-system atomic promise of zero HTTP requests after cancel returns is made. RecoveryCancellationIT controls claim -> public cancel -> execute against actual HTTP and an independently configured MariaDB; the M5 gate requires its ordered POST/DELETE/GET/DELETE/GET proof. DB fencing still does not revoke an already-sent HTTP request.


M5 operator payload protection (round3): OperatorPayloadGuard.prepare performs a read-only lookup of the exact execution/version and incident/step/attempt/operation/direction/generations. It requires nonlegacy identity, the original adapter plan and matching published/current binding; it does not infer missing legacy metadata. Only that leaf's configured credential reference is read, outside any DB transaction. Execution-scoped cancel/withdrawal instead uses this execution's exact published references. The same AdapterCatalog.safeOutput recursion protects normal REST and operator free-form output, reason/evidence, idempotency key and request identity; decoded nested strings, scalar representations, field names and the common forbidden fields are checked. No credential value enters the prepared token: it carries only context/body digests.

AdmissionService.recover and OperatorService.command recheck the immutable context and request digest under pool -> execution -> incidents before any new payload, decision, output or audit write. Invalid payload returns422 with no mutation, including capacity-rejected NOW. A missing credential file returns503 VALIDATION_UNAVAILABLE before mutation; stale/unbound/mismatched context fails closed. Existing same-key decisions are reread under lock and replayed without reading credential files again; a changed body remains409. Queue tick previews its candidate, prepares credentials without locks, then rechecks the chosen identity in the normal admission transaction. If the candidate changed, it returns without consuming cursor or permit; stale/invalid queued recovery is withdrawn, while unavailable credential validation leaves it queued. There is still one admission queue.

Optional absent output/replacementOutput fields are structural envelope absence; they are not treated as supplied scalar null. A supplied nested null still goes through the shared scalar guard, and required output schema rules still apply. This preserves STOPPED/FAILED resolution and RETRY/CANCEL when a configured credential is literally null/true/false. The file is read at preflight time; credential rotation is not an atomic cross-filesystem/DB transaction. Every new persistence boundary, including queued application, prepares again.

Crash acceptance snapshots use a separate test-only READ ONLY / REPEATABLE READ / WITH CONSISTENT SNAPSHOT transaction in scripts/crash_boundary.py. Before that read begins, all verified fixture-owned JVM threads are stopped and owner-labelled test MariaDB has no active transactions/commands. If SIGSTOP caught an app transaction, the helper resumes exact identities, observes real drain and retries a bounded number of times; it does not kill inside an unverified boundary. The snapshot transaction performs only DB reads and finishes before SIGKILL. All original state/lease/attempt/operation fields are compared after kill. This changes test observation only; application short-transaction and external-I/O rules remain unchanged.

FINAL round3: new admission prepares the exact input/key/requestId envelope against the selected version before the pool transaction. Under pool then route locks it rechecks immutable definition/bindings/envelope hashes before mutations; an already durable decision replays first, including when preparation failed. Registry metadata/delete snapshots only existing versions of that route; edit snapshots old and replacement definitions; withdrawal snapshots its selected draft. Route locks protect the pure snapshot recheck. Actual configured credential reads never occur inside these database transactions; credential-free checks may be pure inside an existing transaction. External credential rotation is not atomically serialized by these DB locks.
