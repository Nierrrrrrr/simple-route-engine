# M0 — 契約、環境與可恢復計畫


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


目前階段 M0：先建立可實作、可驗證、可接手的基線。
1. 查看repo與既有instruction，確認是從零還是有使用者檔案；不覆蓋不相關內容。
2. 執行tool/version/network/Docker/local K8s可行性preflight，確保所有操作只在隔離測試環境。
   tools可由workspace script bootstrap，固定下載版本與來源；需要全域管理員權限則不要偷偷取得。
3. 查官方文件選定Java21相容的GA stack，鎖版本并建立dependency inventory與來源/日期。
4. 將固定架構轉成STATE_MACHINES/TRANSACTIONS/ADR、API與DSL草稿、module map。
   特別固定manual CANCEL與running cancel差別、rollback後MANUAL_WAIT、IN_DOUBT持permit。
5. 建立M0–M6/FINAL ExecPlan目錄與STATE/TRACEABILITY/DECISIONS/HANDOFF；不要要求使用者批准一般命名。
6. 實作 scripts/verify-phase.sh 的dispatcher、真正的M0 validator與summary產生器。
   未實作phase不得return 0；M0之後每個phase由實作逐步補強，禁止stub PASS。
7. 建立scripts/doctor.sh與本地工具指引；M0不需企業正式route/秘密。
8. M0 validator須有negative self-test，刪缺欄位/壞鏈結/未滿足工具需求時確實失敗。
9. 執行M0 gate，修正，交fresh review。不要順便寫完整業務引擎。
