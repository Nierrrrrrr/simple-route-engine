# Implementation decisions

- 2026-09-25: M0 only, modular packages rooted at dev.routeengine; no application code until M1.
- Exact versions and official sources: [ADR 0001](../adr/0001-stack.md).
- API/security/DSL bounds and token rotation: [ADR 0002](../adr/0002-api-security-dsl.md).
- Lock order, persistent WRR cursor, CAS generations and short READ COMMITTED transactions: [transaction contract](../architecture/TRANSACTIONS.md).
- WSL2 Ubuntu executes Bash against the same Windows checkout; only workspace caches and run-specific Docker/kube configuration.
- Official Maven wrapper binary type retains ZIP SHA-256 verification when Linux lacks unzip.
- Desktop controller uses protected validator import; original runner main remains unused. Final result belongs in evidence, not mutable source PASS markers.
- 2026-09-25 M1: [foundation ADR](../adr/0003-foundation.md) records actual JDBC/audit/immutable triggers, monotonic drafts, structural DSL subset and local process acceptance.
- M1 local correction 1: Failsafe classesDirectory explicitly uses target/classes so the Boot repackaged executable jar does not hide application classes from integration tests. No test assertion changed.
- M1 local correction 2: re-discover Docker's actual random published DB endpoint after restart, verify bounded TCP handshake and unchanged container ID/hash. This changes fixture connectivity, not restart/persistence requirements.
- M1 round 2 / AC-008: Jackson scalar coercion is disabled before Bean Validation/CAS for Integer, Boolean and Textual targets; floating-point values cannot be truncated into stateVersion. DTOs and business state transitions stay unchanged.
- M1 round 2 / AC-008: ApiErrors preserves framework ErrorResponse 4xx statuses and response headers (including Allow/Accept), while producing a sanitized requestId/UTC envelope. Unexpected failures remain 500.
- Both reviewer defects were reproduced by 19 failing real HTTP cases, fixed without changing assertions, and the same 26-case focused HTTP suite passed. The cumulative gate and fresh review remain required for the new candidate.

- M1 round 3 / AC-008: require Jackson FAIL_ON_TRAILING_TOKENS to consume the complete single JSON body before invoking the controller. Legal trailing whitespace is allowed.
- M1 round 3 / AC-008: declare application/json on RouteController mappings so Accept negotiation happens before registry transactions. Incompatible Accept returns the established 406 JSON envelope with no persisted changes.
- The 17 new rejection regressions failed before correction; all 46 focused HTTP cases then passed unchanged. The three accepted-media control cases each execute all seven mutations. No transaction or schema behavior was changed.

- M2: [admission ADR](../adr/0004-admission.md) records pool-first SQL, stable FIFO tie-break, immutable original idempotent decisions, uncertain outcome503 and safe internal stop.
- M2 local correction 1 preserves M0 configUpdateCursorRule: reset only when weights change. Capacity/pause-only updates retain cursor; regression initially fails before correction.
- M2 phase compatibility: migration assertions now require exact versions [1,2]; invalid POST /executions is 422 and unimplemented recovery remains 501. All previous M1 assertions remain, including scalar, trailing-token and Accept-before-mutation regressions.
- FoundationIT disables the admission wake loop for isolated registry tests; dedicated packaged process tests run the scheduler and prove durable queue restart. No runtime service was added.

- M2 local correction2: new validator-negative assertion uses the fixed helper's actual PipelineError wrapper and requires the missing AdmissionProcesses report in its message. Underlying missing-evidence rejection is unchanged; initial builder-gate-1 stopped at M0 and is preserved.

- M2 local correction3 normalizes the initial AdmissionService Result body through the same stored JSON representation as replay. This preserves identical HTTP content and resolves internal LongNode/IntNode equality. The full19-case test source remains unchanged.

