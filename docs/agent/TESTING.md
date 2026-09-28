# Executable validation

| Delivery scope | Value |
|---|---|
| Candidate phase | FINAL |
| Accepted phases | M0, M1, M2, M3, M4, M5, M6 |
| Executable gates | M0, M1, M2, M3, M4, M5, M6, FINAL |
| Deferred gates | None |
| Delivery examples | 5 |

M0-M6 are historically accepted on their recorded source fingerprints. FINAL is a candidate until an independent fresh-agent sixth-route exercise, this full gate and a NEW readonly Reviewer pass. The current full entrypoint is below; the controller must first supply the genuine handoff directory and receipt.

Use Linux x86_64 in WSL2 Ubuntu, Python 3.12, Bash, curl and a real Linux Docker daemon.
No H2 or unavailable-Docker skip fallback exists.

```bash
export ROUTE_RUN_ID=final-20260926-d831
bash scripts/bootstrap-tools.sh
source scripts/env.sh
export ROUTE_FINAL_HANDOFF=.evidence/desktop/$ROUTE_RUN_ID/FINAL/round-3/handoff-agent-1/execution
export ROUTE_FINAL_HANDOFF_RECEIPT=.evidence/desktop/$ROUTE_RUN_ID/FINAL/round-3/fresh-handoff-receipt.json
bash scripts/verify-desktop-phase.sh FINAL .evidence/desktop/$ROUTE_RUN_ID/FINAL/recheck-unique
```

scripts/desktop_gate.py imports only protected validator functions, hashes fixed files/source before and
after execution, injects ROUTE_SOURCE_FINGERPRINT, checks actual JUnit cases and refuses existing results.
It never invokes the original pipeline main. Raw command arrays, exit codes and logs live under evidence.

scripts/foundation_gate.py first runs the complete M0 gate. LocalFixture starts an official digest-pinned
MariaDB container with labels route-engine.run-id and route-engine.purpose, a random localhost port, a fresh
schema, and generated secrets under .local. It proves the schema is empty before Flyway, executes
`./mvnw -B clean verify`, preserves unit/IT JUnit even on Maven failure, and records the dependency tree.
Failsafe explicitly uses target/classes because Spring Boot repackages the main jar.

Actual Java tests:
- src/test/java/dev/routeengine/registry/DefinitionRulesTest.java: canonical hash, supported version/identity,
  unknown fields/nodes and sanitized validation failures.
- src/test/java/dev/routeengine/FoundationIT.java: actual MariaDB/InnoDB/Flyway, live HTTP server,
  draft/publish/withdraw/soft-delete, composite FK, uniqueness, CAS, audit atomic commit/rollback,
  direct published SQL protection, requestId/UTC/validation invalid admission422 and invalid recovery422.

Direct SQL execution rows in FoundationIT are explicitly test fixtures to check immutable FK bindings.
They are not proof that M1 implements execution admission or work.

LocalFixture.smoke starts `bash scripts/local-run.sh` as an independent process, creates/publishes a
DEMO route via HTTP, stops the app, runs a real `docker restart` on its labelled database, checks its
stored hash/status, starts a second app process, and compares the complete published response.
application-*.log, raw-*-real-database-restart.*, empty-database.log and process-restart-proof.json are
the AC-006/AC-010 evidence. This also verifies the documented local startup command.
The fixture cleans only a container whose run ownership label matches, and its own .local secret directory.

For unit-only development, `./mvnw -B test` compiles/runs unit tests but is not an M1 gate.
Integration tests require generated ROUTE_DB_* and ROUTE_TEST_TOKEN from LocalFixture; missing values fail.
Use the full cumulative gate for acceptance. FINAL requires original fresh-agent handoff evidence plus the controller receipt before it runs the cumulative gate. Missing evidence fails closed.

scripts/test_gate.py retains missing/empty/skip/count-mismatch/fingerprint/AC/protected-file negative tests.
New requirement tests must be named with the AC prefix, fail when behavior is wrong, and be mapped in
TRACEABILITY. validate_m1_reports refuses absent mandatory unit, real DB integration or process coverage.
Do not weaken requirements, edit expected values to hide defects, or claim planned tests ran.

