# M6 — 加固、部署與交接文件


先讀根目錄 AGENTS.md 與 ai-kit 中的固定契約、自治政策、驗收矩陣及文件清單，
再讀實際 repository、既有 HANDOFF / STATE / ExecPlan。不要依賴聊天摘要當現況。
本回合只處理指定 phase 和必要前置修正，不擅自跳過 gate 或重新選型。
不需要問一般實作問題；自行決策並記錄。需要改固定契約或缺必要權限才 BLOCKED。
先建需求→失敗案例→測試映射，再實作；真跑測試、修錯、重跑，不能停在列出計畫。
不得修改 ai-kit/ 或 .ai-run/。遵守外層指定 evidence 路徑與 structured result。
完成時更新 docs/implementation/STATE.json、該phase ExecPlan、TRACEABILITY 與 HANDOFF。
state只記錄事實；外層runner執行驗證與fresh review後才是本phase通過。
最終訊息使用外層 JSON schema；沒有schema時列 phase、實際commands/exits/evidence、尚存findings、blockers。
不得聲稱生產驗收或正式部署已授權。


目前階段 M6：工程交付前加固與文件，不擅自接正式環境。
完成caller/operator/admin、production fail-closed auth、secret redaction、endpoint/namespace/playbook allowlists。
完成metrics/readiness/runbook、single-replica Recreate manifests、graceful stop與SIGKILL恢復、持久artifacts。
使用DB migration/舊state fixture測新engine仍保持舊route/人工等待語意；完整dependency inventory與固定images。
提供真實可跑的local scripts/CI pipeline（可用Azure DevOps pipeline或平台中立shell），CI不需正式秘密。
依DOCS_DELIVERABLES逐一完成，actual file/symbol/command全部驗證，產生AGENT prompt templates。
提供五條清楚標DEMO的route涵蓋REST/condition/parallel/Ansible/K8s，不能聲稱就是公司五條實際流程。
準備clean-room第六條route驗證脚本；範例沒有未知endpoint就用fixture。
先完成M0–M6所有mandatory tests、fault cases、文件鏈結/schema/版本驗證，P0/P1/P2清零。
最後更新source狀態與handoff，工程環境之外的驗收清楚NOT_RUN，production未授權。
