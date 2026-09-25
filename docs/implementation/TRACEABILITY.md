# Requirement traceability

M0 has executable validators. Future symbols are explicitly planned and must be replaced by actual tests before their gate.

| ID | Phase | Requirement | File / symbol | Command | Status |
|---|---|---|---|---|---|
| AC-001 | M0 | 契約與 phase 邊界固定 | scripts/m0_validate.py::validate_documents; GateTests.test_missing_document/test_broken_document_link | bash scripts/verify-desktop-phase.sh M0 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-002 | M0 | 工具與隔離 preflight | scripts/doctor.py::main/validate_doctor; GateTests.test_missing_tool_requirement | bash scripts/verify-desktop-phase.sh M0 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-003 | M0 | 可機器驗證的 gate | scripts/desktop_gate.py::run_gate; scripts/test_gate.py::GateTests.test_wrapper_* | bash scripts/verify-desktop-phase.sh M0 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-004 | M0 | 可恢復的 agent 工作紀錄 | scripts/m0_validate.py::validate_state; GateTests.test_missing_state_field/test_missing_requirement_trace | bash scripts/verify-desktop-phase.sh M0 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-005 | M1 | 可重現 build | DefinitionRulesTest; scripts/foundation_gate.py::LocalFixture.command (Maven clean verify) | bash scripts/verify-desktop-phase.sh M1 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-006 | M1 | 真實 MariaDB migrations | FoundationIT.AC006_emptyDatabaseFlywayUsesRealMariaDbInnoDb; LocalFixture.start/smoke; scripts/test_fixture_startup.py::RealTlsTests | bash scripts/verify-desktop-phase.sh M1 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-007 | M1 | route CRUD 與 immutable version | FoundationIT.AC007_draftPublishImmutableSoftDeleteKeepsExecutionVersion/AC007_uniqueMonotonicVersionAndDraftWithdrawal | bash scripts/verify-desktop-phase.sh M1 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-008 | M1 | API/data schema 基礎 | FoundationIT.AC008_validationErrorsRequestIdUtcAndActualOpenApi/AC008_invalidAdmissionAndUnavailableRecoveryNeverCreateWorkAndUnauthenticatedRequestsFail/AC008_scalarCoercionNeverMutatesRegistry/AC008_frameworkClientErrorsKeepStatusHeadersAndEnvelope/AC008_singleJsonBodyRequiredBeforeMutation/AC008_unacceptableResponseTypeNeverMutates/AC008_jsonAndWildcardAcceptCommitNormally | bash scripts/verify-desktop-phase.sh M1 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-009 | M1 | 持久化事件與唯一性 | FoundationIT.AC009_fkStateCasAndEventsCommitOrRollbackTogether/AC009_routeMutationRollsBackWhenAuditCannotBeWritten | bash scripts/verify-desktop-phase.sh M1 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-010 | M1 | 本地可啟動環境 | scripts/foundation_gate.py::LocalFixture.smoke; scripts/local-run.sh | bash scripts/verify-desktop-phase.sh M1 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-011 | M2 | 最後一個 slot 競爭 | src/test/java/dev/routeengine/AdmissionIT.java::AC011_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-012 | M2 | 100/20 硬保留 | src/test/java/dev/routeengine/AdmissionIT.java::AC012_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-013 | M2 | CRITICAL strict priority | src/test/java/dev/routeengine/AdmissionIT.java::AC013_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-014 | M2 | 6:3:1 持久化 WRR | src/test/java/dev/routeengine/AdmissionIT.java::AC014_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-015 | M2 | class 內 FIFO 與 NOW 不插隊 | src/test/java/dev/routeengine/AdmissionIT.java::AC015_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-016 | M2 | NOW 原子成功或拒絕 | src/test/java/dev/routeengine/AdmissionIT.java::AC016_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-017 | M2 | QUEUE 與 capacity snapshot | src/test/java/dev/routeengine/AdmissionIT.java::AC017_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-018 | M2 | 冪等與回應遺失 | src/test/java/dev/routeengine/AdmissionIT.java::AC018_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-019 | M2 | 配置更新與縮減 | src/test/java/dev/routeengine/AdmissionIT.java::AC019_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-020 | M2 | permit generation | src/test/java/dev/routeengine/AdmissionIT.java::AC020_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-021 | M2 | 跨程序交易正確 | src/test/java/dev/routeengine/AdmissionIT.java::AC021_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-022 | M2 | DB outage fail closed | src/test/java/dev/routeengine/AdmissionIT.java::AC022_*; scripts/admission_gate.py::process_acceptance/validate_m2_reports | bash scripts/verify-desktop-phase.sh M2 EVIDENCE_DIR | HISTORICAL_PASS; cumulative rerun required |
| AC-023 | M3 | 持久化順序推進 | EngineIT.AC023_*; scripts/engine_gate.py::process_acceptance/validate_m3_reports | bash scripts/verify-desktop-phase.sh M3 EVIDENCE_DIR | HISTORICALLY ACCEPTED M3 round4; current M4 regression pending |
| AC-024 | M3 | 條件與上下文固定 | EngineIT.AC024_*; scripts/engine_gate.py::process_acceptance/validate_m3_reports | bash scripts/verify-desktop-phase.sh M3 EVIDENCE_DIR | HISTORICALLY ACCEPTED M3 round4; current M4 regression pending |
| AC-025 | M3 | 受限 parallel ALL_SETTLED | EngineIT.AC025_*; scripts/engine_gate.py::process_acceptance/validate_m3_reports | bash scripts/verify-desktop-phase.sh M3 EVIDENCE_DIR | HISTORICALLY ACCEPTED M3 round4; current M4 regression pending |
| AC-026 | M3 | durable retry 與時鐘 | EngineIT.AC026_*; scripts/engine_gate.py::process_acceptance/validate_m3_reports | bash scripts/verify-desktop-phase.sh M3 EVIDENCE_DIR | HISTORICALLY ACCEPTED M3 round4; current M4 regression pending |
| AC-027 | M3 | 安全 MANUAL_WAIT | EngineIT.AC027_*; scripts/engine_gate.py::process_acceptance/validate_m3_reports | bash scripts/verify-desktop-phase.sh M3 EVIDENCE_DIR | HISTORICALLY ACCEPTED M3 round4; current M4 regression pending |
| AC-028 | M3 | step 認領與 fencing | EngineIT.AC028_*; scripts/engine_gate.py::process_acceptance/validate_m3_reports | bash scripts/verify-desktop-phase.sh M3 EVIDENCE_DIR | HISTORICALLY ACCEPTED M3 round4; current M4 regression pending |
| AC-029 | M3 | 一般例外隔離 | EngineIT.AC029_*; scripts/engine_gate.py::process_acceptance/validate_m3_reports | bash scripts/verify-desktop-phase.sh M3 EVIDENCE_DIR | HISTORICALLY ACCEPTED M3 round4; current M4 regression pending |
| AC-030 | M3 | 未知結果不盲目重送 | EngineIT.AC030_* + AC028_AC030_*; EngineHistoryIT.AC030_*; scripts/engine_gate.py::process_acceptance/validate_m3_reports | bash scripts/verify-desktop-phase.sh M3 EVIDENCE_DIR | HISTORICALLY ACCEPTED M3 round4; current M4 regression pending |
| AC-031 | M3 | DSL 發布驗證 | EngineDslTest.AC031_*; EngineIT.AC031_* | bash scripts/verify-desktop-phase.sh M3 EVIDENCE_DIR | HISTORICALLY ACCEPTED M3 round4; current M4 regression pending |
| AC-032 | M4 | REST真實HTTP行為 | RestAdapterTest.AC032_*; RestEngineAcceptance.AC032_* | bash scripts/verify-desktop-phase.sh M4 EVIDENCE_DIR | M4 accepted; two221-case gates and fresh review, see M4/ACCEPTED.json |
| AC-033 | M4 | 副作用與冪等查验 | scripts/adapter_processes.py::process_acceptance (real HTTP SIGKILL) | bash scripts/verify-desktop-phase.sh M4 EVIDENCE_DIR | M4 accepted; two221-case gates and fresh review, see M4/ACCEPTED.json |
| AC-034 | M4 | 無冪等的未知操作 | RestAdapterTest.AC034_*; RestEngineAcceptance.AC034_*; adapter_processes unknown_crash | bash scripts/verify-desktop-phase.sh M4 EVIDENCE_DIR | M4 accepted; two221-case gates and fresh review, see M4/ACCEPTED.json |
| AC-035 | M4 | 實際Kubernetes rollout | KubernetesAcceptance.AC035_* | bash scripts/verify-desktop-phase.sh M4 EVIDENCE_DIR | M4 accepted; two221-case gates and fresh review, see M4/ACCEPTED.json |
| AC-036 | M4 | Job建立/回應遺失 | KubernetesAcceptance.AC036_*; adapter_processes job_crash | bash scripts/verify-desktop-phase.sh M4 EVIDENCE_DIR | M4 accepted; two221-case gates and fresh review, see M4/ACCEPTED.json |
| AC-037 | M4 | 真實Ansible執行 | KubernetesAcceptance.AC037_AC041_* | bash scripts/verify-desktop-phase.sh M4 EVIDENCE_DIR | M4 accepted; two221-case gates and fresh review, see M4/ACCEPTED.json |
| AC-038 | M4 | Job取消與remote工作 | KubernetesAcceptance.AC038_*; RestEngineAcceptance.AC038_*; runner_on_start + real Pod convergence | bash scripts/verify-desktop-phase.sh M4 EVIDENCE_DIR | M4 accepted; two221-case gates and fresh review, see M4/ACCEPTED.json |
| AC-039 | M4 | 外部重試世代 | RestAdapterTest.AC039_*; RestEngineAcceptance.AC039_* | bash scripts/verify-desktop-phase.sh M4 EVIDENCE_DIR | M4 accepted; two221-case gates and fresh review, see M4/ACCEPTED.json |
| AC-040 | M4 | 失敗通知有限且隔離 | RestEngineAcceptance.AC040_*; scripts/adapter_fixture.py HTTP gateway | bash scripts/verify-desktop-phase.sh M4 EVIDENCE_DIR | M4 accepted; two221-case gates and fresh review, see M4/ACCEPTED.json |
| AC-041 | M4 | artifact與secret保護 | RestAdapterTest.AC041_*; KubernetesAcceptance.AC037_AC041_*; adapter_artifacts full PVC reader + inherited-env canary | bash scripts/verify-desktop-phase.sh M4 EVIDENCE_DIR | M4 accepted; two221-case gates and fresh review, see M4/ACCEPTED.json |
| AC-042 | M5 | recovery NOW原子拒絕 | RecoveryIT; RecoveryProcesses real HTTP/JVM crash suite | bash scripts/verify-desktop-phase.sh M5 EVIDENCE_DIR | M5 candidate pending frozen full gate and fresh review |
| AC-043 | M5 | recovery QUEUE原priority | RecoveryIT; RecoveryProcesses real HTTP/JVM crash suite | bash scripts/verify-desktop-phase.sh M5 EVIDENCE_DIR | M5 candidate pending frozen full gate and fresh review |
| AC-044 | M5 | recovery冪等/競態 | RecoveryIT; RecoveryProcesses real HTTP/JVM crash suite | bash scripts/verify-desktop-phase.sh M5 EVIDENCE_DIR | M5 candidate pending frozen full gate and fresh review |
| AC-045 | M5 | RETRY與SKIP | RecoveryIT; RecoveryProcesses real HTTP/JVM crash suite | bash scripts/verify-desktop-phase.sh M5 EVIDENCE_DIR | M5 candidate pending frozen full gate and fresh review |
| AC-046 | M5 | ROLLBACK預設禁止 | RecoveryIT; RecoveryProcesses real HTTP/JVM crash suite | bash scripts/verify-desktop-phase.sh M5 EVIDENCE_DIR | M5 candidate pending frozen full gate and fresh review |
| AC-047 | M5 | rollback完成/失敗 | RecoveryIT; RecoveryProcesses real HTTP/JVM crash suite | bash scripts/verify-desktop-phase.sh M5 EVIDENCE_DIR | M5 candidate pending frozen full gate and fresh review |
| AC-048 | M5 | CANCEL多狀態語意 | RecoveryIT; RecoveryCancellationIT actual HTTP/MariaDB claim-cancel-execute; RecoveryProcesses JVM suite | bash scripts/verify-desktop-phase.sh M5 EVIDENCE_DIR | M5 candidate pending frozen full gate and fresh review |
| AC-049 | M5 | IN_DOUBT人工查驗 | RecoveryIT; RecoveryProcesses real HTTP/JVM crash suite | bash scripts/verify-desktop-phase.sh M5 EVIDENCE_DIR | M5 candidate pending frozen full gate and fresh review |
| AC-050 | M5 | 舊permit延遲回應 | RecoveryIT; RecoveryProcesses real HTTP/JVM crash suite | bash scripts/verify-desktop-phase.sh M5 EVIDENCE_DIR | M5 candidate pending frozen full gate and fresh review |
| AC-051 | M6 | 正式模式身份與權限 | HardeningAcceptanceTest (planned) | bash scripts/verify-desktop-phase.sh M6 EVIDENCE_DIR | NOT_RUN |
| AC-052 | M6 | 命令/URL/namespace邊界 | HardeningAcceptanceTest (planned) | bash scripts/verify-desktop-phase.sh M6 EVIDENCE_DIR | NOT_RUN |
| AC-053 | M6 | 啟停與重疊Pod | HardeningAcceptanceTest (planned) | bash scripts/verify-desktop-phase.sh M6 EVIDENCE_DIR | NOT_RUN |
| AC-054 | M6 | 版本與DB升級相容 | HardeningAcceptanceTest (planned) | bash scripts/verify-desktop-phase.sh M6 EVIDENCE_DIR | NOT_RUN |
| AC-055 | M6 | 監控/audit/持久化與runbook | HardeningAcceptanceTest (planned) | bash scripts/verify-desktop-phase.sh M6 EVIDENCE_DIR | NOT_RUN |
| AC-056 | M6 | 部署與測試可重現 | HardeningAcceptanceTest (planned) | bash scripts/verify-desktop-phase.sh M6 EVIDENCE_DIR | NOT_RUN |
| AC-057 | M6 | Agent接手文件完整 | HardeningAcceptanceTest (planned) | bash scripts/verify-desktop-phase.sh M6 EVIDENCE_DIR | NOT_RUN |
| AC-058 | M6 | 範例與外部驗收標示 | HardeningAcceptanceTest (planned) | bash scripts/verify-desktop-phase.sh M6 EVIDENCE_DIR | NOT_RUN |
| AC-059 | FINAL | 乾淨環境全量累積驗收 | FinalAcceptanceTest + fresh Reviewer (planned) | bash scripts/verify-desktop-phase.sh FINAL EVIDENCE_DIR | NOT_RUN |
| AC-060 | FINAL | 獨立整體審查 | FinalAcceptanceTest + fresh Reviewer (planned) | bash scripts/verify-desktop-phase.sh FINAL EVIDENCE_DIR | NOT_RUN |
| AC-061 | FINAL | 第六條route接手演練 | FinalAcceptanceTest + fresh Reviewer (planned) | bash scripts/verify-desktop-phase.sh FINAL EVIDENCE_DIR | NOT_RUN |
| AC-062 | FINAL | fault matrix與長時語意 | FinalAcceptanceTest + fresh Reviewer (planned) | bash scripts/verify-desktop-phase.sh FINAL EVIDENCE_DIR | NOT_RUN |
| AC-063 | FINAL | 交付清單與真實證據 | FinalAcceptanceTest + fresh Reviewer (planned) | bash scripts/verify-desktop-phase.sh FINAL EVIDENCE_DIR | NOT_RUN |
| AC-064 | FINAL | 上線界線 | FinalAcceptanceTest + fresh Reviewer (planned) | bash scripts/verify-desktop-phase.sh FINAL EVIDENCE_DIR | NOT_RUN |


