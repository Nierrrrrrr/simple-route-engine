# M4 — 真實Adapters


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


目前階段 M4：完成真正的REST、Kubernetes、Ansible三類adapters與有限failure notification。
寫明adapter submit/observe/reconcile/cancel/safeRetry/idempotency/compensation/output契約。
REST用實際HTTP fixture：202接受後輪詢、timeout、對端成功後丟回應、不可冪等未知結果。
K8s在專用local kind namespace操作真實Deployment/Job：版本/UID完成、409 conflict、failure、cancel收斂。
Ansible在真實Job跑ansible-runner對隔離fixture；保存rc/status/events及持久artifact，不能用echo代替。
穩定operation與Job identity在提交前存DB，回應丟失/worker重啟先查既有Job，不能盲目create新工作。
App Pod不是Job owner；已提交但JobGC找不到進查驗而非認定沒執行。
清楚實作transport/business/rollback三種身份規則、預防雙層retry、remote async追蹤。
notification用NATS HTTP fixture/endpointRef，有限retry，不遞迴不蓋主錯誤。
加入submit副作用完成到result落DB之間的故障注入，實測去重count。
local K8s/Docker不可用則BLOCKED，不得將mock tests提升為真實integration PASS。
累積跑M0–M4，補文件的actual classes與操作安全限制。
