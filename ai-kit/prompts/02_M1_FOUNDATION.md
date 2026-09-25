# M1 — 專案、DB與Route管理


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


目前階段 M1：建立可跑的application foundation。
依M0鎖定stack完成Maven Wrapper、Spring Boot、明確package邊界、MariaDB/Flyway。
實作核心schema、route/draft/publish/soft-delete/version lookup、error envelope、OpenAPI、audit transaction。
建立DEMO最小route資料；published不可直接update，查詢後續仍可使用原version。
提供Docker Compose或等價本地啟動與真實MariaDB整合測試；從空DB與重啟持久化都測。
不能用H2替代InnoDB語意，不能H2_PASS就說DB integration PASS。
建立step/admission/execution的必要資料模型，但沒有實作的execution行為明確拒絕，不回假的成功。
擴充verify-phase，涵蓋所有M0與M1 AC。完成後文件反映真實class/paths。
