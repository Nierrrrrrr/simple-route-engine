# M5 — 人工Recovery


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


目前階段 M5：完整人工恢復，但不交由使用者代替你跑loop。
實作recovery API，RETRY/SKIP/ROLLBACK/CANCEL均支援QUEUE/NOW_OR_REJECT，沿用原priority。
incident/execution鎖與pending recovery唯一；NOW拒絕保持MANUAL_WAIT無side effect。
QUEUE放行前重驗incident，舊incident/重複key/兩個不同action並發只有一個有效。
RETRY只重做失敗step/branch；SKIP驗證downstream required output。
ROLLBACK預設拒絕，限定當前合法step、有定義才執行；成功回MANUAL_WAIT，補償失敗retry不跑forward。
manual CANCEL要經其admission；running cancel使用原permit，等外部停止才釋放；queue撤回不創新工作。
提供具evidence/audit的未知operation resolve，禁止把resolve當force retry/force release。
做入隊/放行/執行/釋放各點crash、舊generation延遲抵達、兩人工指令race tests。
累積跑M0–M5，所有失敗修正後再交review，不把未通過項目留到M6『再說』。