M2 round2 fixture correction is supplementary AC-006/AC-010 evidence. The cumulative gate includes
16 startup regressions (14 policy safety tests, two real MariaDB TLS cases), never a substitute for
AdmissionIT or six mandatory AdmissionProcesses cases. Current source freeze and result are in
M2/round-2/builder-gate-1; round1 process-focused passes do not establish this new source's gate.

M3 round2 adds a mandatory independent engine MariaDB proof in the cumulative clean build (ADR0006),
EngineHistoryIT V3-to-V4 preservation, and EngineIT new-attempt incident/fencing/rollback regression.
Original red, errno150 supporting-index red and single-variable probe remain under M3/round-2.
M3 status remains candidate requiring a new cumulative gate and fresh reviewer; no M4–FINAL claim.

M3 round4 AC-028 adds EngineIT.AC028_existingIncidentLock* (three actual DB contention cases),
covering existing incident acquisition before terminal, repeated UNKNOWN and claim-budget step/attempt
writes. Reviewer SQL red and new contention red remain separately preserved. See ADR0007. The cumulative
M0–M3 gate and new Reviewer must run again at the final source; previous158-case PASS is historical.

M4 round3 adds AdapterBoundaryAcceptance (8 actual cases) to the mandatory cumulative adapter suite:
AC007_publishedBindingsRejectDirectDatabaseMutation; AC017_queuedVersionCannotAdoptChangedPlaybookAfterRestart,
AC017_queuedVersionCannotAdoptChangedImageAfterRestart, AC017_queuedVersionCannotAdoptChangedKubernetesContextAfterRestart,
AC017_existingBusinessRetryCannotRebindAfterCatalogRestart; AC031_publicationRejectsMissingAndCrossKindIncludingRollbackAndNotice,
AC031_runtimeRejectsCrossKindAndMissingReferences; AC041_decodedSecretsInNestedValuesAndFieldNamesNeverPersist.
These strengthen AC-007/017/031/041 without deleting earlier assertions. Actual MariaDB guards reject
binding mutation; closed/reopened application contexts share the same DB, execution and definition hash.
New publication adopts the changed catalog explicitly. Existing process crash/restart proofs remain.
validate_m4_reports requires the decoded-secret, queued/retry-binding, SQL immutability and typed-ref
proofs in addition to all earlier reports. GateTests adds missing-publication-proof and decoded-leak
negative cases (41 total). Candidate evidence is M4/round-3/builder-gate-1, not an older round's gate.

