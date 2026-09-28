# Add a DEMO route with existing nodes

Use examples/demo-engine.json and the [DSL](../routes/DSL_REFERENCE.md) without changing Java.
For this dev.* fixture example, start the isolated configured app with SPRING_PROFILES_ACTIVE=engine-development
and ROUTE_ENGINE_FIXTURE_DIRECTORY set to a run-owned directory. All database/auth settings still come
from the isolated fixture environment. Never point it at production or put real credentials in examples.
Set BASE to the local URL and TOKEN to the generated token, then run:

    curl --fail-with-body -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"routeId":"demo-engine","name":"DEMO durable engine"}' "$BASE/routes"
    curl --fail-with-body -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' --data-binary @examples/demo-engine.json "$BASE/routes/demo-engine/versions"
    curl --fail-with-body -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"stateVersion":0}' "$BASE/routes/demo-engine/versions/1/publish"
    curl --fail-with-body -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -H 'Idempotency-Key: demo-engine-001' -d '{"routeId":"demo-engine","priority":"NORMAL","admissionMode":"QUEUE","input":{}}' "$BASE/executions"

Read executionId from the202 response and GET $BASE/executions/$EXECUTION_ID with the same bearer token.
The initial decision is immutable; the execution snapshot progresses to SUCCEEDED with permitHeld=false.
Preserve the key after503/response loss; GET admission-requests?key=demo-engine-001 retrieves its decision.
Draft/edit/publish validate finite bounds and typed dependencies; execution admission binds the exact
published version and validates inputSchema. New existing-node routes need no Java change/redeployment.

This is an executable development example, not the FINAL independent sixth-route handoff exercise.
Actual REST/Kubernetes/Ansible integrations are M4, recovery is M5, enterprise endpoints are NOT_RUN.

Before publishing a real adapter example, configure its controlled catalog refs. Publication validates
ref existence/kind and freezes artifact/target semantics. examples/demo-foundation.json is illustrative
and needs a demo-fixture REST catalog entry; examples/demo-engine.json uses only explicit dev.* refs.
Neither example enables a general missing-adapter fallback. See ADR0009 for queued version behavior.

Routes using only existing leaf types need no Java changes. To offer compensation, declare rollback in the leaf, keep its ID globally unique and its inputs limited to input/prior settled output references. Failed-route recovery is available through RUNBOOK incident discovery and M5 APIs.


## Delivery examples and a sixth pure-configuration route

Use examples/delivery/demo-1.json through demo-5.json for real controlled REST/condition/parallel/Ansible/Kubernetes catalog references. Each file wraps name, definition and input. Configure the catalog before publication; use only refs available in that deployment. Ansible uses playbookRef, Kubernetes resourceRef and REST endpointRef. No Java or redeployment is required for a new combination of existing nodes.

For an already configured isolated fixture API, set ROUTE_DEMO_BASE to its actual loopback URL and ROUTE_DEMO_TOKEN to its synthetic token, then run python3 -B scripts/publish-demo.py YOUR_CONFIG. The helper creates/drafts/publishes/submits and requires SUCCEEDED within180seconds. Admission must be enabled. Preserve all five originals.

## FINAL fresh-agent exercise

Only a NEW acceptance agent performs this after Builder freeze. Read this document, DSL_REFERENCE and the five examples independently. Author one new DEMO using existing node capabilities; choose its content and unique demo-* routeId yourself, different from demo-delivery-1 through5. Do not change any Java, published source example, script or documentation. Create the JSON wrapper with name starting DEMO, definition (version1 and supported DSL/engine/adapter versions), and input. Keep the authored file under the run-owned evidence directory, outside the sealed execution subdirectory. Do not copy a Builder-authored sixth route; none is provided.

