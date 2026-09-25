# ADR 0002 — API, authentication and DSL boundaries

Use explicit Spring JDBC with short transactions. Default capacity and WRR are in
[defaults](../../config/defaults.json); [transaction ordering](../architecture/TRANSACTIONS.md) applies globally.

HTTP accepted/queued = 202; capacity rejection = 409 ADMISSION_REJECTED; incompatible state/idempotency body = 409;
invalid route/action = 422; uncertain commit or DB unavailable = 503 with requestId and original idempotency identity.
No Reservation API; capacity is observedAt/configVersion snapshot. NOW means permit in the same transaction, not start SLA.

Simple bearer principals have caller/operator/admin roles; no new IAM service. Generate at least 32 cryptographically random
bytes for tokens. Store only SHA-256 token hashes and principal/role mapping in referenced secret configuration; compare in
constant time. High entropy prevents offline dictionary recovery. Raw token returned once to operator outside application logs.
Rotate by installing a new hash, accepting both for bounded overlap, then removing old hash and auditing the config version.
Production mode rejects missing/empty auth configuration; local tests use ephemeral tokens. Credential refs may occur in DSL,
values never in snapshots/audit/exceptions/runner indices. Do not log authorization/request payloads.

DSL is JSON, explicit typed comparison AST, no eval/script/goto/loop. SEQUENCE, CONDITION, PARALLEL ALL_SETTLED (depth one),
REST, KUBERNETES, ANSIBLE; finite onFailure notification and opt-in per-step rollback. Defaults bound node count=100 and branches=10.
Publish rejects unknown fields/types, duplicate node IDs, missing or cyclic dependencies, unsafe expressions and version mismatch.
M3 implements validator; current [DSL reference](../routes/DSL_REFERENCE.md) and schema are design drafts, not a running registry.
