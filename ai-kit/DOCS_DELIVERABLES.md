# 文件是驗收項目，不是收尾備註

## 固定入口
根目錄 AGENTS.md 已提供，不需覆寫；最終必須確保其中鏈結皆存在且正確。
根目錄 README.md：架構摘要、需求、如何啟動、如何測試、DEMO/外部未驗證範圍。

## 架構與契約
- docs/architecture/OVERVIEW.md：模組責任、資料流、runtime dependency inventory。
- docs/architecture/STATE_MACHINES.md：execution/step/attempt/recovery/permit 狀態與合法 transition 表。
- docs/architecture/TRANSACTIONS.md：各操作交易界線、lock order、isolation、CAS/fencing、idempotency。
- docs/architecture/FAILURE_RECOVERY.md：crash 點、外部未知、reconcile、不能保證的事情。
- docs/adr/：版本選擇、DSL 邊界、不可逆變更与其原因，不能替代使用者批准的架構變更。
- docs/api/openapi.yaml：實際一致的 schema、errors、auth、idempotency、curl examples。
- docs/routes/DSL_REFERENCE.md：完整 grammar/JSON schema、每個 node、when、parallel、failure/rollback。

## 給下一位 AI agent
- docs/agent/HANDOFF.md：從哪讀、每個 feature 實際在哪個 package/file/symbol、目前 gates、限制與 known issues。
- docs/agent/ADD_ROUTE.md：不改 Java 新增第六條 route；引用現成節點、validate/draft/publish/execute，附真實可跑命令。
- docs/agent/CHANGE_ROUTE.md：v1→v2、固定舊 execution、新預設版本、停用、撤回未發布、API 相容性。
- docs/agent/ADD_ADAPTER.md：interface/registration/DSL schema/version/retry/idempotency/observe/cancel/rollback、安全與測試。
- docs/agent/CHANGE_ENGINE.md：狀態/DB migration、lock order、舊 execution 相容、必重跑的 AC IDs。
- docs/agent/TESTING.md：各命令、必需環境、failure injection、log 報表、如何新增 requirement test。
- docs/agent/PROMPT_TEMPLATES.md：新增 route、改 route、加 adapter、修 race 的可直接貼用 prompts。

## 維運
- docs/operations/RUNBOOK.md：啟動/暫停 admission/關機/重啟、IN_DOUBT 查驗、人工 recovery、config 修改。
- docs/operations/SECURITY.md：RBAC、secret references、endpoint/namespace allowlists、rotation、禁止操作。
- docs/operations/DEPLOYMENT.md：local kind 與 production template 的差別、PVC/migrations、backup/restore 檢查。
- docs/operations/EXTERNAL_INTEGRATION_CHECKLIST.md：企業五條 route/REST/NATS/VM credential/正式 K8s 等未提供項目。

## 文件品質門檻
必須寫實際存在的相對路徑、class/interface 名稱、copy/paste 可用命令，不能只有通用建議。
禁止 TBD/TODO 假裝已完成；真正外部未提供項明確標 EXTERNAL_NOT_RUN。
每次 milestone 同步文件，最終 reviewer 驗證鏈結、examples schema 與 OpenAPI 和實作一致。
做 clean-room handoff：用 fresh agent 只讀 repository 文件，新增 DEMO route-6、發布並執行；
只允許新增 example/fixture，不改引擎 Java，原始五條 DEMO 不受影響。
另檢查 adapter extension checklist 指向實際 extension point，不必為了演練增加正式不需要的新 protocol。
