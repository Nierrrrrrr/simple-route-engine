# Local operations through M6

This is the isolated development engine runbook. Production deployment is NOT_AUTHORIZED.
M4 includes actual isolated REST/Kubernetes/Runner tests and controlled catalog-backed adapters.
Enterprise endpoints/credentials remain EXTERNAL_NOT_RUN. There is no public permit-release endpoint.

Use the run-specific environment described in [testing](../agent/TESTING.md). A configured SHA-256
admin bearer token hash and database connection are mandatory; there is no default credential.
Start the built application with `bash scripts/local-run.sh`. It binds loopback by default.

```bash
curl -sS -H "Authorization: Bearer $ROUTE_TOKEN" http://127.0.0.1:8080/capacity
curl -sS -H "Authorization: Bearer $ROUTE_TOKEN" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-request-001' -X POST http://127.0.0.1:8080/executions \
  --data '{"routeId":"demo-process-admission","priority":"NORMAL","admissionMode":"QUEUE","input":{}}'
curl -sS -H "Authorization: Bearer $ROUTE_TOKEN" \
  'http://127.0.0.1:8080/admission-requests?key=demo-request-001'
```

The route must already be published; follow registry examples and use an existing DEMO route ID. Route
version omitted means bind its latest published version now, never at dequeue. The lookup returns the
original decision even if the execution is now admitted; GET /executions/{id} returns current permit/state.
A 503 or lost response is uncertain: retain/retry the same key or look it up. A recorded rejection remains
rejected even after capacity returns; deliberately use a new key for another competition.

To pause admission, GET /capacity and PUT /capacity/config with its current configVersion, all total/reserve/
weight values, admissionEnabled=false and an operator reason. To resume, repeat with a fresh version and
admissionEnabled=true. Pausing prevents new permit acquisition but still durably accepts QUEUE requests;
NOW is explicitly rejected. Held permits are unaffected. Weight changes reset WRR cursor; other changes
preserve it. Unsafe shrink and stale configVersion return 409 with no config/history mutation.

SIGTERM stops the local process gracefully; SIGKILL also leaves durable queue and permits. After restart
the scheduler scans MariaDB again. Never repair permit_held with manual SQL in real use; isolated acceptance
fixtures may simulate admission-only holders. M5 operator actions below preserve exact identities and never bypass safe release.

Default route.engine settings: enabled=true, workers=4, queue-size=16, scan-ms=100, lease-seconds=30,
poll-seconds=1. Disabling scans does not stop external work or release permits. SIGTERM stops scheduling,
waits up to5s for workers, then interrupts local workers; interruption is not evidence of remote stop.
For isolated fixtures only set SPRING_PROFILES_ACTIVE=engine-development and ROUTE_ENGINE_FIXTURE_DIRECTORY
to a run-owned directory. Never enable this profile in production. Leave pause-after-node unset for normal
development. IN_DOUBT retains permit until known observation or audited operator resolution.

## Historical incidents after V4

V4 preserves historical engine_incidents as legacy_unbound=true with NULL attempt/operation identity.
Do not infer identity from the newest attempt, use these rows to retry/skip current work, or force-release
a permit. Current engine incidents always bind exact attempt, operation, direction and generations.
Known observation resolves only that identity; previous resolved incidents remain for audit. Unbound
history requires investigation; M5 refuses legacy-unbound recovery/resolve instead of guessing.

## Adapter operations

Set ROUTE_ADAPTERS_CONFIG to an operator-owned JSON catalog as described in ADD_ADAPTER. An empty
catalog permits no real adapter target. Use only the explicitly configured kubeconfig/context and
namespace; never rely on a user's home context. Prepare the immutable Runner image and artifact PVC
before selecting their controlled references. The integration fixture provisions only isolated test resources.

Keep an operation's catalog entry unchanged while it is active. A changed hash or vanished previously
submitted resource causes UNKNOWN, preserves the incident/permit and stops unsafe subsequent work.
Do not recreate the missing Job or infer failure from HTTP timeout. Inspect that exact operation and
its recorded UID externally; submit evidence through the M5 resolve API below.

Completed Runner artifacts live at the recorded PVC/path, independent of the app and Runner Pods.
Restrict PVC access; command artifacts contain the sanitized environment. Secret references must resolve
to files, never environment values or route input. Rotating a REST credential file preserves its reference;
active catalog target changes require reconciling existing work first. Do not erase artifacts before
retention/audit obligations are established for a real deployment.

V6 publication freezes endpoint/resource and explicit Kubernetes target semantics. A changed catalog,
playbook, image or kubeconfig content/context cannot retarget an old queued version or business retry.
The execution becomes IN_DOUBT/RECONCILING and retains its permit. Inspect the immutable version
binding and original operation plan first. Restore the original configuration to observe an existing
saved operation; do not automatically submit a never-submitted blocked marker. New behavior needs a
new published version. Legacy NULL bindings have the same fail-closed behavior and must not be
backfilled from the current catalog. Use the exact-operation manual resolution below; do not force-release slots.

