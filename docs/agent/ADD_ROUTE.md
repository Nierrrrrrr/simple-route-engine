# Add a DEMO route with existing nodes (M3)

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