The doctor exports only the run's kubeconfig and checks ownership/Ready. It preserves this test cluster
for later stages. Cleanup of kind must first verify its node ownership and use the dedicated environment.

Docker may assign a different random published host port after restart. LocalFixture records the actual
before/after port and container ID, checks a MariaDB TCP handshake with a 20-second upper bound, then gives
the restarted app the discovered endpoint. The same container ID and stored published hash must survive.

## M1 round 2 HTTP boundary regressions

FoundationIT.AC008_scalarCoercionNeverMutatesRegistry has 21 real HTTP parameter cases across create,
route update, draft edit and publish. It rejects float/string/boolean coercion and checks complete route,
version/hash/stateVersion snapshots plus audit counts remain unchanged. AC008_frameworkClientErrorsKeepStatusHeadersAndEnvelope
has three real HTTP cases for 404/405/415, requiring the UTC/requestId envelope and the 405 Allow header.
These run in the standard M1 cumulative gate. The focused red/green loop and original reviewer replay are
retained under .evidence/desktop/desktop-20260924T212931Z/M1/round-2 as labelled diagnostic artifacts.
Before the fix the focused suite ran 26 cases with 19 failures; unchanged assertions then passed all 26.
The small existing positive API cases are included in those focused totals. No raw production data is used.

## M1 round 3 request dispatch regressions

FoundationIT.AC008_singleJsonBodyRequiredBeforeMutation sends raw HTTP strings with literal trailing
garbage or a second JSON root (10 cases over create/update/draft/edit/publish). It never re-serializes
the malformed body through a JSON node. AC008_unacceptableResponseTypeNeverMutates checks image/png
Accept on create/update/draft/edit/publish/delete/withdraw (7 cases). Both compare all persisted
route/version/audit fields and assert the sanitized requestId/UTC envelope, 422 and 406 respectively.
AC008_jsonAndWildcardAcceptCommitNormally covers application/json, application/* and */* (3 cases,
each running all 7 mutations), allowing legal trailing whitespace and requiring exactly one audit per write.

Round 3 red-1 ran 46 focused HTTP cases with 17 failures and no errors/skips; focused-green-1 passed
the same 46 cases. Previous 26 focused cases remain. The added test fragment was saved before red;
no full test-file/hash snapshot was taken at that time. All evidence is retained under M1/round-3.
The full cumulative M0–M1 gate additionally retains the genuine database restart and independent app
process proof. Diagnostic replay does not add JUnit cases or replace the gate.

## M2 cumulative gate

```bash
export ROUTE_RUN_ID=desktop-20260924T212931Z
source scripts/env.sh
bash scripts/verify-desktop-phase.sh M2 .evidence/desktop/$ROUTE_RUN_ID/M2/recheck-unique
```

scripts/admission_gate.py runs the complete M1 gate (and M0 beneath it), then creates a fresh run-owned
MariaDB and independently launches two packaged Java processes. AdmissionIT uses real DB/HTTP with
scheduled wake disabled so assertions control exact admission order. FoundationIT disables that unrelated
scheduler too; packaged process tests enable the scheduler and kill/restart it with backlog.
The 200-way tests use latches/barriers; process proof includes two distinct PIDs, 100 contenders per JVM,
all 200 statuses, and authoritative SQL counts. Tests simulate completed holders with explicitly isolated
SQL fixture transactions; no production release endpoint exists and no external jobs are running.

Six process cases test two-JVM final-slot contention, duplicate keys, persisted WRR/FIFO across SIGKILL,
HTTP response dropped after upstream commit followed by process kill and original-key lookup/replay,
a genuine MariaDB deadlock (heavy fixture transaction makes admission the victim), and DB stop/start.
The outage case checks actual 503 and stable identity, same-container recovery, no cached new execution,
then restarts the app against the rediscovered database port. Raw logs and JUnit are copied to evidence.
AdmissionIT additionally covers default 80/20 limits, CRITICAL shared/strict priority, 100 continuously
backlogged admissions 60/30/10, empty class skip, NOW no leapfrog or latent execution, route eligibility
locks, immutable version/decision, config shrink/audit rollback, principal isolation, permit-generation
fencing, active/unknown work release refusal, and lock-timeout 503. No six-hour soak or external adapter
claim is made by these admission-only cases. Engine, adapter, recovery and hardening suites follow below.


