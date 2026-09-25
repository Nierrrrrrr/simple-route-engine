# ADR 0004: Database admission implementation (M2)

The fixed architecture is unchanged. AdmissionService uses the existing short READ COMMITTED
TransactionTemplate; scheduler_pool row 1 is always the first business row locked. RouteRegistry gains
lockForNewExecution so a concurrent disable/delete/publish cannot bypass eligibility inside admission.
Registry-only transactions keep route locks and never subsequently acquire the pool.

V2 adds unique auto-increment queue_sequence for strict class FIFO when UTC timestamps tie. Queue
selection does not use UUID ordering. NOW participates as a temporary last-in-class candidate; only its
winning transaction creates an execution and advances WRR. QUEUE persists a bound published version
immediately and gets admitted later by the bounded wake loop. CRITICAL remains strict priority, shared
capacity allowed, no preemption; noncritical counts never exceed T-R.

Canonical parsed request content is hashed with sorted object keys. The identity is a deterministic UUID
from authenticated principal + fixed operation scope + Idempotency-Key, allowing uncertain callers to
retain identity before the DB responds. MariaDB unique constraints are authoritative. Original response_json
never changes; admission_requests.decision may advance. Return codes: 202 accepted/queued, 409 explicit
capacity reject or content conflict, 422 invalid/disabled, 503 unavailable/uncertain database. DataAccessException
and TransactionException (including commit wrappers) are caught as uncertain; no automatic retries occur.

M0 configUpdateCursorRule remains authoritative: only weight changes reset cursor to zero. Every accepted
config update increments version and writes complete append-only history + audit atomically. T 1..100000,
R 0..T and each weight 1..100 bound arithmetic and cycle allocation. These are validation limits, not defaults.
During self-review an initial implementation reset on every update; a focused real-DB failing regression
was added, then correction 1 preserved capacity-only cursor state without weakening the test.

The internal stop seam checks matching permit generation/state version and converged persisted work.
There is no public release API, no lease-triggered permit reclamation, no M2 external side effect. Later
workers must preserve the same safe-stop/fencing contract. Test-only holders are closed in pool-first SQL
transactions only in isolated test DBs. Real two-JVM, 200-way, SIGKILL, HTTP response-drop, deadlock and
DB stop/start fixtures supplement same-JVM invariants; no JVM synchronization establishes DB correctness.


M2 round2 preserves admission semantics and corrects only test fixture startup. Official pinned-image
healthcheck skips certificate verification; verified SQL can still reject a not-yet-valid certificate.
Readiness now uses the exact SQL client, retaining TLS verification and the original 90-second budget.
Only unused, owner/purpose-verified anonymous-volume initialization can be retried once on the exact
exited TLS failure; used database restart/outage never recreates. Strict expired/auth/SQL errors fail,
and diagnostics never expose credentials. Real peer-certificate red/green and safety policy regressions
record this decision; the underlying original time discrepancy remains unproven. No runtime service,
production transport/certificate configuration, transaction isolation or business assertion changes.
