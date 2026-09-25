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

The API currently uses the configured admin bearer hash and constant-time matching established in M1.
M5 operator identity comes from the authenticated local-admin bearer context. Fine-grained caller/operator/admin separation and full deployment hardening remain M6.
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