- M2 outer round2 correction1: verified SQL readiness, precise failure diagnostics, one bounded fresh
  initialization replacement only before use with run/purpose/anonymous-volume guards; 90-second shared
  deadline unchanged. No retry for expired/auth/SQL errors, no recreation on used DB restart/outage.
  Controlled loaded-certificate red/green proves readiness mismatch; OS time cause remains unconfirmed.
  Fixture tools pinned to existing Ubuntu package versions; all 19 admission assertions retained.

- M3 initial compatibility: FoundationIT migration assertion becomes exact [1,2,3] for additive V3; no prior schema check removed. FoundationIT/AdmissionIT and M2 process fixture explicitly disable engine scanner, keeping their original admission-only assertions. EngineIT manually drives real engine transactions; M3 process tests enable scanner. Development adapter only exists with explicit engine-development profile.

- M3 local correction1: explicit UTC LocalDateTime at JDBC DATETIME boundaries; real DB lease test exposed implicit JVM +08 Timestamp conversion. Preserve failing assertion; production ownership remains DB-clock based.

- M3 correction2: missing closing brace in UTC helper; compiler failure and unchanged-assertion green preserved.
- M3 correction3: reject optional required-binding paths, retain EXISTS for optional declared fields; close unknown incident on known terminal result with same-transaction audit. Both defects reproduced first. See ADR0005.

- M4 round3 correction1: ADR0009 binds adapter semantics at publication (V6), including explicit
  Kubernetes target snapshot, with pure local runtime drift checks and no legacy inference. Existing
  V1-V5 remain unchanged. True MariaDB mutation/restart and typed-ref regressions accompany the change.
- M4 round3 AC041: inspect decoded text/field names recursively before persistence; actual HTTP secrets
  containing quote/backslash now fail closed, while all prior output-size/redirect/PVC scans remain.

- M4 round4 correction1: protect nontext scalar persisted JSON representations in addition to decoded
  text/keys. Genuine HTTP/DB red shows10 scalar leaks; legitimate5 controls disallow blanket rejection.
  No V1-V6 migration, credential-format, timeout or retry policy change. Scalar proof has explicit actual
  outcome assertions; expected blocked flags do not establish PASS. See ADR0009 and SECURITY.

- M5 V7 extends the existing admission_requests queue; no second scheduler. Rollback has its own step_run/recovery_origin_id. Compensation success exposes COMPENSATED with explicit CANCEL, and never silently resumes forward. retry_base establishes a new finite human retry window without resetting historical attempt numbers or operation generations.
- M5 foundation smoke legitimately changes obsolete recovery501 to strict empty-body422, retaining packaged app/DB restart proof. Exact migrations now1..7 with existing historical identity/plan/binding assertions and additional NULL recovery-context assertions.
- M5 correction1 fixes first/replay numeric JsonNode normalization in production response code, preserving complete equality assertions. Correction2 normalizes optional null output at request construction, preserving full stale-incident validation and all queued admission assertions. Reds remain under M5/round-1.

M5 rollback when uses the same permitted immutable context as its captured input; rollback_allowed is saved before forward submission. A false/missing captured guard rejects ROLLBACK with422 and leaves its current incident unchanged. STOPPED confirmation offers RETRY/CANCEL. After a successful forward recovery with no other failed operation, never-dispatched stopped nodes reopen; already successful steps/condition choices remain unchanged.

- M5 correction3: edge-red contains25 actual integration executions with3 failures (STOPPED leaves RUNNING, unstarted sibling remains stopped, false rollback guard accepted). Fixes safe STOPPED convergence, bounded resumption of only never-dispatched nodes, captured rollback guard and accurate advertised actions. processes-1 preserves the correct NOW409 behind queuedCRITICAL; fixture now creates both manual executions before queuing. The obsolete future-phase test now covers M6/FINAL and verifies M5 still requires an injected fingerprint. Negative recursion was stopped only through its recorded owned PID tree; no interrupted suite is counted as passing.


