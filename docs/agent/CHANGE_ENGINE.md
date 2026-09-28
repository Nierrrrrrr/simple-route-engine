# Change the durable engine

Start with the fixed ai-kit contract, actual STATE/HANDOFF, EngineService and V1/V2/V3 migrations.
Never rewrite an accepted migration or published route snapshot. New columns/tables use a new migration.
M3 separates engine tree progression, OperationAdapter I/O and EngineScheduler's bounded wakeup/executor.

Preserve pool -> execution -> existing incident/admission -> step/attempt lock order and short READ COMMITTED transactions. EngineService.claim
creates attempt/identity before commit. execute checks current authority and performs I/O after commit.
complete must atomically persist outcome, incident changes, branch join/next PENDING nodes and event.
Changing this order requires new atomic rollback and genuine process crash tests, not just unit mocks.

The step lease uses DB UTC and generation/state-version CAS; retry budgets use domain Clock persisted as
UTC DATETIME. permit_generation, lease_generation and operation_generation have separate purposes.
An expired lease or missing external operation never proves safe release or retry. All initialized work,
attempts and notifications must be terminal before AdmissionService.stop releases a matching permit.

DefinitionRules limits tree depth/nodes/parallel and validates typed backward dependencies. Keep the
machine schema and OpenAPI synchronized. New language behavior must fail closed for unsupported versions.
Run M0–M3 cumulative tests and all later implemented phases. Add failure-first cases to EngineIT,
EngineDslTest and scripts/engine_gate.py as appropriate. Keep existing admission-only scanner-disable
settings; dedicated engine processes must remain enabled. Freeze source/docs before fresh review.
Incident changes must preserve V4 exact attempt/operation/direction and generation identity, including
legacy_unbound history. Run EngineHistoryIT before EngineIT on their dedicated fresh database.
Never resolve by step alone or let a prior resolved incident suppress a new attempt's UNKNOWN event.
See ADR0006 and the round2 regression; no admission permit reset is an acceptable test isolation fix.

Preserve the common pool/execution/existing-incident acquisition before all step/attempt writes.
EngineIT.AC028_existingIncidentLock* uses actual incident contention and independent step/attempt NOWAIT
locks for terminal, repeated UNKNOWN and claim-budget paths. Keep these assertions and their bounded
waits. New incident insertion must not accidentally reacquire an older incident after step work; ADR0007
records the FK parent audit. Do not treat the pool lock as an exemption from the fixed acquisition order.

For recovery changes inspect AdmissionService.recover/tick, RecoveryPolicy.validate/apply, OperatorService.command and EngineService.settle/claim/confirm. Preserve fixed lock order and V4 incident identity; append migrations after V8. Run cumulative M5 for AC-001 through AC-050, including real process crashes, mixed admission/recovery WRR and old callback/release fencing.


Operator mutations must call OperatorPayloadGuard.prepare before entering a transaction and recheck its immutable context/body digest after the fixed pool/execution/incident locks. Do not read credential files while holding DB locks, persist a prepared secret, skip queue revalidation or change original idempotent decisions. RecoveryOutputProtectionIT and guard proof negatives must remain mandatory.

M6 changes also require AC-051 through AC-058. V8 adds operations indexes only; append future migrations after V8. Preserve ClaimLifecycle checks after database wait boundaries, original principal identity and accepted M5 artifact migration proof. Run cumulative M6; never use a newly built candidate as the old upgrade engine.
