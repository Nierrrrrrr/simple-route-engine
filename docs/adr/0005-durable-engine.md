# ADR 0005: finite durable engine (M3)

The existing Java/JDBC/MariaDB stack and fixed safety contract remain unchanged. V3 adds node snapshots,
parent/order, retry policy/count/time, operation generation and engine_incidents; V1/V2 remain immutable.

EngineService interprets the bound published tree into step_runs. Only initialized nodes exist. SEQUENCE
initializes its next child in the transaction that commits its predecessor result. CONDITION/when choices
are stored once. PARALLEL initializes each branch independently; branch outputs remain on their rows and
the container merges keyed outputs only at ALL_SETTLED. Successful siblings are never reinitialized.

All engine mutations take the pool row, then execution, existing incidents, then steps/attempts (ADR0007). This deliberately serializes short
metadata work and coordinates with AdmissionService.stop; no adapter I/O, development hook or waiting
occurs in a transaction. No separate queue service, replay interpreter or JVM correctness lock is added.
The bounded worker pool is scheduling capacity only, not route admission capacity.

Each new business attempt gets a distinct operation ID and operation_generation. Observing an existing
operation retains both, while claiming it advances lease_generation. permit_generation stays independent.
DB UTC clock controls leases/polling; java.time.Clock controls retry domain budgets. JDBC DATETIME values
use explicit UTC LocalDateTime, avoiding default JVM timezone conversion. Six-hour tests change only the
injected Clock; they are not a soak and never change the OS/DB clock.

Lease expiry and unknown results only observe the original operation. Missing identity after a committed
intent is UNKNOWN, even if the process may have died before submit. A stale worker cannot commit and is
rechecked before I/O; DB fencing cannot revoke I/O already sent. Unknown retains the route permit.
A terminal observation resolves its existing IN_DOUBT incident with result, next pending work and audit
in one transaction. Known failures pause new forward work; initialized external operations and bounded
notifications must converge before MANUAL_WAIT and permit release.

Typed references use declared JSON value shapes. Unconditional bindings and ordinary comparisons require
every path component to be declared required. EXISTS may inspect optional declared fields. Cross-branch,
forward, self, skipped/conditional-arm and undeclared output dependencies are rejected. This avoids
null substitution and routes that become permanently stuck waiting for a value that may never exist.

DevelopmentAdapter and DevelopmentCrashHook exist only under explicit engine-development profile.
References are a fixed dev.* allowlist; a route cannot supply a file path. The operator-configured base
is a run-owned fixture directory in acceptance. Files model a remote fixture, not production state.
Hook .armed gates claims before completion; .reached proves completion committed; it waits outside the
transaction. Default runtime has no fixture adapter/hook. Unregistered adapters fail safely before I/O.
M4 supplies actual REST/Kubernetes/Ansible/notification integrations. M5 supplies operator recovery APIs.

Compatibility changes: admission/foundation suites explicitly disable the scanner; their original
admission assertions remain. Migration assertion is exact [1,2,3,4]; V4 and test DB isolation are documented in ADR0006. M3 process suites enable real scanners
and independent JVMs. Existing safe SEQUENCE/activity snapshots remain valid. No fixed ai-kit changes.