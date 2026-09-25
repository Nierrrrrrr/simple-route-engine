# ADR 0006: incident identity and independent engine test database

M3 round1 exposed two concrete failures. The cumulative AdmissionIT suite correctly leaves a configured
one-slot pool, one held permit and one queued request. EngineIT incorrectly reused that business state
and failed to assert its admission result. Separately, the V3 unique key on step_run_id/kind suppressed
a new IN_DOUBT incident after a known terminal observation and legitimate second business attempt.

The cumulative clean Maven verify now receives two fresh, run-owned MariaDB containers. FoundationIT
and AdmissionIT use the first; EngineHistoryIT and EngineIT require ROUTE_ENGINE_TEST_DB_URL/USER/PASSWORD
for the second with no fallback. EngineIT always asserts202, ADMITTED and a nonempty execution ID.
Alphabetical failsafe class order lets EngineHistoryIT verify actual V1–V3 legacy data through V4
before EngineIT uses that database. Every original business assertion still executes. Only engine-owned
fixture rows are retired by engine teardown; admission business permits are never changed for isolation.
The gate records distinct IDs/URLs, zero cross-suite rows, nonzero intended rows and owner-checked cleanup.

V4 preserves V1/V2/V3 and existing incidents. Historical rows receive legacy_unbound=true and NULL operation
identity; neither status nor audit is rewritten and an attempt is never inferred from the latest row.
These rows are historical evidence requiring explicit future operator analysis, not an automatically
actionable decision about a current operation. M5 operator resolution remains unimplemented.

New incidents bind immutable attempt_id, step_run_id, operation_id, direction, operation_generation and
permit_generation. Composite foreign key and unique(attempt_id,kind) preserve exact attempt association.
The old step unique key is replaced with a nonunique step index to preserve its existing foreign key.
Terminal result processing resolves only that bound identity in the same transaction as result, next
pending work and audit. A fresh business attempt can open its own incident, preserving previous history.
Current-worker validation also matches the persisted attempt/operation/direction before any result or I/O.

Regressions cover UNKNOWN -> known retryable FAILED -> new UNKNOWN, old lease/operation rejection,
incident identity immutability, transactional result/incident/audit rollback, and conservative legacy
migration. Six real engine crash cases and the original cumulative gates must pass again on frozen source.