- M5 round2 correction1 repairs the remaining FoundationIT obsolete501 placeholder using strict invalid422, valid-schema missing-target404, both route/recovery unauthenticated401 and unchanged counts for executions/admission_requests/operator_commands/step_runs/step_attempts/execution_events. The round1 full gate red remains intact; this is phase compatibility under the fixed contract.
- Cancellation ordering uses the existing durable claim commit as dispatch linearization. No runtime change or new barrier was introduced. RecoveryCancellationIT directly orders existing claim/execute public engine methods around the public authenticated cancel API and actual REST I/O. It proves no fresh sibling/later dispatch, original permit retention through nonterminal cancellation, and release after observed STOPPED.
- Round2 correction2 binds that new context explicitly to ROUTE_ENGINE_TEST_DB_* and asserts actual JDBC URL plus distinct main/engine endpoints. Focused1's green case used the main fixture database and is not independent-DB proof. The focused evidence runner then had import/subdirectory setup failures before Maven; focused2 is explicitly NOT_EXECUTED and its stale copied reports are not counted. Fresh focused3 and the frozen full gate are the required results.

- M5 round2 correction3 is conservative resource accounting for evidence-only runner import/subdirectory setup repairs. No test executed before those failures, no stale XML counted. Focused3 ran88 cases against distinct real DBs with zero failure/error/skip. No additional runtime/test behavior change; full gate and fresh review remain mandatory.


- M5 round3 addresses Reviewer29's confirmed AC-041 operator bypass; that review was platform-interrupted before formal result, so it is not counted complete. The original red-only probe and incomplete artifacts remain unchanged.
- OperatorPayloadGuard shares AdapterCatalog's existing decoded field/scalar policy and captures exact persisted context. Credential reads are before mutation transactions; inside locks only immutable context/body hashes are rechecked. RestAdapter's credential method now explicitly rejects transaction-local file access. No V1-V7 schema change, new queue, credential persistence or external resubmission.
- Same-key replay checks the stored decision before new preparation and rechecks it under lock; this preserves the original response even if a credential file is temporarily unavailable. Queue preparation uses an unlocked preview only; locked selection remains authoritative and a changed candidate consumes no permit/cursor.
- Structural absent optional outputs are omitted only from sensitive-value scanning; supplied nested null remains protected and required typed output remains validated. Literal null/true/false credentials have five explicit legal controls.
- Correction1 fixed test BeforeAll/TempDir setup (original output-red one error, no behavior proof). output-red-2 ran52 cases with48 actual failures and no errors/skips. Correction2 implemented the guard but first rerun failed compile (missing requestId helper parameter; copied old XML excluded). Correction3 fixed that parameter, added five absence controls, strengthened valid string output schema and wired mandatory proof plus six validator negatives. output-green-2 actually ran57 protection cases +10 adapter unit cases, all green. Local budget3/3.

- M5 round4 correction1: two real minimized tests establish pre-kill lease re-claim between a completed snapshot and SIGKILL. A test-only SIGSTOP boundary now verifies direct-child PID/start identity/executable/cwd and every thread, checks test-DB transaction/command idleness, and resumes/drains/retries at most10 times when a short transaction is pending. Snapshots use a single consistent read-only transaction; original fields/equality remain. A real blocked pool-row transaction proves the resume path, not only the idle fast path. Monotonic event ordering is authoritative for orchestration; observed DB wall clock need not be monotonic. No production Java, lease configuration, migration, operation identity or recovery semantics changed.

M5 round4 correction2: preserve root main-gate-1 TLS2026 after readiness. Diagnostics observed6 clock backsteps but no TLS reproduction; original cause unproven. Controlled real future-certificate transition reproduces first-schema seam (2cases/1failure/0errors), then25 startup cases pass after fresh-unused COUNT uses existing exact-error loop/original90s deadline. No TLS downgrade, host clock change, generic SQL retry, timeout extension or used DB recreation. Call32 usage-interrupted; resumed call33/total34. User requests stop after accepted M5; M6/FINAL pending.
