# Add an adapter

The actual seam is src/main/java/dev/routeengine/engine/OperationAdapter.java.
Register a Spring bean implementing supports, binding, submit, observe and cancel. binding(node) and
plan(Request) are pure local
functions of already-loaded non-secret catalog configuration; it must not read files, credentials, DB or
network. EngineService.claim persists its returned JSON in V5 step_attempts.adapter_plan before commit.
Request includes operationId, operationGeneration, business attempt, direction, frozen node/input,
persisted context, previously observed externalUid and cancelRequested. Historical attempts lacking a
plan do not invent one and real adapters fail closed.

EngineService.execute checks DB fencing and calls I/O outside a transaction. complete atomically saves
outcome, next work and audit. Outcome is SUCCEEDED/FAILED/WAITING/UNKNOWN/STOPPED, optional typed output,
known-terminal retryability, and externalUid. UNKNOWN never permits submit. A fresh business attempt
gets a fresh operation UUID/generation; observation/transport uses the existing identity. A rollback
request must have direction ROLLBACK and a distinct operation, rather than borrowing a forward key.
No DB fencing scheme revokes an already transmitted HTTP request or guarantees exactly-once side effects.

M4 candidate implementations (fresh review required):
- adapters/AdapterCatalog loads a deployment-owned JSON file selected by route.adapters.config.
- adapters/RestAdapter implements a bounded JSON operation protocol at controlled endpointRef values.
  POST includes operationId, direction, operationGeneration and input; GET /{operationId} observes.
  A 202 is WAITING. Terminal results must name that exact operation and explicitly attest status.
  FAILED only becomes retryable when the endpoint attests both terminal failure and retryable.
  No redirects are followed. TLS is required except explicitly allowed loopback test HTTP.
  Credentials are file references loaded only at I/O, never route inputs or the persisted plan.
- adapters/KubernetesAdapter handles controlled KUBERNETES and ANSIBLE references. Pure plan freezes
  catalog hash, namespace, kind and name re-{operationId}. Observe checks UID and Deployment generation;
  a previously submitted missing resource is UNKNOWN. Failed rollout persists a stop intent before
  requesting deletion, and only absence of both resource and labelled Pods proves its local work stopped.
  EngineService.requestCancel is an internal running-permit seam; public recovery authorization is M5.
- config/runner contains real synchronous localhost playbooks and an Ansible Runner image context.
  Runner uses a complete version lock, file-mounted secrets and a clean environment; rc/status/stdout/
  job_events/command stay on PVC. Full content scans include command, not only stdout or filenames.
  Successful focused artifact survival is recorded; final acceptance depends on the cumulative gates.
  Job backoffLimit=0 reduces overlapping retry layers but Kubernetes can still start a Job more than once.

Document an adapter's controlled references, immutable artifact/digest, terminal status, cancellation,
safe retry, output schema, secret redaction, artifact storage and compensation capability. Introduce new
protocol/node types only with explicit DefinitionRules/schema/version changes. Do not allow route
fields to choose arbitrary URLs, headers, namespaces, images, commands or filesystem paths.

Keep DevelopmentAdapter and crash barriers behind engine-development. AdapterCrashHook is a test-only
barrier after real I/O and before saving its result; it is not a runtime durability mechanism.
M4 behavioral sources are RestAdapterTest, RestEngineAcceptance, KubernetesAcceptance, AdapterBoundaryAcceptance,
scripts/adapter_fixture.py and scripts/adapter_processes.py. Their explicit *Acceptance names are
invoked with -Dit.test; they are not silently included in an earlier phase's DB-only suite.
Run the full implemented cumulative gate, not only these focused cases, before acceptance.

The controlled catalog is selected by ROUTE_ADAPTERS_CONFIG at process startup. endpoints map a ref to
baseUri/allowedHost/query/cancel/timeoutMillis/maxResponseBytes and optional credentialRef; credentials
map ref to a readable bearer-token file. HTTPS uses standard certificate/hostname verification; only
explicit loopback test HTTP is allowed. No redirect forwards Authorization. Startup errors and adapter
exceptions are sanitized and never print tokens or raw remote response bodies.

resources map a ref to namespace, runId, immutable image, kind (DEPLOYMENT/JOB/ANSIBLE), plus Runner
pvc/playbook/artifactDigest/optional secretName. kubernetes requires explicit kubeconfig and context.
ANSIBLE currently permits the packaged probe/wait/fail localhost playbooks only. Changing these
deployment-owned templates requires a new image digest and acceptance evidence, not a route override.
See the actual generated adapter-catalog.json in M4 integration evidence for the complete nonsecret
test configuration; it is not a production credential or deployment configuration.

For extensions, add a failing behavior case to the actual fixture suite, persist any new intent fields
before first I/O, preserve unknown/restart/cancel semantics, and update scripts/adapter_gate.py proof
validation. Never replace real DB/kind/Runner with mocks or count unselected stale target XML as proof.

V6 publication requires a nonempty immutable binding for every typed activity, rollback and notification
ref. The default binding method rejects unversioned adapters. Include every semantically relevant
configuration in the binding; use nonsecret hashes/reference names for sensitive configuration.
Kubernetes adds explicit targetHash as well as image/playbook/artifact metadata. Already-published and
queued versions cannot silently adopt changed catalog semantics; runtime checks drift before I/O and
retains an IN_DOUBT permit. Missing legacy bindings are not reconstructed. Publish a new version for
changed behavior. See ADR0009 and its actual MariaDB/HTTP restart and mutation regressions.
REST safeOutput recursively checks decoded text and field names, plus the JSON representation of each
nontext scalar (numbers, booleans and null), against the actual configured credential. This is the same
scalar form canonical persistence emits; numeric source lexemes may normalize (1e2 becomes100.0).
Serialized-container-only comparison is insufficient for escaped strings. Text-only traversal is also
insufficient. Legitimate nonsecret scalars retain their type/value; credentials are not restricted to
hide a missing comparison. Reject unsafe output before DB/downstream use and return sanitized UNKNOWN.

M5 compensation calls the same OperationAdapter contract with direction ROLLBACK and a distinct operation/step identity. Transport observation keeps that identity; human/business retry advances operation_generation. RecoveryPolicy captures rollback input before forward submit. Add actual rollback failure/retry/cancel and old-callback tests to RecoveryIT and recovery_processes.py; never call an adapter in a recovery transaction.
