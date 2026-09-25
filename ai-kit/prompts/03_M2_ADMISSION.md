# M2 — Admission與容量正確性


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


目前階段 M2：只把業務admission、queue與permit做正確。
實作全域pool短READ COMMITTED transaction，固定lock order，T100/R20、持久化HHHHHHNNNL。
實作POST /executions QUEUE/NOW_OR_REJECT、GET capacity、request lookup、config更新。
NOW與QUEUE用同一套priority/FIFO/WRR；NOW失敗無latent工作且不消耗權重。
實作principal-scope Idempotency-Key、request fingerprint、原結果重放與commit回應遺失處理。
permit generation獨立於worker lease，release冪等且不能釋放新permit。
以真實MariaDB測200路搶最後slot、80 noncritical硬上限、CRITICAL shared、60/30/10與restart游標。
至少兩個獨立JVM/process共用DB，不接受只有同JVM的lock test。
測DB outage、lock timeout/deadlock、非法config/縮減與重複API。
引擎尚未完成時使用測試fixture模擬permit holder，不能暴露正式『直接任意釋放slot』API。
完整跑M0–M2 gate；不要因正常happy path過了就開始M3。
