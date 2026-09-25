# Failure and recovery contract

Before intent commit, no external operation may exist. After intent commit/before submit, reconcile the durable identity.
After submit/before response, use the same operation identity to observe or dedupe only if adapter contract allows it.
After response/before result commit, recover by observation, never infer failure from a lost response.
After result commit/before next tick, the next due node already exists atomically and restart scans it.
Expired leases fence late writes; DB fencing does not revoke an HTTP request already sent by a stale worker.

Unknown, unsafe-to-repeat side effects enter IN_DOUBT; hold permit and stop unsafe subsequent nodes.
Operator resolution must supply evidence and confirm only SUCCEEDED/FAILED/STOPPED for that operation.
Kubernetes Job name/labels/UID remain durable; known submitted but GC-missing Job is unknown, not permission to create another.
Deleting a Job is a request, not confirmation all local/remote work has stopped. No untracked Ansible async poll:0.

Each adapter defines submit, observe/reconcile, cancel, terminal success/failure, retryability, dedupe, safe resubmit,
output schema, redaction and optional compensation. There is no exactly-once side-effect guarantee.
REST uses endpointRef allowlists, bounded responses, TLS, no credential-forwarding redirects.
Ansible Jobs have stable identity, no Application Pod owner, pinned image/playbook, backoffLimit=0, persistent artifacts.
Notification attempts are bounded, never recurse, preserve the primary incident, and settle before release.

M3 executes commit/branch/retry/unknown process kill/restart; M4–M5 extend external and recovery boundaries. Six-hour retry timing uses a controllable clock;
short real-time asynchronous restart tests are separate. This is not a six-hour soak claim.

Actual M3 evidence comes from scripts/engine_gate.py::process_acceptance, with separate JVMs, SIGKILL
and SQL snapshots. EngineIT rolls back completion to prove output/next pending/event cannot partially
commit. Missing committed fixture identity becomes IN_DOUBT; it is never blindly submitted again.

## Implemented M4 behavior

RestAdapter submits once for a newly committed intent and reclaims by GET of the same operation UUID.
A timeout, response loss, wrong operation result, malformed/oversized response, redirect or unavailable
query leaves UNKNOWN; none authorizes a new POST. An explicit terminal retryable failure permits a new
business attempt/UUID. onFailure uses the same protocol with finite attempts and never recursive notices.

KubernetesAdapter persists re-{operationId}, namespace/kind/generation before creating a resource.
Real 409 conflicts cause observation. Reclaim after response loss queries the same name and checks
UID/run/purpose/generation; GC-missing submitted resources stay UNKNOWN. Failed rollouts and cancellation
persist stop intent before normal resourceVersion-bound delete, then wait for all local work to stop.
App Pods are not Job owners. backoffLimit=0 avoids one retry layer, but Kubernetes may start a Job more
than once; no exactly-once promise follows from a stable name.

Runner artifacts stay on PVC under the operation UUID. rc/status/stdout/job_events and command are
retained. Runtime uses file-mounted secrets, an allowlisted clean environment, nonroot/read-only root
and a writable /tmp. The full M4 gate deletes the original successful Pod before a separate reader
checks all files, DB snapshot and logs for the generated test secret. Raw failed evidence stays preserved.
External inventories, remote async work, enterprise gateways and production credentials are EXTERNAL_NOT_RUN.

M5 real HTTP crash tests kill independent JVMs after recovery enqueue, after permit admission before dispatch, during external work before DB result, and after result+permit release. Each restart uses the durable queue/operation; per-operation remote submit/effect counters must remain1. Old callbacks and release calls cannot change a newer permit generation. Completed compensation leaves a new COMPENSATED manual incident with CANCEL only. An operator-confirmed STOPPED/FAILED operation becomes a current failure incident only after all work settles. No force-release endpoint exists.
