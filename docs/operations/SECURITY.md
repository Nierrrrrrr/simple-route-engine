# M4 adapter security boundaries

The catalog and explicit kubeconfig are deployment-owned. Route definitions select validated references,
never arbitrary hosts, paths, images, namespaces, shell commands or remote inventories. REST allows
HTTPS with standard certificate/hostname verification, or explicitly enabled loopback HTTP for tests.
allowedHost must match the configured URI, and URI credentials/query/fragment are rejected. Requests
have finite timeouts and byte limits; redirects are never followed. Authorization values are read
from configured files during I/O, omitted from snapshots/audit and rejected if echoed in outputs.

config/kubernetes/adapter-role.yaml is an undeployed namespace-scoped Role template: only get/create/
delete on Jobs/Deployments and get/list on Pods. It grants no Secret read, exec, cluster-admin or
wildcards. Operators must select the actual work namespace and bind only the intended engine identity;
this task does not apply production RBAC. Local fixture setup/reader privileges are separate from the
engine's minimal runtime role. Explicit kubeconfig/context avoids home/service-account fallback.

Controlled work Pods run as UID/GID1000, without a service-account token, privilege escalation or
capabilities. Their root filesystem is read-only; /tmp is an emptyDir. Runner mounts its pre-created
artifact PVC and optional Secret volume read-only at /run/route-secrets (file mode0440). It clears
inherited environment before Runner records command, and synchronous localhost playbooks read the
credential from the file with no_log. No async poll:0 or untracked remote work is supported.

Runner's rc/status/stdout/job_events/command remain available on PVC after Pod deletion. Access must
be restricted and retention managed by operators. The test suite scans every artifact byte, the DB
snapshot and logs for an ephemeral secret, including an intentionally injected inherited-env canary;
a detected secret fails before unredacted capture is persisted as test evidence. Secrets are never
included in the DB artifact index, route input, operation plan or API error.

M6 RequestSecurityFilter uses SHA-256 hashes with constant-time comparison. ROUTE_ADMIN_TOKEN_SHA256 is required; missing/malformed or duplicate cross-role hashes refuse startup in every profile. Optional ROUTE_CALLER_TOKEN_SHA256 and ROUTE_OPERATOR_TOKEN_SHA256 enable the fixed caller and operator principals. The legacy admin principal remains local-admin, preserving old idempotency identities. This minimal deployment has one principal per role; it is not a multi-user identity server.

Caller may read routes/capacity and its own execution/admission decisions, and submit executions. Operator can submit, read operational execution state across principals, discover incidents and recover/cancel/resolve. Admin additionally edits routes/versions and capacity configuration. Only admin/operator may read metrics. Admission decision lookup remains principal-scoped, including admin/operator; tokens cannot impersonate a caller by supplying actor fields. Unknown mutations fail closed for non-admin. Health GET probes alone are unauthenticated and expose no details.

Generate a 32-byte random token outside source and hash it with SHA-256; distribute the raw token only to its principal and store hash variables in deployment Secret references. Each role accepts at most two comma-separated hashes for a bounded rotation overlap. Restart with old,new hashes, switch clients, then restart with only new; both hashes retain the same actor and idempotency scope. Never reuse the same hash across roles. Raw tokens are not persisted by the filter or logged. Local scripts use generated disposable tokens.
EXTERNAL_ACCEPTANCE=NOT_RUN; PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED.

The output guard covers every JSON scalar: decoded strings and field names, and the actual canonical
JSON representation for numbers, booleans and null. It recurses through objects and arrays before the
engine can save output or resolve downstream inputs. Thus numeric credentials echoed as numbers, and
literal true/false/null credentials, fail closed just as the same text does. It preserves valid nonsecret
scalar types/values and adds no credential-character restriction. Numeric lexical normalization is
covered (response1e2 persists as100.0), while escaped-string comparison still uses decoded content.
The true HTTP/MariaDB scalar regression also checks audit values and that the controlled raw response
body never enters logs; incidental generic words in framework logs are not classified as secret echo.


M5 operator payload protection (round3): OperatorPayloadGuard.prepare performs a read-only lookup of the exact execution/version and incident/step/attempt/operation/direction/generations. It requires nonlegacy identity, the original adapter plan and matching published/current binding; it does not infer missing legacy metadata. Only that leaf's configured credential reference is read, outside any DB transaction. Execution-scoped cancel/withdrawal instead uses this execution's exact published references. The same AdapterCatalog.safeOutput recursion protects normal REST and operator free-form output, reason/evidence, idempotency key and request identity; decoded nested strings, scalar representations, field names and the common forbidden fields are checked. No credential value enters the prepared token: it carries only context/body digests.

