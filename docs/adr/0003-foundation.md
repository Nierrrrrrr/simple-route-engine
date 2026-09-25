# ADR 0003 — M1 persistence and local acceptance

M1 uses explicit JDBC and a shared READ COMMITTED TransactionTemplate. Registry writes lock the route
row first; they never acquire scheduler_pool or execution locks. Future admission takes pool first.

Published versions are immutable by application guards and MariaDB triggers. max_version is a high-water
mark: withdrawing a DRAFT never reuses a number. Publishing older drafts cannot move the default backwards.
Soft delete retains definitions and execution references. Execution binding/priority are immutable in DB.
State CAS checks affected rows. execution_events is append-only; AuditLog.append requires a transaction.
Route mutation and audit commit together. Audit version is retained historical metadata after draft
withdrawal, while execution bindings use the required composite FK.

M1 accepts a strict structural DSL subset (SEQUENCE and REST/KUBERNETES/ANSIBLE leaves); unsupported
condition/parallel/retry/rollback fields fail closed until M3 semantic validation. No activity executes.
Current auth requires a high entropy admin bearer token SHA-256 hash. No default token is embedded;
full caller/operator/admin mapping and rotation remain M6. Local runner binds 127.0.0.1.

scripts/foundation_gate.py creates a run-labelled database, runs Maven clean verify, then starts
scripts/local-run.sh in two distinct processes with an actual Docker database restart between them.
The image is pinned in config/mariadb-image.txt. Generated temporary secrets are never command logs.

M0 future-phase negative tests now cover M2–FINAL because M1 has actual acceptance.
All mandatory assertions remain; M1 additionally requires nonempty unit, integration and process cases.

M1 round 2 adds ApiJsonConfiguration: JSON scalar token types are checked before Bean Validation and
stateVersion comparisons; string/number/boolean coercion and floating-point truncation are forbidden.
ApiErrors preserves Spring HTTP client statuses/headers instead of converting framework errors to 500.
Both changes have live HTTP regression coverage with zero-mutation assertions, not mock-controller tests.

M1 round 3 requires complete single-root JSON consumption with FAIL_ON_TRAILING_TOKENS. A valid
prefix followed by garbage or another value is invalid before dispatch. RouteController declares
application/json as its produced representation, causing incompatible Accept rejection before
registry mutation transactions. A 406 response must not conceal a successful write. Existing
ApiErrors provides the JSON error envelope even when the requested success representation is unavailable.