Available isolated catalog: REST sync/async/lost/unsafe/timeout/failure/flaky and bounded notification refs; Successful async and notify-async fixture operations return202 WAITING, and FINAL alone completes them through real HTTP /complete/<operationId> only after an actual engine GET has observed202 WAITING. A later engine GET must observe200 SUCCEEDED before the route succeeds. The lifecycle response trace is retained in async-lifecycle.json and validated; no DB state is forced. Fault refs lost/unsafe/timeout/failure/flaky and notification-failure refs preserve their normal adverse behavior and are not auto-completed. Shared M4/M5 crash fixtures still require their explicit completion controls. Actual Kubernetes resourceRef job/deployment and Ansible playbookRef runner (the underlying allowlisted playbook is probe) are configured by the helper with the genuine pinned Runner image, isolated namespace/PVC and synthetic credentials. Existing delivery examples and DSL_REFERENCE specify exact node shapes. The helper does not supply missing config fields or alter your content.

Use the preflight-ready run from STATE. For this candidate:

    export ROUTE_RUN_ID=final-20260926-d831
    export PYTHONDONTWRITEBYTECODE=1
    source scripts/env.sh
    export ROUTE_SOURCE_FINGERPRINT="$(python3 -B -c 'import json,os; print(json.load(open(".evidence/desktop/"+os.environ["ROUTE_RUN_ID"]+"/FINAL/round-3/candidate-freeze.json"))["source_fingerprint"])')"
    mkdir -p .evidence/desktop/$ROUTE_RUN_ID/FINAL/round-3/handoff-agent-1

Now author your own demo6.json in that parent directory. Then execute:

    python3 -B scripts/final_handoff.py .evidence/desktop/$ROUTE_RUN_ID/FINAL/round-3/handoff-agent-1/demo6.json .evidence/desktop/$ROUTE_RUN_ID/FINAL/round-3/handoff-agent-1/execution

The tool performs a clean package build (mandatory test execution belongs to the later cumulative gate), checks all engine Java against the controller baseline, starts a new real MariaDB and a live engine/scheduler with run-local auth/catalog, and configures admission. It publishes and executes your exact config through scripts/publish-demo.py, then all five unchanged delivery examples in that isolated database/namespace. Each must be terminal SUCCEEDED with permit released; a same live JVM and distinct execution IDs are recorded. The helper saves actual JAR/source/Java/example/config hashes, original API traces, stdout, commands/exits and six JUnit cases. Synthetic tokens stay in the process environment/private .local fixture files and are not printed in traces. Cleanup checks run ownership before deleting only its test resources.

On success, execution/handoff-proof.json seals every file in execution/. Do not add notes, edit fixtures or write your agent result inside that sealed subdirectory afterwards. Put notes/agent-result.json beside execution/ instead. Report the original evidence path and any documentation gap to the controller. A failure is not acceptance; retain raw evidence and do not silently edit source or resubmit unknown external work. Any needed source correction requires a new candidate and another fresh agent.

The controller, not this script or the fresh agent, records platform-derived task identity and call number in a receipt outside execution/. Receipt exact keys: schema_version=1, role=FRESH_ACCEPTANCE, agent_id, agent_call_number, run_id, source_fingerprint, proof_sha256 (original handoff-proof.json), evidence_directory (repository-relative execution path). It must identify a call later than the Builder checkpoint. The separate FINAL gate takes ROUTE_FINAL_HANDOFF and ROUTE_FINAL_HANDOFF_RECEIPT, checks all source/hash/path/case constraints and imports the original execution transparently. Context freshness is assessed using controller platform records and the independent Reviewer; a script cannot prove it.
The local demo helper accepts only parsed http://127.0.0.1:<port> origins without userinfo, path, query or fragment, and refuses redirects before forwarding credentials. Use synthetic local fixture credentials.

For FINAL round3, the controller must first create the immutable security-repair Java baseline selected by STATE.final_java_baseline. This baseline incorporates the AC-041 pre-persistence repair; do not modify Java during the fresh configuration exercise. Use round-3/candidate-freeze.json and round-3/handoff-agent-1 only. The controller receipt is round-3/fresh-handoff-receipt.json.