## MariaDB fixture verified readiness (M2 round2)

The pinned image healthcheck deliberately skips TLS verification. LocalFixture therefore requires a
successful SELECT 1 through precisely the same MariaDB user, database, default local transport and TLS
verification as subsequent fixture SQL. Only the exact not-yet-valid error may wait within the original
90-second monotonic deadline. Other auth/certificate/SQL errors fail immediately and preserve diagnostics.
An exited entrypoint may get one fresh initialization replacement only before application/Flyway/data use,
with matching run+purpose and anonymous-volume checks. Used DB restart/outage never rebuilds or clears data.
Diagnostics retain commands, exits, state and server logs; they never read Config.Env or print passwords.

scripts/test_fixture_startup.py runs 14 explicit policy safety tests using command doubles plus two actual
MariaDB tests with generated test-only CA/certificates and strict client verification. Peer fingerprints
prove the configured certificate was loaded; the future certificate must block readiness until valid,
and an expired one must fail immediately with precise diagnostics and unchanged container. These run
before Maven in the cumulative gate and write TEST-FixtureStartup.xml. The policy doubles establish only
fixture safeguards; all admission/transactions remain actual MariaDB/HTTP/JVM tests.

Test-only tools are already installed Ubuntu 24.04 packages, pinned in config/test-tools.json:
python3-cryptography 41.0.7-4ubuntu0.4 (upstream 41.0.7), openssl 3.0.13-0ubuntu3.15,
python3 3.12.3-0ubuntu2.1. Python is /usr/bin/python3; cryptography is loaded from
/usr/lib/python3/dist-packages/cryptography/__init__.py; OpenSSL is /usr/bin/openssl.
The gate records dpkg binary/source package names and exact versions; differing versions fail rather
than installing or silently substituting a floating dependency. Rebuild these test tools from the exact
Ubuntu noble distribution source package revisions recorded in that inventory, or acquire their matching
Ubuntu binary packages into an isolated test environment. No global installation is part of this task.

Diagnostic prototypes and invalid harness revisions are retained only under labelled round2 evidence.
Original natural TLS failures are real, but the cause of their certificate/client time discrepancy remains
unconfirmed; no OS clock changes or global Docker restart were performed.

## M3 cumulative gate and exact crash windows

Run bash scripts/verify-desktop-phase.sh M3 .evidence/desktop/$ROUTE_RUN_ID/M3/recheck-unique after
exporting the existing run ID and sourcing scripts/env.sh. engine_gate.py runs M2/M1/M0 at one fingerprint,
including clean Maven verify, all52 FoundationIT, all19 AdmissionIT, TLS startup, the two-JVM200-way
admission race and database faults. It then runs six EngineProcesses cases against another owned DB.
Missing EngineIT/EngineDslTest/EngineProcesses, AC prefixes or genuine crash proof fail validation.
The gate-negative suite includes missing M3 process evidence; the protected validator is unchanged.

EngineIT tests atomic result/next-pending/event rollback, condition/when, all-settled, context isolation,
six-hour domain budget, DB lease time, notification convergence, bounded executor, old lease CAS,
crash-before-submit unknown, incident closure and publish/input validation. Only its engine fixture rows
are retired in teardown. FoundationIT/AdmissionIT and M2 process tests disable scanner to preserve their
admission-only assertions. M3 process tests enable scanning and independently running JVMs on MariaDB.

DevelopmentCrashHook writes .armed outside Tx before completion, blocking new claims; .reached is written
after complete returns. Tests read committed output/next pending and attempt identities before SIGKILL,
require exit -9, restart a different PID and verify unique progression. Other cases kill two JVMs during
an external parallel branch, preserve a successful sibling and operation ID; kill in durable retry wait
then wait real seconds; change external data after a fixed condition; and retain an unknown operation.

