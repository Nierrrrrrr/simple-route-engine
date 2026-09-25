# Windows 桌面版 ChatGPT / Codex：實作啟動指令

本文件是使用者對「操作方式」的補充：使用桌面版 Codex 的主 agent 與子代理執行，
不啟動 Python 外層 runner。架構、必測要求、安全規則與文件交付不變。
這不是宣布 Windows 開發環境已就緒；你必須實際檢查。

## 讀取固定資料
完整讀取：
- AGENTS.md
- ai-kit/ARCHITECTURE_CONTRACT.md
- ai-kit/AUTONOMY_POLICY.md
- ai-kit/MILESTONES.md
- ai-kit/ACCEPTANCE_MATRIX.md
- ai-kit/requirements.json
- ai-kit/DOCS_DELIVERABLES.md
- ai-kit/prompts/00_START_AUTOPILOT.md

存在時讀取 docs/implementation/STATE.json、docs/agent/HANDOFF.md、目前 ExecPlan。
只以實際 checkout 為準，不能假設取得其他 ChatGPT 對話或 Project 的全部上下文。
固定 ai-kit/ 與 AGENTS.md 不改寫，.ai-run/ 仍保留給原外層 runner，不使用或偽造它。

## 先做桌面環境檢查
1. 確認工作目錄、專案檔案、Git 狀態與工作區寫入能力；保護既有使用者修改。
   若目前資料夾不是 Git repository、也不位於其他 repository 中，可以在此執行 git init。
   不修改使用者全域 Git 設定、不擅自 commit 其他人的檔案或 push。
2. 辨識目前 agent 是原生 Windows / PowerShell，還是 WSL2 / Linux。
   列出所用 shell、Windows 路徑與 Linux 路徑（適用時），確保是同一份 checkout。
3. 檢查 Git、Bash、Python、JDK、Maven Wrapper 建置可行性、Docker daemon / Linux containers、
   local kind / kubectl 與下載依賴的權限。不以 PATH 有命令就宣稱 daemon 可用。
4. 本包的驗收入口是 Bash。優先使用同一個已配置的 WSL2 發行版執行 Linux 建置與測試。
   原生 Windows agent 可透過明確的 wsl 命令執行；路徑轉換與引用必須正確。
   不把 Bash 原文直接交給 PowerShell，也不把換 shell 當成刪除驗收的理由。
5. 專案工具可在授權的 workspace-local 路徑 bootstrap，固定來源、版本並核驗下載內容。
   安裝 WSL2 / Docker、修改 OS 功能、重新開機、改全域 execution policy 或提權，
   都不能假設已獲授权。缺少時一次列出真正必要的操作與可重現檢查，保存 BLOCKED。
6. 採專用測試 kubeconfig 與本 run 的 DB / kind cluster，不讀取或使用正式 context / credentials。
   不停用 sandbox / security monitoring、不擅自切換 full access。
7. 實際確認可以啟動審查子代理；無此能力時可完成不依賴審查的準備，
   但不得把同一 agent 換一段角色文字說成獨立審查，標記 NEEDS_FRESH_REVIEW。

## 桌面版調度方式
你是主 agent，負責依序推進 M0 → M1 → M2 → M3 → M4 → M5 → M6 → FINAL。
每階段讀取 ai-kit/prompts/ 裡對應的 01 到 08 prompt，不跳過 gate。
其中「本回合只處理指定 phase」是對該階段 Builder 的範圍限制，不是要求主 agent
每階段向使用者詢問是否繼續。

本模式把原 prompt 裡「外層 runner 調度 / 指定 evidence / 整合 review」的責任
交給主 agent 和下列真實驗證流程；沒有啟動原 runner，因此不得聲稱有 CLI 外層程序監督。

每個 phase：
A. 指派一個 Builder，讀固定契約和目前 repo，plan → 實作 → 真跑測試 → 修正。
B. Builder 完成並同步必要文件後暫停所有寫入，固定受驗程式版本。
C. 實際執行 Bash 的 scripts/verify-phase.sh <phase> <evidence-dir>，
   核對 exit code、原始輸出、JUnit 實際 testcase 數、skipped 與 requirement ID 覆蓋。
D. 啟動新的 Reviewer 子代理，使用 ai-kit/prompts/09_INDEPENDENT_REVIEW.md。
   提供 phase、固定契約、repo 與證據位置；要求獨立讀程式和原始紀錄，
   不只閱讀 Builder 的結論。Reviewer 不修改程式、測試、契約或文件。
   它以新任務上下文開始；不得宣稱同模型審查具有統計上的獨立保證。
E. 缺陷交回 Builder，依 10_FIX_FINDINGS.md 修正並加 regression；重跑 gates 和新的 review。
F. 沒有必要驗收缺口且 review 通過，才更新進度並進下一 phase，不要求使用者貼「繼續」。

