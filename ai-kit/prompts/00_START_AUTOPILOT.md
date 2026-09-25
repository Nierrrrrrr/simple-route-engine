# 一次啟動完整實作（互動式Codex用）

架構已定案。請先完整讀取AGENTS.md、ai-kit/ARCHITECTURE_CONTRACT.md、AUTONOMY_POLICY.md、
ACCEPTANCE_MATRIX.md、MILESTONES.md、DOCS_DELIVERABLES.md，並以repository實況為準。

你的任務是從零完成自建Route Engine，不是只寫設計建議。
Java/Spring Boot模組化單體+MariaDB+既有K8s，不使用Temporal或其他外部workflow/broker。
請依01_M0到07_M6、08_FINAL的prompt逐階段執行。
每階段自動plan→實作→實測→review→修正→重跑；通過才下一階段，不要詢問我是否繼續。
使用fresh-context reviewer/subagent做審查；有subagent時可獨立審查交易/故障恢復/測試安全，
但同一核心狀態機不要讓多個builder同時寫。reviewer不能代替builder改code。
沒有fresh reviewer工具時，不得說已独立審查，保留NEEDS_FRESH_REVIEW，不能給FINAL PASS。

不得削弱固定需求或測試來過關，必須真正執行MariaDB/kill-restart/local K8s/Ansible測試。
每個phase維護ExecPlan、STATE.json、TRACEABILITY與HANDOFF，証據附command/exit/raw log。
普通技術細節自行決定並記錄；只有架構衝突、必要權限/秘密、無法消除的環境問題或資源預算才停下。
每階段最多六個外部review-fix round；相同無進展故障三次停止並保存精確blocker。

不要在此session再啟動另一個無人runner，以免兩個builder同時修改repo。
目前只允許本地隔離開發測試，不許push或正式deploy。真實五條企業route未知，用DEMO明確標示。
FINAL需新context從文件完成第六條route純設定演練，原五條DEMO仍通過。
最終交付程式、測試、部署模板、操作文件、後續agent擴充文件與可重跑的驗收證據。

若context快滿/工具限制：先保存精確STATE/HANDOFF/正在失敗的測試與下一個命令，
不得把尚未完成標完成。恢復時從repository文件接續，而不是重設整個工程。