Fixture files are run-owned and configured only at process startup; route definitions cannot choose paths.
DevelopmentAdapter asserts no active DB transaction during I/O. This is M3 simulation, not M4 real
REST/kind/Ansible integration or exactly-once proof. Six-hour tests inject Clock, not OS/DB time; the
independent retry restart uses actual seconds and is not a six-hour soak.
Focused selections can leave target XML from unselected suites: only newly selected cases count.
Acceptance always clean-verifies and parses actual nonempty testcase nodes with no failure/error/skip.

## M3 round2 isolation and incident regression

The cumulative gate provisions a second fresh MariaDB container for EngineHistoryIT/EngineIT, requiring
ROUTE_ENGINE_TEST_DB_URL, ROUTE_ENGINE_TEST_DB_USER and ROUTE_ENGINE_TEST_DB_PASSWORD. Missing values
fail; no fallback to the admission database exists. Both containers are verified empty before migration.
Alphabetical failsafe order runs EngineHistoryIT first on the engine DB, preserving two legacy incident
rows and audit through V3 -> V4 without inferring an attempt. EngineIT then runs its full17 cases there.
FoundationIT52 and AdmissionIT19 still execute in the same clean Maven verify on the first database.

test-database-isolation.json records distinct container IDs/URLs (no password), positive intended rows,
zero cross-suite rows and cleanup verification. Each fixture retains raw owner labels and cleanup exit.
Gate-negative tests reject missing isolation proof, the same container/URL or cross-suite rows.

The incident regression reproduces second-attempt UNKNOWN after first-attempt known failure, tests exact
new OPEN identity, rejects old workers and an old operation ID even with current lease fields, forbids
identity reassignment, and rolls back incident resolution with result/audit together. V4's supporting
step index is required when replacing the original unique key; original V1/V2/V3 are unchanged.

## M3 round4 actual incident-lock order regression

EngineIT adds3 cases (current total20) at the real service/transaction boundary. The fixture holds an
existing incident without taking production locks, starts a worker mutation and polls its own DB user's
PROCESSLIST for the blocked incident statement. Before releasing the incident, a third connection must
obtain SELECT FOR UPDATE NOWAIT on the step and attempt. The gate's raw Maven/JUnit system-out preserves
the blocked SQL and independent NOWAIT success. Original red3 failed on the original source. A2-second
condition deadline and unchanged database timeouts bound this probe; sleeps are not used as proof.

Terminal completion, repeated UNKNOWN, and claim elapsed-budget/new-failure paths are covered while all
prior identity, generation, atomic rollback, admission and process assertions remain. Test-only lock
holding measures the database protocol; it is not a production long transaction or an external I/O path.
All earlier158 cases rerun cumulatively along with these3; actual final counts come only from gate XML.

## M4 adapter suites and historical focused evidence

RestAdapterTest uses a genuine loopback HttpServer, and RestEngineAcceptance uses an isolated real
MariaDB plus scripts/adapter_fixture.py HTTP gateway. KubernetesAcceptance requires the explicit
run kubeconfig, run-labelled namespace and pinned image loaded in kind; it never skips unavailable
Kubernetes. The Acceptance classes are explicitly selected via -Dit.test in M4, not named *IT.

Round1 focused commands are preserved under .evidence/desktop/desktop-20260924T212931Z/M4/round-1:
- run-http-db.py invoked ./mvnw -B -Dtest=RestAdapterTest,AdapterContractTest -Dit.test=RestEngineAcceptance verify: exit0,15 cases.
- run-kind.py invoked the same selected units with -Dit.test=KubernetesAcceptance: exit1, one Runner failure out of5 integration cases.
- run-processes.py invoked scripts/adapter_processes.py::process_acceptance: exit0,3 true SIGKILL/restart cases.

