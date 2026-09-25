# FINAL — 獨立全案驗收


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


目前階段 FINAL：準備與执行全案工程驗收，不是再加功能。
這是新的context；先由固定契約/AC反推現況，不相信M6或前agent口頭PASS。
從乾淨build與全新local DB/kind測試資源執行全mandatory suites，包括真實Ansible與故障注入。
依docs/agent/ADD_ROUTE.md，用你這個fresh context做第六條DEMO route演練：
只新增fixture/config，用publish/execute API成功跑完；不能改任何engine Java來讓新情境通過。
若文件無法照做，記錄缺口，修文件/必要程式後把演練交下一次fresh review重新檢查。
核對actual原始log、test數量/skipped、traceability與runtime依賴；防止stub/mock被當integration。
完成docs/verification/FINAL_ACCEPTANCE.md（依證據、有source fingerprint、不宣稱正式上線）。
整理EXTERNAL_INTEGRATION_CHECKLIST，真實企業五條route與正式environment明確未驗證。
不得發布正式artifact/部署/用正式credentials。完成後交外層fresh FINAL reviewer。
最後只能在全部required checks+review通過時標ENGINEERING_ACCEPTANCE=PASS；
EXTERNAL_ACCEPTANCE=NOT_RUN、PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED。

外層runner模式：docs/verification/FINAL_ACCEPTANCE.md在fresh reviewer前只標CANDIDATE，最終PASS由runner寫至.ai-run/FINAL_RESULT.json；不要先在原始碼文件中自我授權PASS。
