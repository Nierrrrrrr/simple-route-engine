# M3 — 持久化Route Engine


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


目前階段 M3：實作有限能力的DB-backed Route Engine，不做Temporal replay。
完成順序、受控when/condition、一層parallel ALL_SETTLED、persisted context/output/branch choices。
每次只推進一小段：短交易認領/intent→I/O在外→短交易結果+後續待辦+event。
retry存next_action_at/attempt/budget，不用sleep thread當唯一狀態，等待仍占permit。
實作lease/fencing、DB掃描reconciler、safe manual boundary、IN_DOUBT保留permit。
此phase adapter使用可控制的test fixture/受限開發adapter，明確不得冒充M4外部整合。
做真正子程序kill/restart測試，不只new Service()：step完成到next pending、branch執行中、retry等待。
用injectable clock驗證6小時行為，另做短wall-clock integration；不要把虛擬時間叫6小時soak。
測不同execution例外隔離/有界executor/parallel輸出無shared mutable state。
M0–M3全累積gate；確認沒有業務worker根據lease timeout自動回收permit。
