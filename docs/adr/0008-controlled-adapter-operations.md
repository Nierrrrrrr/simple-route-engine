# ADR 0008: controlled adapter plans and external identities

Status: M4 candidate, NEEDS_FRESH_REVIEW; not yet accepted.
The fixed architecture and external safety semantics are unchanged.

V5 adds adapter_plan to step_attempts, cancel_requested to executions, and adapter_stops for durable
per-operation resource stop intent. Existing migrations V1-V4 stay byte-for-byte unchanged. Old attempts
retain null plans; EngineHistoryIT preserves all prior incident/audit assertions and adds null-plan and
default-cancellation checks. FoundationIT now requires versions1..6 (V6 publication binding is specified in ADR0009) while retaining all prior assertions.
The full M4 gate reruns these historical compatibility checks on fresh real MariaDB databases.

Plan construction reads only the catalog object loaded at startup. It records a catalog hash and stable
Kubernetes resource name/namespace before external submission. Runtime catalog drift therefore causes
UNKNOWN until an operator restores the relevant configuration; no attempt silently changes its target.
The resource name is derived from the durable operation UUID, with independently stored observed UID.
For Deployment this first controlled template contract creates an operation-owned rollout with desired
generation 1. It does not update an arbitrary pre-existing business Deployment.

REST uses a controlled JSON operation protocol. An accepted or unknown network response remains active.
Explicit operation-bound terminal status is needed for success/failure/stop. HTTP status alone is not
sufficient. Retryable terminal failure creates a new business attempt; reclaim observes the old operation.
The endpoint query capability is configured, not inferred from a timeout. Redirects are never followed,
request/response time and response bytes are bounded, and secret-bearing outputs fail closed.

Kubernetes client is fixed Fabric8 7.4.0. Config.fromKubeconfig(context, File) uses an explicit file;
requestRetryBackoffLimit is set to zero so automatic client retries do not obscure engine retry policy.
Observed resourceVersion is bound to deletion after matching operation/run labels and UID. Deletion is
normal graceful deletion, never force deletion. adapter_stops is written before deletion. The adapter
then observes the resource and every operation-labelled Pod; the first delete response returns WAITING.
This stopping contract is limited to synchronous local Pod work. Untracked remote async is unsupported.
Ansible's packaged playbooks do not expose shell, remote inventory, arbitrary playbooks or async poll:0.

The app Pod is never Job owner. Completed Runner evidence belongs on PVC storage, with only references
in DB output. Python3.12.12 base digest and every runtime package version are locked, including Runner
2.4.1/Core2.19.2. The gate hashes current context files, builds/loads the actual image and records its
immutable digest, raw build/owner/version/load commands and exits; mismatches or missing proofs fail.

Round1's real Runner rc5/read-only HOME failure is preserved. Round2 provides /tmp HOME/ANSIBLE_HOME/
local temp with nonroot/read-only root, fixed HTTP content, and secret files mounted read-only.
Runner2.4.1 writes its environment into command artifacts. An inherited-env canary demonstrated leakage
in the original image; the new entrypoint clears inherited environment before invoking Runner and the
playbook reads the secret from a file with no_log. The command artifact is retained and scanned with all
other files, never deleted or retrospectively redacted to conceal PVC persistence.
Synchronous task-start events prove work began before cancellation, followed by actual Pod convergence.
These engineering fixtures do not authorize enterprise integration or production deployment.

Official API sources consulted:
- https://raw.githubusercontent.com/fabric8io/kubernetes-client/v7.4.0/kubernetes-client-api/src/main/java/io/fabric8/kubernetes/client/Config.java
- https://raw.githubusercontent.com/fabric8io/kubernetes-client/v7.4.0/kubernetes-client/src/main/java/io/fabric8/kubernetes/client/dsl/internal/BaseOperation.java
- https://kubernetes.io/docs/concepts/workloads/controllers/job/
- https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- https://docs.ansible.com/projects/runner/en/stable/intro/