These commands are fixture-backed one-shot checks. They do not invoke the Python outer runner and do
not replace the implemented M4 cumulative dispatcher. Keep the per-command exits, JUnit and resource/crash
JSON. That round1 Runner failure is historical and was fixed before M4 acceptance; no successful artifact
check is inferred from image build or Pod startup. All adapter fixture cleanup checks exact run-id and purpose labels.

## M4 cumulative adapter layer (historically accepted)

Run the same isolated run environment with PYTHONDONTWRITEBYTECODE=1:
bash scripts/verify-desktop-phase.sh M4 .evidence/desktop/$ROUTE_RUN_ID/M4/recheck-unique

adapter_gate.py executes the full M3/M2/M1/M0 gate first. It then starts a new labelled real MariaDB,
builds current config/runner (all source hashes recorded), verifies image and kind ownership, loads
the immutable digest, and runs RestAdapterTest/AdapterContractTest plus explicit RestEngineAcceptance/
KubernetesAcceptance/AdapterBoundaryAcceptance. There is no image-env shortcut in the cumulative gate.
Recovery and hardening dispatchers build cumulatively on this layer. FINAL adds strict fresh-handoff import and fault/evidence checks.

The actual HTTP fixture covers sync/202/poll/4xx/5xx/timeouts/response loss, operation dedupe, unknown
no-query retention, bounded nonrecursive notification and cancel-before-notification-submit. Real kind
covers Deployment UID/generation, an actual409, failed rollout with confirmed Pod stop, stable Job
identity and GC-missing retention. Runner cancellation first reads the actual runner_on_start marker
for the synchronous wait task, then verifies the same permit until Job/Pods are gone.

adapter_artifacts.py removes the original successful Runner Pod and reads the entire PVC from a separate
reader. rc0/statussuccessful/stdout/job_events/command must exist; every content byte plus actual DB and
logs is scanned for the generated secret. A separate real Runner Job deliberately inherits that canary
to regress the command-environment leak. Neither deletion of command nor filename-only scans qualify.

adapter_processes.py adds three actual SIGKILL/restart windows after real HTTP side effect or real Job
creation but before DB result commit. It records old/new PIDs, -9 exits, operation IDs, effect/POST counters
and same Job UID/count. The no-query case remains RECONCILING with held permit and no resubmit.
validate_m4_reports rejects missing/empty/skipped reports, missing AC coverage, missing artifact/crash
proof, context mismatch and missing image command evidence. test_gate.py retains all older negative
regressions and adds these M4 fail-closed cases. Synthetic validator fixtures are never integration proof.

Round2 focused-adapters-1 recorded21 passing cases before the final canary/notification additions.
gate-negatives-1 recorded39 cases with2 errors; cancel-pending-red recorded the real CANCELING:1 failure.
Correction2 fixes the local proof-parser contracts and pending notification stop transition; the
corresponding green directories and frozen full builder gate are authoritative for actual final counts.
Round1 failures remain historical evidence and are not overwritten.

Round3 boundary-red saved5 intended failures; correction1 boundary-green-1 saved18 actual passing
cases (Boundary8, Contract3, REST7). Boundary tests reopen real application contexts against the same
MariaDB for playbook/image/target and business-retry drift, directly reject SQL mutation of published
bindings, reject missing/cross-kind refs, and send6 actual HTTP responses carrying plain/quote/backslash
credentials in nested text/field names. Those responses must remain IN_DOUBT with held permits and no
persisted secret. New published v2 must explicitly use the new binding. gate-negatives-1 ran41 tests;
full M0 gate writes their actual JUnit. All earlier true process/kind/Runner/PVC/cancel tests remain.
Those historical M4 round3 artifacts required a controller gate and fresh Reviewer before later M4 acceptance.
Round2 builder-gate-1's transient endpoint refusal remains an unexplained historical red; no timeout,
global environment setting or repeat-until-green strategy was introduced.