同一時間只有一個 Builder 寫入核心 checkout。讀取型審查可平行，但不得與受審程式寫入重疊。
不要在本桌面 session 另外執行 run_pipeline.py 的 main 或另一個 unattended Builder。
一般命名、套件拆分、索引、相容依賴版本自行決定並記錄；不重新進行架構選型。

## 證據與固定驗收器
本模式由主 agent 建立唯一 run-id，原始證據位於：
.evidence/desktop/<run-id>/<phase>/round-<n>/
此目錄已被原包 .gitignore 與 source fingerprint 排除，不放到 ai-kit/ 或 .ai-run/。
檔案內容保持 UTF-8，Shell 腳本維持可在 Linux 執行的換行與可執行入口。

每個 gate 都要檢查固定工作包的 checksum，以及本次 source fingerprint。
可以在 WSL2 / Linux 的 Python 中 import 原 ai-kit/tools/run_pipeline.py，
重用 protected_files、check_protected、source_fingerprint、validate_gate、validate_agent；
必須實際讀取這些函式的介面，不猜參數，不執行 main。
M0 建立 scripts/verify-desktop-phase.sh 等薄包裝入口，重用固定 validator、不得弱化它。
包裝器負責依原 runner 的契約向 verify-phase.sh 傳递 fingerprint 與 evidence 路徑，
並在失敗、缺檔、mandatory test skipped 或必要 AC 未驗證時回非零。
對包裝器加入反向測試：缺少證據、錯誤 fingerprint、空測試、skip、缺 AC 都必須失敗。

這提供可重跑的檢查，但不是額外的外層安全沙箱或不可繞過的自主執行保證。
不要聲稱桌面模式具有原 runner 的硬性調度/呼叫次數控制。

進度保存在 docs/implementation/STATE.json、ExecPlan、TRACEABILITY 與 docs/agent/HANDOFF.md。
這些是來源文件，修改後 fingerprint 會改變；進下一 phase 要基於新的內容重新驗證。
FINAL 前先完成所有交付文件與 CANDIDATE 驗收說明，再固定 fingerprint、測試、review。
最後結果寫到 .evidence/desktop/<run-id>/FINAL_RESULT.json，避免為了標 PASS 修改已受驗來源。
如果最後仍需修改來源或交付文件，就重跑受影響的 gates 和 review，不能沿用舊證據。

## 不可弱化的要求
架構固定：Java / Spring Boot 模組化單體 + MariaDB + 既有 Kubernetes，無 Temporal / Redis / 新 broker。
100 / 20 / 6:3:1 可配置；初始與人工 recovery 都有 QUEUE / NOW_OR_REJECT，恢復沿用原 priority。
只有 step 明確定義的 rollback 才可執行；狀態機與 cancel 細節遵守固定契約。
必須真的驗證 MariaDB、跨程序竞争、kill/restart、REST、local Kubernetes 與 Ansible Runner。
未執行不是 PASS，不能以 H2 / mock / echo PASS / 弱化 assertion 取代必要驗收。
沒有真實企業五條 route 的資料，只能交付標示為 DEMO 的情境，不聲稱已完成企業遷移。

## FINAL 與接手文件
FINAL 必須指派沒有參與實作的新驗收子代理，依 08_FINAL_ACCEPTANCE.md 執行。
驗收 agent 與只讀 Reviewer 是不同職責；第六條 DEMO route 演練所需的測試 fixture
必須放在獨立測試資源／證據目錄，不改受驗引擎 Java。
若不得不修改來源範例或文件，視為新候選版本，重跑驗收並交下一個 fresh Reviewer。

必須交付 DOCS_DELIVERABLES.md 的全部文件；特別確認：
- docs/agent/ADD_ROUTE.md：不改 Java 新增、驗證、發布並執行第六條 route。
- docs/agent/CHANGE_ROUTE.md：新版本不影響舊 execution。
- docs/agent/ADD_ADAPTER.md：實際 extension points、恢復契約與測試。
- docs/agent/HANDOFF.md、TESTING.md、CHANGE_ENGINE.md：真實路徑與可跑命令。

## 中斷與資源邊界
每階段最多六個外層 review/fix 回合；同一問題三次沒有進展則保存 BLOCKED_STALLED。
主 agent 在 STATE 記錄實際回合與已知的 agent 呼叫；平台額度與安全限制仍依工具執行。
不能降低驗收來續跑，也不能承諾本機關閉、休眠或工具停止後還會自行執行。
真實阻礙時保存：已完成階段、失敗命令/exit、證據路徑、最小解除操作、接續指令。
不因為正常階段切換詢問使用者；涉及必要權限、安全或固定架構衝突才停止。

完成時以實際證據回報：
ENGINEERING_ACCEPTANCE=PASS 或 NOT_PASS
EXTERNAL_ACCEPTANCE=NOT_RUN
PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED
附 FINAL_RESULT.json、source fingerprint、主要證據與接手文件路徑。

現在開始環境檢查與 M0；具備必要能力就持續執行，不要只回覆計畫。
