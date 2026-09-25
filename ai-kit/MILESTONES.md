# Milestones

這是本次自建版本的編號，不假設其他對話的M0–M6已實作。

| Phase | 範圍 | Prompt |
|---|---|---|
| M0 契約、環境與可恢復計畫 | 工具preflight、ADR、state machine、OpenAPI/DSL草稿、ExecPlan、verify報表入口。 | `ai-kit/prompts/01_M0_CONTRACT_AND_PLAN.md` |
| M1 專案、DB與Route管理 | Spring Boot/Maven、MariaDB migrations、route/version APIs、audit與local啟動。 | `ai-kit/prompts/02_M1_FOUNDATION.md` |
| M2 Admission與容量正確性 | 100/20/6:3:1、原子NOW/QUEUE、冪等、permit generation、跨程序競態。 | `ai-kit/prompts/03_M2_ADMISSION.md` |
| M3 持久化Route Engine | 順序/條件/parallel、durable retry、manual boundary、leases與crash恢復。 | `ai-kit/prompts/04_M3_ENGINE.md` |
| M4 真實Adapters | REST、Kubernetes、Ansible Job、外部未知、通知與artifacts。 | `ai-kit/prompts/05_M4_ADAPTERS.md` |
| M5 人工Recovery | RETRY/SKIP/ROLLBACK/CANCEL的兩種mode、incident一致性與回收。 | `ai-kit/prompts/06_M5_RECOVERY.md` |
| M6 加固、部署與交接文件 | 安全/維運/升級/完整文件/五條DEMO/重啟與全累積回歸。 | `ai-kit/prompts/07_M6_DELIVERY.md` |
| FINAL 獨立全案驗收 | 第六route演練、乾淨重建、fault matrix、fresh審查与最終範圍結論。 | `ai-kit/prompts/08_FINAL_ACCEPTANCE.md` |


每個phase：plan→build→實測→fresh review→fix→再測；未通過不进入下phase。
M0只做契約/工具/計畫，不能謊称已具備M1引擎。
後階段可以做必要相容修改，但必須重跑所有前置gates。
FINAL builder準備clean-room演練與交付；FINAL reviewer只審查，不改實作。
外層runner若在review發現錯誤會交回builder並重跑；使用者不用手動貼fix prompt。