Round4 scalar-red proved10 nontext leaks among16 actual HTTP requests; numeric text was already
blocked and5 nonsecret controls passed. It is a genuine behavioral red (Boundary9/1 failure, no errors
or skips), not a compile failure. scalar-green-1 passed19 cases after the one-branch guard correction.
The new matrix includes direct/nested number/boolean/null, decimal and canonical exponent, alongside
unchanged escaped text/field-key cases. It verifies persisted output/input and audit, no raw response
logging, no unsafe downstream dispatch, held IN_DOUBT permits, and legitimate control type/value.

scalar-secret-boundary.json records blocked as EXPECTED policy. Actual state, secretPersisted,
outputAbsent, incident count and downstream attempts determine success. validate_scalar_proof requires
all16 unique variants and safe11/legitimate5 outcomes, rather than trusting that expected flag.
GateTests adds4 negatives (45 total): missing scalar proof/variant, leaked value, or rejected legitimate
control. That historical M4 round4 used builder-gate-1 plus parent gate and fresh review. New changes require the current cumulative gate.

M5: bash scripts/verify-desktop-phase.sh M5 EVIDENCE_DIR runs M0-M4 and real RecoveryProcesses. Foundation Maven includes RecoveryIT and exact V1-V8 history migration in the M6 source; the separate old-runtime upgrade fixture requires V1-V7 before upgrade. scripts/recovery_processes.py can run focused against its own fresh evidence directory; it records actual API races and four HTTP SIGKILL windows. M5 gate validation rejects missing proof, wrong counts, duplicate effects, skipped tests, missing AC or fingerprint mismatches. Source must freeze before the full gate; read actual XML and summary counts.


M5 round2 adds mandatory RecoveryCancellationIT (one actual HTTP/MariaDB integration case). Its Spring context explicitly uses ROUTE_ENGINE_TEST_DB_URL/USER/PASSWORD and asserts the actual JDBC base URL differs from the foundation endpoint. It calls claim, commits the public cancel command, then executes the existing claim; HTTP POST/DELETE/GET order and held permit across WAITING are checked before STOPPED release. No fresh parallel sibling or following step gets an attempt. M5 gate extracts CANCEL_INTERLEAVING_PROOF from actual JUnit output. All focused runs must supply separate owned main/engine DBs; no copied stale XML is accepted as a new execution.


RecoveryOutputProtectionIT is mandatory in clean Maven verify and M5 proof validation. It creates only synthetic credential files in JUnit temporary storage and records statuses/booleans, not credential values. HTTP and DB snapshots supply rejection/no-mutation evidence. Its normal controls include required string output with ordinary nested null and replay during temporary credential-file unavailability. Optional-output absence under null/true/false credentials has separate controls. M5 requires57 cases and exact proof coverage; that historical revision ran60 validator cases including six new guard proof tests. output-red setup error and output-green-1 compile-only failure have no new executed protection cases; their stale copied artifacts are explicitly NOT_EXECUTED, and only current Maven logs/XML may be counted.

M5 round4 replaces the crash fixture observation boundary after a real red showed normal lease re-claim between completed snapshot and SIGKILL. All source callers use scripts/crash_boundary.py, verify exact owned process identities/all stopped threads, bound the resume/drain transition, and save raw DB activity and monotonic order. The single consistent snapshot retains all original fields and before==after_kill. M5 has9 real RecoveryProcesses cases, including the four original windows and a deliberately blocked real DB transaction that must resume/drain before a valid snapshot; evidence is boundaryDrain plus per-execution crash-boundary files. That M5 revision had70 GateTests, including10 boundary/transition negatives. The accepted historical M5 evidence is M5/round-4; these counts are historical. Full cumulative gate must rerun all affected M3/M4/M5 process paths.

M5 round4 correction2 adds initial-schema TLS seam:25 startup tests (previous16 plus7 policy/proof negatives and2 real MariaDB cases). Future certificate installed only in fresh unused fixture after SELECT1; schema COUNT must pass with TLS validation within same90s deadline. Expired fails without initialization. M1 validates actual names, peer SHA and proof. Six natural nonreproductions with clock backsteps do not establish original cause. Historical M5 authority is round4/builder-freeze-correction2.json and builder-gate-2; earlier337-case gate/root pre-Maven TLS failure historical.