AdmissionService.recover and OperatorService.command recheck the immutable context and request digest under pool -> execution -> incidents before any new payload, decision, output or audit write. Invalid payload returns422 with no mutation, including capacity-rejected NOW. A missing credential file returns503 VALIDATION_UNAVAILABLE before mutation; stale/unbound/mismatched context fails closed. Existing same-key decisions are reread under lock and replayed without reading credential files again; a changed body remains409. Queue tick previews its candidate, prepares credentials without locks, then rechecks the chosen identity in the normal admission transaction. If the candidate changed, it returns without consuming cursor or permit; stale/invalid queued recovery is withdrawn, while unavailable credential validation leaves it queued. There is still one admission queue.

Optional absent output/replacementOutput fields are structural envelope absence; they are not treated as supplied scalar null. A supplied nested null still goes through the shared scalar guard, and required output schema rules still apply. This preserves STOPPED/FAILED resolution and RETRY/CANCEL when a configured credential is literally null/true/false. The file is read at preflight time; credential rotation is not an atomic cross-filesystem/DB transaction. Every new persistence boundary, including queued application, prepares again.

## FINAL round3 envelope security repair and fresh handoff boundary

Round1 review found AC-041 input/definition credential persistence. Round2 repaired that gap and completed an actual415-case/35-report/63-check gate plus fresh agent54. Independent Reviewer55 then found configured credentials persisted through initial Idempotency-Key and X-Request-ID in decisions/audit and version requestId in audit. Round2 is CHANGES_REQUIRED; all round1/round2 evidence and both older Java baselines remain immutable.

Round3 Builder call56 extends PersistenceGuard to initial input/key/requestId, draft/publish requestId, edit old and replacement definition contexts, withdrawal selected draft, and metadata name/requestId or deletion against the affected route's existing versions. It reads only referenced REST credentials, including rollback/notification refs, outside DB transactions; no unrelated credential stores are enumerated. Fixed DSL/envelope metadata and deployed reference identifiers are not business literals. Exact version-context and envelope digests are rechecked under existing pool/route/execution locks before row, decision, cursor, permit or audit mutation. Unsafe content returns422; unavailable relevant credentials return503. Detected unsafe or unavailable-validation errors replace incoming requestId in response body and X-Request-ID with a generated correlation ID.

Existing durable accepted/rejected admission decisions replay before preparation errors and persist no replacement envelope; body conflicts remain409. Changed route/version context returns409 for fresh preparation. Credentials represent the pre-transaction read snapshot; external rotation is not atomically locked by MariaDB. A route with no definition has no selected credential context; metadata creation does not inspect unrelated secrets globally.

Version GET/list and historical execution checks retain round2 fail-closed behavior: unsafe definitions/inputs or unavailable relevant credentials stop without rewriting published definitions, dispatching unknown work, or releasing held permits. Restore credential access or publish a clean version and use audited reconciliation for existing operations. This repair does not erase historical data. Typed inputs, scalar output protection, binding drift, original idempotency decisions and lock order remain mandatory regressions.

Engine Java changes are intentional security repairs before fresh handoff. STATE.final_java_baseline schema_version1 selects only .evidence/desktop/final-20260926-d831/baseline/engine-java-security-repair-round3.json. Root creates that immutable map after Builder freeze and records differences from the round2 baseline separately. The resolver rejects older/substituted, missing, traversing and symlinked baselines. New acceptance agent57 independently authors round-3/handoff-agent-1/demo6.json and executes all six routes without Java/source changes against this repaired baseline. Builder does not author or execute route6.

Current evidence is .evidence/desktop/final-20260926-d831/FINAL/round-3. After builder-source-freeze.json, root creates candidate-freeze.json and the Java baseline, obtains agent57's handoff, seals fresh-handoff-receipt.json, runs main-gate-1, then dispatches new Reviewer58. These steps remain pending. ENGINEERING_ACCEPTANCE=NOT_PASS; EXTERNAL_ACCEPTANCE=NOT_RUN; PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED. Builder COMPLETE means preparation only.