## M5 operator actions
All calls use the authenticated bearer identity, never a body actor or priority override.
First discover exact identifiers:
```bash
curl -sS -H "Authorization: Bearer $ROUTE_TOKEN" "http://127.0.0.1:8080/executions/$EXECUTION_ID/incidents"
```
Copy the returned incidentId and stepId into INCIDENT_ID and STEP_ID. Use only actions currently listed.
```bash
curl -sS -H "Authorization: Bearer $ROUTE_TOKEN" -H 'Content-Type: application/json'   -H 'Idempotency-Key: recovery-001' -X POST "http://127.0.0.1:8080/executions/$EXECUTION_ID/recoveries"   --data "{\"incidentId\":\"$INCIDENT_ID\",\"stepId\":\"$STEP_ID\",\"action\":\"RETRY\",\"admissionMode\":\"QUEUE\",\"reason\":\"Verified external failure and reviewed retry\"}"
```
RETRY/SKIP/ROLLBACK/CANCEL all accept QUEUE or NOW_OR_REJECT. SKIP may require replacementOutput satisfying the failed node outputSchema. Rollback is current-step-only and requires its declaration/captured context. After successful compensation, rediscover the new COMPENSATED incident and use CANCEL to end the route; old incident IDs are consumed. Failed compensation exposes a new rollback incident whose RETRY does not run forward.
Running cancel: POST /executions/{id}/cancel with Idempotency-Key and {"reason":"..."}; no new permit. The same endpoint withdraws QUEUED or RECOVERY_QUEUED without external work. Manual CANCEL instead uses /recoveries and a current incident.
Unknown operation: inspect external evidence for the exact operationId/UID, then POST /executions/{id}/incidents/{incidentId}/resolve with Idempotency-Key and {"stepId":"...","operationId":"...","outcome":"FAILED","reason":"checked","evidence":"exact external terminal record"}. SUCCEEDED also accepts output matching the existing schema; STOPPED requires confirmed stop. This confirms only the existing operation and does no submit. Unknown siblings/notifications retain the permit. Keep evidence nonsecret and concise; reason/evidence each max200.
Recovery responses expose admissionRequestId; GET /admission-requests/{id} returns the original decision to the same principal. Same key/body replays after any state advance. A rejected NOW never becomes queued; a new capacity competition needs a new key. On503 or lost response, retain/retry the original key. Never edit permit flags or incident identities manually.

M5 rollback when uses the same permitted immutable context as its captured input; rollback_allowed is saved before forward submission. A false/missing captured guard rejects ROLLBACK with422 and leaves its current incident unchanged. STOPPED confirmation offers RETRY/CANCEL. After a successful forward recovery with no other failed operation, never-dispatched stopped nodes reopen; already successful steps/condition choices remain unchanged.


M5 dispatch/cancel ordering: a fresh operation is dispatched at the claim transaction's durable INTENT_COMMITTED commit under pool -> execution locks. A later cancel commit prevents any new fresh claim, including pending parallel siblings and subsequent sequence work. An operation claimed before cancellation may still submit afterward with its saved identity. It retains the original permit and is subsequently cancelled/observed; a DELETE202 or WAITING result never proves termination. Only terminal evidence plus convergence of every started operation releases the permit. No cross-system atomic promise of zero HTTP requests after cancel returns is made. RecoveryCancellationIT controls claim -> public cancel -> execute against actual HTTP and an independently configured MariaDB; the M5 gate requires its ordered POST/DELETE/GET/DELETE/GET proof. DB fencing still does not revoke an already-sent HTTP request.


Operator output rejection:422 INVALID_REQUEST can indicate a bound credential or forbidden field in output, reason/evidence or request identity. Do not copy credentials from provider evidence. Execution/incident/permit and command/admission state remain unchanged; correct the payload before retrying.503 VALIDATION_UNAVAILABLE means the exact bound credential cannot currently be checked; restore that deployment-owned reference and retry. Same-key replay of an already stored decision remains available without the credential file. Legacy/unbound or changed binding context fails closed; do not substitute current catalog metadata for missing historical identity.


## M6 operational lifecycle and observations

RequestSecurityFilter enforces caller/operator/admin; see SECURITY.md. Operator/admin can read caller-created execution status, while admission decision lookup remains scoped to its original principal. Pause admission using PUT /capacity/config with admissionEnabled=false and the current configVersion, not by reducing capacity below held permits. Existing work retains its permit. GET /capacity is only an observed snapshot.

SIGTERM triggers ClaimLifecycle on ContextClosedEvent. EngineService.claim rechecks after DB locks; queued local tasks cannot begin a new claim after stopping. Admission wake/submission likewise stop. Already committed operations may complete or remain durable for restart; shutdown does not release permits or delete Jobs. Spring graceful HTTP shutdown and the worker five-second bounded drain are separate from business safe-stop. For Kubernetes retain a45-second termination grace period and the unchanged stable Job identities. After SIGKILL restart scans DB and reconciles; never force-release unknown external work.

GET /actuator/health/readiness includes DB health; liveness does not depend on target HTTP success. GET /actuator/metrics requires operator/admin. route.queue.depth, route.permits.total/noncritical, route.admission.rejected, route.retry.wait, route.in.doubt, route.stalled, route.lease.expired, route.reconcile.events and route.scheduler.lag.seconds are durable DB observations. Query errors return NaN, never a cached capacity admission decision. Alert on unknown/stalled/lag growth and investigate with incident/audit identities. Gauge totals are current DB observations, not process-lifetime counters.

ROUTE_LOG_FILE selects the persistent log file; default local path is .local/logs/route-engine.log. Logback rolls10MB files with seven-day history and100MB cap. Production template mounts a log PVC; Runner artifacts use a separate catalog PVC. Restrict both volumes and apply approved retention. Backup/restore proof and template configuration are in DEPLOYMENT.md. An unavailable DB stops readiness/admission; target API failure alone must not restart the entire app.

FINAL round3 credential-envelope rejection:422 performs no admission/version/audit mutation;503 indicates relevant validation is unavailable. Detected-unsafe or unavailable-validation errors generate a new response correlation ID rather than echo the incoming X-Request-ID. Retain that safe response ID; do not paste the rejected credential-bearing header into logs or retry records. Historical unsafe definitions/executions remain unchanged and fail closed; restore safe validation or use a clean published version and audited reconciliation, never force-release unknown work. Existing durable admission decisions continue to replay without a new credential read.