## M6 suites

scripts/hardening_processes.py executes real role APIs, graceful/overlapping JVMs, nonzero metrics vs SQL, DB outage readiness, five real DEMOs, restricted Kubernetes API probes and separate DB dump/restore. scripts/hardening_shutdown.py holds a real pool-row lock across SIGTERM and requires zero attempts/submits after shutdown begins; old M5 reproduces the failure. scripts/hardening_upgrade.py uses the byte-pinned accepted M5 artifact or checksum-verified archived historical source from config/upgrade with explicitly different provenance modes. scripts/hardening_build.py creates a new workspace and fixed-base executable image. scripts/hardening_gate.py runs M5 cumulatively before these suites and validates proof content. Actual XML determines counts. No full-pass conclusion follows from a focused suite or package-only build.

HardeningTest verifies role negatives/rotation and catalog rejection; existing RestAdapterTest retains actual HTTP redirect/credential, body bound and output checks. FoundationIT now asserts exact migrations1..8 rather than1..7 because V8 is additive; all previous migration tests remain. The original M5 57-case output protection and nine process crash cases remain mandatory. The FINAL dispatcher requires fresh handoff evidence and then executes every earlier gate.

M6 fixture isolation: HardeningFixture first asks a run-owned Docker sleep-only probe to allocate a loopback port, cleans that probe after checking ownership, then creates MariaDB on the same explicit port. WSL availability alone does not establish Docker Desktop host availability; a transfer collision is an error, not a retry. This preserves the same JDBC endpoint across actual stop/start and proves the same JVM readiness503 then200. Inherited M0-M5 fixtures retain their original dynamic mappings. Round1 published new-port refusal was not reproduced by the diagnosis and is not claimed explained by stale-JVM URL alone.

Current document consistency checks in scripts/hardening_documents.py compare the scope tables and default gate commands with STATE, real dispatcher arms, examples and the actual resolve API. Mutation controls reject an obsolete default phase, omitted executable gates, a future-work DEMO claim and a future resolution claim. They complement manual semantic review; they do not establish external acceptance.

M6 AC058 uses one scheduler+engine JVM, with admission enabled before publishing/submitting all five DEMOs. Each record includes the same live PID and durable terminal snapshot; Kubernetes summaries retain Job/Deployment identity/outcomes. This happy-path suite does not inject process crashes between admission and completion. All dedicated SIGKILL, unknown-outcome, SIGTERM and overlap suites remain mandatory. On DEMO failure, bounded execution/attempt/incident and Kubernetes identity/status diagnostics are captured before owned cleanup. A lost submit acknowledgement never authorizes resubmit merely because a Job is absent.

## FINAL executable gate and independent handoff

Read ADD_ROUTE for the complete fresh-agent configuration and fixture workflow. Set ROUTE_FINAL_HANDOFF to the original sealed execution directory and ROUTE_FINAL_HANDOFF_RECEIPT to the controller's external receipt before running FINAL. Missing evidence fails before cumulative execution. final_evidence.py validates exact proof/receipt shape, same run/source/Java/example hashes, artifact containment/hash manifest, six distinct original API executions and matching no-skip JUnit. Gate evidence labels imported cases prior external execution, preserves original hashes and records the handoff JAR separately from later rebuilt JARs.

final_gate.py then runs the complete M0-M6 gate. It verifies actual clean Maven verify/new work directory build and independent DB isolation, resolves15 fault/timing scenarios to exact successful JUnit names, and binds reports/commands/checks to the frozen source. AC060 is REVIEW-only and absent from executable checks; the separate new Reviewer confirms it. test_final_evidence.py adds synthetic validator controls for missing/stale/tampered evidence, controller identity, Java/examples mutation, missing original routes, mismatched counts, skipped XML, path escapes, false API success and incomplete fault coverage. These synthetic tests are validator tests, never engine integration or fresh-agent execution.