M4 round4 AC-041 adds AdapterBoundaryAcceptance.
AC041_allPersistedScalarRepresentationsRejectCredentialsAndAllowOrdinaryValues. Its16 actual HTTP
responses cover numeric text, direct/nested large integer, decimal/canonical exponent, direct/nested
true/false/null, and5 legitimate scalar controls. Assertions inspect real MariaDB output/input/audit,
held IN_DOUBT/permit, downstream attempts and captured response-body logs. The existing8 boundary
cases and all earlier adapter/process assertions remain. scalar-secret-boundary.json is mandatory;
blocked records expected policy, while actual state/output/leak/incident/dispatch fields prove it.
Four GateTests additions reject missing scalar proof, a leak flag, missing variant and blanket type
rejection of a legitimate control. gate-negatives-1 passed45 actual JUnit cases. Current full candidate
source/evidence is M4/round-4/builder-gate-1; round3 is historical after its fresh review found AC041.


M5 round2 retains round1 fullgate red at FoundationIT's obsolete501 assertion. FoundationIT.AC008_invalidAdmissionAndRecoveryNeverCreateWorkAndUnauthenticatedRequestsFail now checks invalid422/error envelope, missing-target404, auth401 and six unchanged work/command/audit table counts. RecoveryCancellationIT.AC048_claimBeforeCancelRetainsPermitUntilRealTerminalObservationAndStopsNewClaims uses the independent Engine DB, real REST operation and public cancellation API. scripts/recovery_gate.py requires its actual JUnit case and ordered HTTP proof, exported to cancel-interleaving-proof.json. Source/evidence authority: M5/round-2/builder-gate-1, then root gate and fresh Reviewer; previous focused passes do not establish acceptance.


