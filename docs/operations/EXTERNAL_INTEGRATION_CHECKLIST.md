# External integration boundary

EXTERNAL_ACCEPTANCE=NOT_RUN. PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED.

Five examples in examples/delivery are explicitly DEMO synthetic fixtures. They cover REST, typed condition, ALL_SETTLED parallel, actual Ansible Runner and Kubernetes rollout; they are not the five enterprise pipelines.

| Missing enterprise input | Required external review | Status |
|---|---|---|
| Five real route definitions and owners | Map each input/output, rollback and manual boundary | EXTERNAL_NOT_RUN |
| REST endpoints and operation protocol | Verify TLS, identity/dedupe/query/cancel and error outcomes | EXTERNAL_NOT_RUN |
| Existing NATS HTTP gateway | Confirm bounded failure notification protocol | EXTERNAL_NOT_RUN |
| VM inventory, playbooks and credentials | Validate immutable artifacts, scoped secret files and all remote work convergence | EXTERNAL_NOT_RUN |
| Production Kubernetes context/namespaces | Review exact RBAC, PVC, image registry and retention | EXTERNAL_NOT_RUN |
| Identity and token distribution | Issue high-entropy principal tokens, restrict hash configuration and rotation | EXTERNAL_NOT_RUN |
| Database/PVC backup and recovery objectives | Restore rehearsal under approved enterprise controls | EXTERNAL_NOT_RUN |

These inputs are not needed to run isolated engineering tests. They must be supplied and separately authorized before claiming enterprise integration or deploying. Engineering evidence does not certify exactly-once external effects, a six-hour wall-clock soak, independent security approval or production readiness.
