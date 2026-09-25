# Route Engine：agent 工作入口

## 開始前
閱讀 `ai-kit/ARCHITECTURE_CONTRACT.md`、`ai-kit/AUTONOMY_POLICY.md`、
`ai-kit/MILESTONES.md`、`ai-kit/ACCEPTANCE_MATRIX.md`。
存在時再讀 `docs/agent/HANDOFF.md`、`docs/implementation/STATE.json` 與目前階段的 ExecPlan。
不知道的現況先查 repository，不要憑上一個 session 的摘要猜測。

## 不可變的方向
Java / Spring Boot 模組化單體 + MariaDB + 既有 Kubernetes。
不使用 Temporal，不新增 Redis、訊息 broker 或其他 workflow server。
預設 100 slots / CRITICAL 保留 20 / H:N:L=6:3:1。
狀態以 DB 為準；permit、worker lease、外部 operation identity 必須分開。
只有安全停止的 MANUAL_WAIT / 終態才釋放 permit。
外部結果不明不盲目重送；不能用 JVM 鎖或 H2 證明 DB admission 正確。

## 工作協議
每次變更：plan → 最小實作 → 真實測試 → review → 修正 → 重跑 → 更新文件。
不得刪除需求、弱化 assertion、停用測試或偽造測試輸出以取得 PASS。
架構、固定驗收需求或外部副作用安全語意有衝突才要求決策。
一般命名、套件拆分、相容的 dependency patch、SQL index 自行決定並記錄。
不得改寫 `ai-kit/` 或 `.ai-run/`；後者由外層 runner 管理。
不得擅自 push、部署正式環境、讀取正式 credentials 或清理不屬於測試的資源。
原始命令與證據放 runner 指定的 evidence 目錄；未執行不是通過。

## 最終必備文件
`docs/architecture/OVERVIEW.md`、`docs/architecture/STATE_MACHINES.md`、
`docs/architecture/TRANSACTIONS.md`、`docs/api/openapi.yaml`、
`docs/routes/DSL_REFERENCE.md`、`docs/agent/ADD_ROUTE.md`、
`docs/agent/CHANGE_ROUTE.md`、`docs/agent/ADD_ADAPTER.md`、
`docs/agent/CHANGE_ENGINE.md`、`docs/agent/TESTING.md`、
`docs/agent/HANDOFF.md`、`docs/operations/RUNBOOK.md`。

## 驗證入口（M0 建立，後续階段實作）
`bash scripts/verify-phase.sh M0 <evidence-dir>`
`bash scripts/verify-phase.sh M1 <evidence-dir>` … `M6`
`bash scripts/verify-phase.sh FINAL <evidence-dir>`
命令不存在或執行失敗時，回報實際情況，不能說已通過。
