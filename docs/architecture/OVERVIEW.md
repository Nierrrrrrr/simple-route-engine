# Module map

One Java 21 Spring Boot application; MariaDB/InnoDB is the sole durable state source.
Implemented root is `dev.routeengine`: RouteEngineApplication, api.RouteController/ApiErrors/RequestSecurityFilter/UnavailableController, registry.RouteRegistry/DefinitionRules, and audit.AuditLog. M2 adds api.AdmissionController and admission.AdmissionService/AdmissionScheduler. M3 adds engine.EngineService/EngineScheduler, OperationAdapter and explicit development-profile fixtures; M4 adds adapters.AdapterCatalog/RestAdapter/KubernetesAdapter and real Runner Jobs. Operator recovery is implemented by recovery.RecoveryPolicy/OperatorService.

| Module | Responsibility | Allowed collaborator |
|---|---|---|
| `api` | principal, schema, idempotency identity, status/error mapping | application services |
| `registry` | route, immutable published version, semantic compatibility | JDBC registry, validator |
| `admission` | pool lock, CRITICAL/FIFO/WRR, acquire/release/config | database transactions |
| `engine` | node transitions, retry due times, persisted decisions/branch outputs | adapter contracts, stores |
| `adapters` | submit/observe/cancel with stable external identity | controlled HTTP/Kubernetes endpoints |
| `reconcile` | durable due work and unknown operations; no blind resubmit | engine and adapters |
| `audit` | append events in the state transaction; bounded redacted observability | JDBC |

Flow: Control API → short MariaDB command transaction → DB due-work scan → lease/intent transaction
→ external adapter I/O outside transaction → result/next-work/event transaction.
Restart scans durable rows; no in-memory-only queue. Parallel branches share one permit and isolate outputs.
One replica/Recreate is an operational default, never the concurrency correctness argument.

Runtime services: Spring Boot, MariaDB, existing Kubernetes. Ansible Runner is an on-demand Job;
NATS notification uses an existing HTTP gateway. No Redis, broker, workflow server or leader-election service.
Local kind/Testcontainers/HTTP fixtures are test tools and do not alter production dependencies.

Defaults are [machine-readable](../../config/defaults.json): T=100, R=20, H:N:L=6:3:1.
U is all held permits; N is non-CRITICAL held permits. U<=T and N<=T-R always.
Critical may consume shared capacity; pending critical has strict priority without preemption.
Noncritical HHHHHHNNNL cursor persists, advances only on admission, skips empty classes, has no accumulating credit.
Only a weight change resets cursor to zero under the same pool transaction and audit; capacity or pause changes preserve it.

See [states](STATE_MACHINES.md), [transactions](TRANSACTIONS.md),
[failure recovery](FAILURE_RECOVERY.md), [dependency inventory](../adr/0001-stack.md).

EngineService performs bounded tree advancement and reconciliation against step_runs/step_attempts.
EngineScheduler owns no durable continuation. Defaults: workers4, queue16, scan100ms, lease30s, poll1s.
The file fixture is only a test external system, not a production runtime dependency.

Engine writes acquire pool -> execution -> existing incidents -> step/attempt through the common
EngineService execution-lock entrance. This includes claim, completion and budget-failure paths; see
ADR0007 and TRANSACTIONS for new incident insertion/FK semantics. Global pool serialization does not
substitute for the fixed lock order.

M4 publication now freezes adapter semantics in immutable V6 version bindings, before QUEUE or a
first worker claim. AdapterBindings validates typed refs including rollback and notification. Missing
or drifted bindings block I/O and retain IN_DOUBT permits; new versions adopt changed catalogs.
Kubernetes bindings include the explicit parsed target context/digest. REST output checks decoded
text/field names and persisted number/boolean/null representations before persistence. See [ADR0009](../adr/0009-published-adapter-bindings.md).

M5 adds recovery.RecoveryPolicy and OperatorService plus api.RecoveryController. Shared admission remains in AdmissionService; EngineService owns all external transitions, compensation dispatch and fenced operator confirmations. MariaDB remains the only durable queue. No new runtime service is introduced. Actual M5 gates are scripts/recovery_gate.py and recovery_processes.py; M6 adds role authorization, ClaimLifecycle and operations.EngineMetrics; current acceptance status is in STATE/HANDOFF, and FINAL is the current authorized candidate phase; acceptance still requires its own fresh handoff, full gate and review.

M6 adds only Spring/JDBC code and additive V8 indexes. No runtime dependency was added. RequestSecurityFilter authorizes role routes; ClaimLifecycle gates process intake only, while MariaDB remains the cross-process correctness boundary. EngineMetrics reads aggregate SQL on demand. See operations/SECURITY and DEPLOYMENT for fixed images and persistent storage.

FINAL round3 extends credential pre-persistence guards to initial admission key/requestId and affected route/version mutation envelopes. Context preparation reads only relevant credentials outside transactions; immutable snapshots are checked under existing locks. Detected unsafe request IDs are replaced in error bodies and response headers. See SECURITY.md and HANDOFF.md for historical fail-closed handling and the new round3 Java baseline/fresh-agent boundary.
