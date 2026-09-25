# FINAL ExecPlan

Status: NOT_STARTED. Scope: Fresh acceptance agent, isolated clean rebuild, route6 config-only handoff, fault matrix and fresh independent review.

## Requirement to failing scenario

| ID | Required proof / failure condition | Planned test |
|---|---|---|
| AC-059 | 重新建置並跑所有mandatory suites，無fail/error/skip/NOT_RUN；真實MariaDB與kind/Ansible證據存在。 Failure of any clause must fail the gate. | FinalAcceptanceTest + fresh Reviewer (planned) |
| AC-060 | fresh session從固定需求反推code/test/故障路徑，P0/P1/P2與mandatory缺口全部關閉，只有有理由的P3可記錄。 Failure of any clause must fail the gate. | FinalAcceptanceTest + fresh Reviewer (planned) |
| AC-061 | fresh session只讀repo文件，純新增fixture/config發布執行DEMO route6，不改任何引擎Java；前五route回歸。 Failure of any clause must fail the gate. | FinalAcceptanceTest + fresh Reviewer (planned) |
| AC-062 | 提交前後/回應遺失/落DB前後/parallel/manual/recovery crash點皆有實測，6小時虛擬時鐘與非soak界線清楚。 Failure of any clause must fail the gate. | FinalAcceptanceTest + fresh Reviewer (planned) |
| AC-063 | 需求ID→測試→命令→原始log/報表→source fingerprint完整，沒有硬編碼success或篡改驗收器。 Failure of any clause must fail the gate. | FinalAcceptanceTest + fresh Reviewer (planned) |
| AC-064 | ENGINEERING_ACCEPTANCE=PASS只在全部滿足；EXTERNAL_ACCEPTANCE=NOT_RUN、PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED。 Failure of any clause must fail the gate. | FinalAcceptanceTest + fresh Reviewer (planned) |

## Execution sequence

1. Read fixed prompt and actual previous-phase evidence.
2. Add a failing test for each requirement and bounded crash/negative cases.
3. Implement minimum compatible behavior and update actual file/symbol mappings.
4. Run this phase and every previous gate, preserve raw logs/JUnit.
5. Freeze source; fresh reviewer reads code and evidence; fix findings and repeat within six rounds.
6. Update handoff and STATE without claiming later stages passed.

Command: `bash scripts/verify-desktop-phase.sh FINAL .evidence/desktop/$ROUTE_RUN_ID/FINAL/round-1/gate`.
Currently this dispatcher intentionally fails because this phase is unimplemented. No test result exists yet.
