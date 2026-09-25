# DSL v1 with M4 controlled adapters

The [JSON Schema](schema.json) and [OpenAPI](../api/openapi.yaml) describe the wire shape.
registry.DefinitionRules performs additional graph, scope, type and bound checks at draft/edit/publish;
admission also validates the selected definition and declared input. All failures are sanitized 422.

A definition requires routeId, version and string versions dslVersion=1, engineSemanticsVersion=1,
adapterContractVersion=1, plus a SEQUENCE root. Optional inputSchema declares a nonsecret object shape.
IDs match [A-Za-z][A-Za-z0-9_-]{0,127} and are globally unique, including rollback nodes.
Maximum definition size is 262144 UTF-8 bytes, 100 nodes, structural depth 20, parallel depth one,
and 1–10 branches per PARALLEL. Unknown nodes/fields, cycles/goto, forward/self references and
cross-branch dependencies reject. There is no eval, script or loop.

SEQUENCE has children in execution order; an empty sequence safely succeeds.
PARALLEL requires join=ALL_SETTLED and branches; every branch has its own persisted state/output.
Container outputs map direct child IDs to their outputs, and a parallel output appears only after join.
One route permit covers all branches. A final branch failure stops future forward nodes while already
started work converges; successful branch results stay intact across another branch's automatic retry.

CONDITION requires condition, then and else nodes. The chosen arm is saved in branch_choice before
dispatch. Any node may use when. A false when records false and SKIPPED without an attempt.
The expression format is {"field":"steps.prepare.ready","operator":"EQ","value":true}.
Operators are EQ/NE/LT/LE/GT/GE/EXISTS. LT/LE/GT/GE require number/integer shapes.
EXISTS omits value; other operators require a matching string/boolean/number/integer value.
References address input.field or steps.node.field (further object fields are permitted).
Only declared, prior settled outputs in the same branch scope are available. An unconditional binding
or comparison requires every property along the path to be required. EXISTS can inspect optional fields.
A conditional arm or when output is not guaranteed and cannot supply an unconditional later binding.

Value schemas support {} (untyped, no typed references), object, string, boolean, number and integer.
Object shapes allow properties, unique required property names and boolean additionalProperties.
No arbitrary JSON Schema evaluator or code runs. Required names must exist in properties.
Activity input is an object of literals, nested values or {"$ref":"steps.prepare.value"} bindings.
Resolved input is saved before first submit and reused on retry. Output must match outputSchema.
Secret values are outside this DSL contract; credentialRef is a name, never an embedded credential.

Activity types REST/KUBERNETES/ANSIBLE require endpointRef/resourceRef/playbookRef respectively.
References and credentialRef match [A-Za-z][A-Za-z0-9_.-]{0,127}; artifactDigest is sha256 plus 64 lowercase
hex characters. input/outputSchema/artifactDigest/credentialRef/retry/rollback/onFailure are optional.
M4 registers RestAdapter for endpointRef and KubernetesAdapter for resourceRef/playbookRef. The
deployment-owned catalog selects actual targets; routes cannot supply URLs, namespaces, images,
commands, playbook paths or environment variables. The default empty catalog safely rejects unknown
references before I/O. DevelopmentAdapter requires the explicit engine-development profile.

retry requires maxAttempts 1–100, maxElapsedSeconds 1–604800 and backoffSeconds 0–86400.
Optional maxBackoffSeconds is 0–86400 and at least backoffSeconds. Default policy is one attempt,
21600 seconds elapsed, one-second initial backoff, cap max(initial,60). Exponential delays are capped.
No attempt begins at or after the elapsed deadline. Retry state, policy, first_attempt_at, attempt_count
and next_action_at persist; waits retain the permit. Only known retryable failure permits a new operation.
Transport observation keeps the existing operation identity; UNKNOWN never permits a new submit.

onFailure is {"endpointRef":"registered-name","maxAttempts":2}; maximum attempts is 1–10.
It creates an isolated notification with a 60-second elapsed budget and one-second initial delay.
Notifications cannot recursively notify, do not overwrite the primary incident, and must settle before
permit release. M4 uses an actual HTTP gateway fixture for the existing NATS integration contract; it
does not add a broker. Pending notices stop on running cancellation; started notices still converge.

rollback may contain one activity with its own unique ID, ref, input/outputSchema/retry and when.
It cannot contain structures, nested rollback or onFailure. M3 validates and retains this definition
but does not execute operator compensation; M5 implements the guarded recovery transition.
M5 implements RETRY/SKIP/ROLLBACK/CANCEL and evidence-based exact-operation resolution.
The internal M4 running-cancel seam is exercised directly by integration tests, not exposed as an API.

Example body for a draft version (the dev adapter requires the explicit test profile):

```json
{
  "routeId":"demo-two-steps","version":1,
  "dslVersion":"1","engineSemanticsVersion":"1","adapterContractVersion":"1",
  "root":{"id":"root","type":"SEQUENCE","children":[
    {"id":"prepare","type":"REST","endpointRef":"dev.success","input":{"ready":true},
     "outputSchema":{"type":"object","properties":{"ready":{"type":"boolean"}},"required":["ready"]}},
    {"id":"check","type":"CONDITION",
     "condition":{"field":"steps.prepare.ready","operator":"EQ","value":true},
     "then":{"id":"yes","type":"REST","endpointRef":"dev.success"},
     "else":{"id":"no","type":"REST","endpointRef":"dev.success"}}
  ]}
}
```

The original enterprise routes were not supplied. All executable examples are DEMO;
EXTERNAL_ACCEPTANCE=NOT_RUN and PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED.

Publication validates that each ref exists in the loaded catalog with the correct kind, including
rollback/onFailure refs. ANSIBLE requires an ANSIBLE entry; KUBERNETES requires DEPLOYMENT or JOB;
onFailure requires REST. Unknown/cross-kind refs leave the version DRAFT with a validation error.
The published V6 binding includes deployment-owned artifact semantics even when artifactDigest is
omitted from the DSL. Old queued or retrying versions never switch silently after catalog changes;
they fail closed with held permit. Publish a new version to adopt changed behavior. Development refs
are limited to the explicit development adapter and are rejected without its profile. The illustrative
examples/demo-foundation.json needs a registered demo-fixture endpoint before publication.

M5 compensation input contract: rollback remains a declared leaf with its own immutable adapter binding and bounded retry configuration. Its input may bind route input and already settled prior outputs permitted by DefinitionRules; it cannot refer to its own forward output or arbitrary later steps. EngineService captures these nonsecret resolved inputs in rollback_input_json before the forward submit. The original forward input/output and attempt history stay on the original step; compensation never rewrites them. Missing captured context rejects rollback. SKIP supplies the declared forward output schema, including required typed values; forbidden secret field names are rejected recursively.

M5 rollback when uses the same permitted immutable context as its captured input; rollback_allowed is saved before forward submission. A false/missing captured guard rejects ROLLBACK with422 and leaves its current incident unchanged. STOPPED confirmation offers RETRY/CANCEL. After a successful forward recovery with no other failed operation, never-dispatched stopped nodes reopen; already successful steps/condition choices remain unchanged.
