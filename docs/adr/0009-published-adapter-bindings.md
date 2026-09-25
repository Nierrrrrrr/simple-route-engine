# ADR 0009: publication binds adapter semantics

Status: M4 round3 candidate / NEEDS_FRESH_REVIEW. This corrects the round2 independent review.

Version-level adapter semantics must exist before admission or first claim. V6 adds nullable
route_versions.adapter_bindings; V1-V5 are unchanged. Publication walks the validated finite tree,
including both conditional arms, parallel branches, rollback and onFailure refs. Exactly one registered
adapter must support each typed ref. Its pure binding reads already-loaded local configuration only.
The binding and PUBLISHED transition commit together with the route default and audit. The existing
published-row UPDATE/DELETE guards protect the new column too; actual MariaDB mutation tests require
SQLSTATE45000 and byte-identical original values after two rejected changes.

Bindings are keyed by node type and ref, with contract1. REST binds the complete controlled endpoint
entry by catalogHash. Kubernetes binds that hash plus kind, namespace, immutable image, targetHash and,
for ANSIBLE, packaged playbook and artifactDigest. Hashes include every resource/endpoint option,
including run ownership, PVC and secret reference names. Credential values do not enter the binding.
The explicit Kubernetes context and kubeconfig content digest form targetHash. At startup the exact
file is parsed with Fabric8's Config.fromKubeconfig(context, File), whose pinned implementation starts
from Config.empty; its bytes are checked unchanged across parsing. Each client uses a copy of that
parsed snapshot. Publication, plan and claim never read kubeconfig, credentials or the network.
Changing inline kubeconfig credentials also conservatively changes targetHash; no old binding is
silently rewritten. REST credential-file value rotation preserves its controlled reference.

Claim compares the immutable version binding with the registered adapter's current binding before
planning any new attempt. A missing/changed binding yields a durable bindingUnavailable marker and
UNKNOWN without adapter I/O, retaining permit and an IN_DOUBT incident. Business retry has the same
check. Reclaim preserves the original durable plan and operation identity; a drifted current catalog
suppresses I/O without replacing that saved plan. Restoring the original catalog allows observation of
an existing saved operation. A never-submitted blocked attempt is not automatically submitted later;
its conservative unknown marker awaits audited resolution (M5). A new published version deliberately
adopts the current binding. This chooses fail-closed availability over guessing old artifact behavior.

Legacy published versions receive NULL, never an inferred binding from today's configuration. Legacy
activity work therefore fails closed; purely structural definitions still advance. History tests retain
all earlier incident/audit/plan assertions and prove the migration leaves historical bindings NULL.
DevelopmentAdapter contributes only its existing explicit dev.* REST refs and only in its development
profile. Empty SEQUENCE fixtures remain valid without any adapter/profile bypass.

Runtime supports/plan/submit independently reject missing or cross-kind references. ANSIBLE requires
kind ANSIBLE; KUBERNETES requires DEPLOYMENT or JOB. A publication error leaves the draft unchanged.
REST outputs are checked as decoded JSON text/field names and persisted JSON representations of
nontext scalars, recursively through objects and arrays before persistence. Text requires decoding to
avoid escaped-string bypass; number/boolean/null require their scalar representation, including numeric
normalization. Neither a serialized-container-only scan nor a text-only traversal is complete. Existing forbidden
secret key names, size limits, redirect refusal and full Runner PVC content checks remain.

AdapterBoundaryAcceptance runs true HTTP/MariaDB cases for plain/quote/backslash secrets, old queued
playbook/image/target changes across application-context restart, business retry drift, explicit new
version adoption, direct SQL binding immutability, and publication/runtime type validation. The full
M4 gate also retains the independent JVM/SIGKILL, real kind, Runner, cancellation and artifact suites.

Round4 corrects the independently reproduced nontext scalar gap from round3. One value-node branch
adds representation comparison without changing credential validation or legitimate scalar outputs.
The permanent true HTTP/DB matrix retains quote/backslash/key tests and adds16 cases,11 secret variants
and5 nonsecret controls. It checks DB output/input, audit payload values, captured raw response bodies,
held permit/incident and downstream dispatch. Ordinary log words such as true/false/null are not treated
as proof of secret echo; the controlled response body/operation and persisted values establish provenance.
