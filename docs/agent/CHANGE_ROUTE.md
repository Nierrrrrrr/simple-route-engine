# Change a route

RouteRegistry stores an allocation high-water mark. POST /routes/{routeId}/versions allocates the next version;
the definition's routeId/version must match. GET the route first to obtain maxVersion.
Edit only DRAFT using PUT /routes/{routeId}/versions/{version} with definition and its stateVersion.
Publish with POST to the same version's /publish endpoint and {"stateVersion": currentVersionState}.
Published versions reject both HTTP editing and direct database UPDATE/DELETE.

Publishing v2 updates the route default while existing executions retain their route_version composite FK.
FoundationIT and AdmissionIT verify immutable bindings; the M3 engine reads the bound version, never the current default.
GET /routes/{routeId}/versions/1 remains available after disable and soft delete for old execution/recovery.
PATCH route metadata uses name/enabled/stateVersion. DELETE route uses query stateVersion and retains data.
DELETE an unpublished version withdraws its draft, retaining audit and never reusing its version number.

All route-definition HTTP mutations require the configured admin bearer token. Read the latest returned stateVersion before
the next mutation; stale values return 409 STATE_CONFLICT. Never edit published snapshots through a migration.
See docs/api/openapi.yaml for the actual request and response schemas. Controlled adapters and public recovery were accepted through M5; M6 is historically accepted and current FINAL awaits its own fresh handoff, full gate and review.

Published versions also bind controlled adapter semantics (V6). Editing a deployment catalog does not
change an older version's meaning: queued/active/retry work blocks with IN_DOUBT if its current adapter
binding differs. Keep old bindings available until work settles, or use available audited resolution;
never rewrite a published row. Publish v2 under the deliberately updated catalog to adopt new behavior.
Unknown or cross-kind refs, including rollback and notification, fail publication and retain DRAFT.

M5 recovery reads the execution-bound published version and adapter bindings, even if the route is disabled or a newer default is published. Never change an existing queued recovery to the new version; publish and submit a new execution for new semantics.

The available endpoint is POST /executions/{id}/incidents/{incidentId}/resolve (operator/admin). Read the incident and use its execution/incident IDs in the path. Supply Idempotency-Key and JSON stepId, operationId, outcome (SUCCEEDED/FAILED/STOPPED), reason, evidence and optional output as specified by OpenAPI. The server derives and rechecks attempt/generation identity; do not invent extra request fields. Resolution never silently adopts changed bindings: unbound, drifted or stale context fails closed. Use recover for the permitted human retry/rollback action after safe resolution.

## FINAL round3 envelope security repair and fresh handoff boundary

Round1 review found AC-041 input/definition credential persistence. Round2 repaired that gap and completed an actual415-case/35-report/63-check gate plus fresh agent54. Independent Reviewer55 then found configured credentials persisted through initial Idempotency-Key and X-Request-ID in decisions/audit and version requestId in audit. Round2 is CHANGES_REQUIRED; all round1/round2 evidence and both older Java baselines remain immutable.

Round3 Builder call56 extends PersistenceGuard to initial input/key/requestId, draft/publish requestId, edit old and replacement definition contexts, withdrawal selected draft, and metadata name/requestId or deletion against the affected route's existing versions. It reads only referenced REST credentials, including rollback/notification refs, outside DB transactions; no unrelated credential stores are enumerated. Fixed DSL/envelope metadata and deployed reference identifiers are not business literals. Exact version-context and envelope digests are rechecked under existing pool/route/execution locks before row, decision, cursor, permit or audit mutation. Unsafe content returns422; unavailable relevant credentials return503. Detected unsafe or unavailable-validation errors replace incoming requestId in response body and X-Request-ID with a generated correlation ID.

Existing durable accepted/rejected admission decisions replay before preparation errors and persist no replacement envelope; body conflicts remain409. Changed route/version context returns409 for fresh preparation. Credentials represent the pre-transaction read snapshot; external rotation is not atomically locked by MariaDB. A route with no definition has no selected credential context; metadata creation does not inspect unrelated secrets globally.

Version GET/list and historical execution checks retain round2 fail-closed behavior: unsafe definitions/inputs or unavailable relevant credentials stop without rewriting published definitions, dispatching unknown work, or releasing held permits. Restore credential access or publish a clean version and use audited reconciliation for existing operations. This repair does not erase historical data. Typed inputs, scalar output protection, binding drift, original idempotency decisions and lock order remain mandatory regressions.

Engine Java changes are intentional security repairs before fresh handoff. STATE.final_java_baseline schema_version1 selects only .evidence/desktop/final-20260926-d831/baseline/engine-java-security-repair-round3.json. Root creates that immutable map after Builder freeze and records differences from the round2 baseline separately. The resolver rejects older/substituted, missing, traversing and symlinked baselines. New acceptance agent57 independently authors round-3/handoff-agent-1/demo6.json and executes all six routes without Java/source changes against this repaired baseline. Builder does not author or execute route6.

Current evidence is .evidence/desktop/final-20260926-d831/FINAL/round-3. After builder-source-freeze.json, root creates candidate-freeze.json and the Java baseline, obtains agent57's handoff, seals fresh-handoff-receipt.json, runs main-gate-1, then dispatches new Reviewer58. These steps remain pending. ENGINEERING_ACCEPTANCE=NOT_PASS; EXTERNAL_ACCEPTANCE=NOT_RUN; PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED. Builder COMPLETE means preparation only.