Source FINAL_ACCEPTANCE remains CANDIDATE/NOT_PASS. The final controller result under the run evidence directory is the acceptance authority after gate plus review. No production credentials, enterprise acceptance or six-hour soak is implied. All prior mandatory assertions and real fixtures remain required.

Historical correction2 preparation (Builder call48): validators-correction2.xml records92 passing cases (73 inherited controls,16 FINAL evidence controls,3 real loopback HTTP lifecycle/fault tests), zero failures/errors/skips. The exact unchanged handoff-agent-1/demo6.json and all five originals passed6 real API executions under builder-regression-correction2; its sealed proof is BUILDER_REGRESSION_NOT_ACCEPTANCE and cannot satisfy independent AC061. One async operation has observed submit202, WAITING poll202, real completion HTTP200 and later terminal poll200; cleanup completed. Shared crash fixtures and all31 engine Java files remain unchanged. The initial19 focused tests also passed. Current document checks are recorded in documents-correction2 after these notes. Candidate-freeze-correction2.json supersedes only preparation readiness; original failed fresh-agent evidence and initial freeze/result remain immutable. NEW agent49 must independently author handoff-agent-2 after this freeze; full root main-gate-1 and a separate NEW Reviewer remain pending. FINAL remains CANDIDATE, NOT_PASS; no external or production acceptance.

FINAL round1 correction3, Builder call50: fresh agent49 actually completed six routes and owned cleanup with zero findings. Controller import failed before receipt or full gate because two genuine successful readiness command logs were empty. Original handoff-agent-2/execution and its185-file manifest remain untouched. Only auxiliary fixture/raw-<number>-<label>.log outputs may now be zero bytes, with nonempty paired command/exit and unchanged exact SHA, manifest, path and symlink checks. Required proof/config/API/stdout/JUnit artifacts stay nonempty. The real sealed tree is tested against its explicitly historical source, not accepted for this changed candidate. New handoff-agent-3 by fresh agent51, full main-gate-1 and a separate Reviewer remain required after candidate-freeze-correction3.json. Three local corrections are now used in FINAL round1; further correction requires a new outer round. FINAL remains CANDIDATE/NOT_PASS.

Current correction3 focused results: all94 validators passed (73 inherited controls,18 FINAL evidence controls,3 real HTTP lifecycle/fault tests), zero failures/errors/skips. Empty auxiliary log acceptance still rejects changed SHA and absent command-exit evidence; resealed empty semantic artifacts are rejected. Historical-import-correction3.json records successful validation of the untouched185-file actual agent49 tree against its historical fingerprint, retaining both zero-byte readiness logs and unchanged proof SHA. This is importer regression only, not current-candidate AC061. Documents are rechecked in documents-correction3 after these notes. Protected31 and engine Java31 remain unchanged. New immutable candidate-freeze-correction3.json and builder-result-correction3.json supersede preparation readiness only. Fresh agent51 must create handoff-agent-3 on the new fingerprint; cumulative main-gate-1 and separate new Reviewer remain pending. No source writes after freeze; FINAL CANDIDATE/NOT_PASS remains truthful.

PersistenceGuardIT uses real HTTP and MariaDB with synthetic credential files. It verifies initial QUEUE/NOW and draft/edit/publish rejection without mutations, decoded literals and typed positives, relevant unavailability, original accepted/rejected replay, actual latest-version pool-lock race, historical claim/queue retention, and the credential-in-transaction prohibition. Credential-free pure checks preserve the unchanged AC028 incident-before-step lock test. The fresh FINAL handoff must use the repaired baseline selected by STATE.final_java_baseline.

FINAL round3 Builder preparation: security/focused-all has216 cases/13 reports, adapter-boundaries25/4, validators95; all pass with zero skips. PersistenceGuardIT has18 true HTTP/MariaDB cases including request key/requestId rejection, every affected registry mutation, unavailable context/replay and actual locked context races. envelope-green-2 records15 packaged-JAR negatives and positive replay with no mutation/response secret. These scoped results precede final document checks and do not replace the fresh agent57, cumulative FINAL gate and Reviewer58. See HANDOFF for preserved failures and the2/3 correction ledger.
