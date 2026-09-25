# Route Engine

Java 21 / Spring Boot modular monolith with MariaDB/InnoDB as the durable business state store.
Current delivery is **M4 round4 CANDIDATE, NEEDS_FRESH_REVIEW**: registry, durable admission/execution,
controlled REST and Kubernetes adapters, synchronous Ansible Runner Jobs and persistent artifacts.
M0-M3 were accepted by the desktop controller; M4 requires its frozen builder/controller gates and fresh
review. Operator recovery remains M5. Current gate results live in the handoff evidence directories.
No production deployment is authorized.

Read [handoff](docs/agent/HANDOFF.md), [architecture](docs/architecture/OVERVIEW.md),
[API](docs/api/openapi.yaml) and [testing](docs/agent/TESTING.md).
The fixed baseline is [the architecture contract](ai-kit/ARCHITECTURE_CONTRACT.md).

From this checkout in WSL2 Ubuntu (Linux x86_64):

```bash
export ROUTE_RUN_ID=desktop-20260924T212931Z
export PYTHONDONTWRITEBYTECODE=1
bash scripts/bootstrap-tools.sh
source scripts/env.sh
bash scripts/verify-desktop-phase.sh M4 .evidence/desktop/$ROUTE_RUN_ID/M4/recheck-unique
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
The doctor uses only the run-specific kind cluster and kubeconfig. The M1 example is clearly DEMO;
five full enterprise-independent scenarios remain future work. Enterprise endpoints/credentials are EXTERNAL_NOT_RUN.
ENGINEERING_ACCEPTANCE=NOT_PASS; EXTERNAL_ACCEPTANCE=NOT_RUN; PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED.

Engine scanner is enabled by default with4 workers and queue capacity16. Admission-only tests disable it.
Development fixtures require the explicit engine-development profile and a run-owned fixture directory.
Default runtime has no development adapter/hook; unregistered refs fail safely before I/O.
See the [DSL](docs/routes/DSL_REFERENCE.md) and [adapter seam](docs/agent/ADD_ADAPTER.md).

Published versions bind controlled adapter artifact and target semantics before queueing. Catalog drift
blocks older queued/retry work safely; publish a new version for changed behavior. Missing/cross-kind
refs fail publication. See [publication bindings](docs/adr/0009-published-adapter-bindings.md).
