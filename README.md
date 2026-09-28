# Route Engine

Java 21 / Spring Boot modular monolith with MariaDB/InnoDB as the durable business state store.
Current delivery is **FINAL candidate, pending fresh handoff, full gate and fresh review**. Registry, durable admission/execution, real REST/Kubernetes/Ansible adapters, recovery and hardening were accepted through M6 on predecessor source6ce81e55b80c37c44361c3faefee7b1163f075b38d8be89d62f19232b621a512 (369 cases,32 reports,58 checks). The user now authorizes FINAL preparation and acceptance. This candidate requires its own frozen-source evidence; no FINAL result is claimed here.

| Delivery scope | Value |
|---|---|
| Candidate phase | FINAL |
| Accepted phases | M0, M1, M2, M3, M4, M5, M6 |
| Executable gates | M0, M1, M2, M3, M4, M5, M6, FINAL |
| Deferred gates | None |
| Delivery examples | 5 |

No production deployment is authorized.

Read [handoff](docs/agent/HANDOFF.md), [architecture](docs/architecture/OVERVIEW.md),
[API](docs/api/openapi.yaml) and [testing](docs/agent/TESTING.md).
The fixed baseline is [the architecture contract](ai-kit/ARCHITECTURE_CONTRACT.md).

From this checkout in WSL2 Ubuntu (Linux x86_64):

```bash
export ROUTE_RUN_ID=final-20260926-d831
export PYTHONDONTWRITEBYTECODE=1
bash scripts/bootstrap-tools.sh
source scripts/env.sh
export ROUTE_FINAL_HANDOFF=.evidence/desktop/$ROUTE_RUN_ID/FINAL/round-3/handoff-agent-1/execution
export ROUTE_FINAL_HANDOFF_RECEIPT=.evidence/desktop/$ROUTE_RUN_ID/FINAL/round-3/fresh-handoff-receipt.json
bash scripts/verify-desktop-phase.sh FINAL .evidence/desktop/$ROUTE_RUN_ID/FINAL/recheck-unique
```

The cumulative gate builds with the official Maven Wrapper, starts a digest-pinned isolated MariaDB,
runs unit and real HTTP/database tests, then launches the packaged app via scripts/local-run.sh.
It restarts the actual database and starts a second app process to prove persistence. It removes
only its own labelled resources afterwards. M4 additionally builds the pinned Runner context, loads its
immutable digest into the dedicated kind cluster, runs real Deployment/Job/Runner and crash cases, and
reads all PVC artifacts after deleting the original completed Runner Pod. Use a new evidence directory
for each run. Missing tools, actual reports, artifact contents or build proofs fail closed.

For an already configured isolated database, set ROUTE_DB_URL, ROUTE_DB_USER, ROUTE_DB_PASSWORD,
ROUTE_ADMIN_TOKEN_SHA256 and optionally ROUTE_PORT, then run `bash scripts/local-run.sh`.
No default credential exists. The app binds 127.0.0.1; never point these commands at production.

Tools/caches live in .tools/.cache. Docker Desktop must expose Linux containers to this WSL distribution.
The doctor uses only the run-specific kind cluster and kubeconfig. The five examples/delivery/demo-*.json scenarios are clearly labelled DEMO and cover REST, condition,
parallel, Ansible and Kubernetes. All five passed real publish/execute checks in the accepted M6 gate;
the current candidate must pass its own frozen gate and fresh review. Enterprise endpoints/credentials are EXTERNAL_NOT_RUN.
ENGINEERING_ACCEPTANCE=NOT_PASS; EXTERNAL_ACCEPTANCE=NOT_RUN; PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED.

Engine scanner is enabled by default with4 workers and queue capacity16. Admission-only tests disable it.
Development fixtures require the explicit engine-development profile and a run-owned fixture directory.
Default runtime has no development adapter/hook; unregistered refs fail safely before I/O.
See the [DSL](docs/routes/DSL_REFERENCE.md) and [adapter seam](docs/agent/ADD_ADAPTER.md).

Published versions bind controlled adapter artifact and target semantics before queueing. Catalog drift
blocks older queued/retry work safely; publish a new version for changed behavior. Missing/cross-kind
refs fail publication. See [publication bindings](docs/adr/0009-published-adapter-bindings.md).

FINAL entry: `bash scripts/ci.sh` after configuring the isolated tools and ROUTE_RUN_ID. Read [deployment](docs/operations/DEPLOYMENT.md), [security](docs/operations/SECURITY.md), [handoff](docs/agent/HANDOFF.md) and [external checklist](docs/operations/EXTERNAL_INTEGRATION_CHECKLIST.md). Five examples are in examples/delivery. FINAL is authorized; production deployment is not. Read ADD_ROUTE for the fresh-agent prerequisite before running FINAL.
