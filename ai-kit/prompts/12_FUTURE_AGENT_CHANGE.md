# 後續接手agent任務模板

先閱讀AGENTS.md、docs/agent/HANDOFF.md以及本次修改類型的指南：
ADD_ROUTE / CHANGE_ROUTE / ADD_ADAPTER / CHANGE_ENGINE / TESTING。
固定架構與permit/transaction/外部副作用安全規則不可隨意修改。

本次需求：<在此描述新增或修改的情境；不提供生產secret>

先判斷能否純route config完成；若能，優先只新增draft/version，不改Java或runtime dependency。
若需新adapter，依已存在interface/registry/schema/版本方式擴充，明確寫submit/observe/cancel/
idempotency/retry/rollback能力，不以新增一條route為由改核心scheduler。
新增或更改route不得直接改published版本，現有queued/manual execution仍使用原definition。

列出受影響AC IDs与測試，實作→驗證→review→修正→回歸，更新文件和examples。
交付變更diff、測試commands/raw evidence、相容性說明與剩餘風險。
不自動部署正式環境；外部未驗證部分明確列出。