M5 round3 closes AC-041's operator entry-point gap affecting AC-045/049: RecoveryOutputProtectionIT has40 output cases (10 shapes x resolve/SKIP QUEUE/SKIP NOW/capacity refusal),8 persisted metadata cases,4 typed/replay controls and5 structural-absence controls =57 actual cases. It uses public authenticated HTTP, the real REST adapter and independent engine MariaDB; rejected requests compare execution/incident/step/attempt/admission/operator/audit/pool snapshots and retain one original external submit. scripts/recovery_gate.py requires both the non-skipped57-case report and operator-output-proof.json. Six validator tests reject missing cases, unsafe status, mutation, rejected legitimate control and shared DB proof, with a synthetic positive parser fixture explicitly separated from engine evidence. M0 negatives now60. Source authority is round3/builder-gate-1 plus root gate/closure/new fresh Reviewer; round2 review remains incomplete and M5 remains unaccepted.

M5 round4 current trace: AC-042/050 -> scripts/crash_boundary.py, all shared M3/M4/M5 crash records, and RecoveryProcesses.AC050_stoppedJvmWithRealInFlightTransactionResumesAndDrainsBeforeSnapshot. Mandatory M5 process count is9 with all four original windows unchanged. Boundary proof rejects absent stopping evidence, live writer/PID/thread mismatch, active DB transaction, event reordering, nonconsistent snapshot and changed state; missing/fake transition-drain evidence also fails. M0 GateTests now70 actual cases. Round3 source/gate references above are historical CHANGES_REQUIRED; current source authority is round4/builder-freeze.json then full Builder/root gates and fresh review. AC-041's57-case guard regression and six negatives remain required.

M5 round4 correction2 supplementary AC-006/010: RealTlsTests.test_initial_schema_future_certificate_after_verified_readiness_waits_within_original_deadline and test_initial_schema_expired_certificate_after_verified_readiness_fails_closed, plus7 FixturePolicyTests, bring startup suite to25. validate_m1_reports requires actual cases, real peer SHA match and validate_initial_schema_proof. Same90s fresh read-only COUNT preserves schemaempty/TLS/usedDB failclosed. Current authority is round4/builder-freeze-correction2.json and full builder-gate-2; earlier results historical.
