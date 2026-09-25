# 從零實作 Route Engine：Codex Prompt Kit

這是給 Codex 的固定契約、逐階段 prompts、驗收要求與可選本地 runner。
**不是已經實作好的 Java 專案。** Java 程式、應用測試與最終agent文件會由你啟動的Codex產生。

## 你需要準備一次的事項

在專用、可丟棄的開發 VM 建立新的 Git repository，安裝並登入可使用指定模型的 Codex。
需要 Python 3.10+、Git、Bash、可用 Docker；Kubernetes測試採本機kind，不需要正式K8s憑證。
其餘Java/Maven/kind工具可由M0在workspace bootstrap，或使用事先安裝的工具。
允許下載依賴/鏡像到測試環境。不要掛載正式kubeconfig、production DB、公司SSH key或不相關檔案。

將此zip解壓至repository根目錄，確認根目錄有AGENTS.md與ai-kit/。
不要把整包放到第二層目錄，否則AGENTS自動發現與runner路徑會不對。
已有repo不能直接覆蓋既有AGENTS；本包預設從零開始，移植到既有repo需要先合併指令與基準。

## 推薦：本地CLI自動跑完整循環

模型API識別碼以你帳號實際可用為準。官方模型頁有`gpt-6-astra`，但本包不保證你的Codex工作區有該權限。
先在Codex以`/model`確認或以`codex --model gpt-6-astra`確認登入與可用性。
不支援時必須停下記錄，不能悄悄換模型。

先檢查本包與規劃（不會呼叫Codex）：

```bash
python3 ai-kit/tools/run_pipeline.py --repo . --model gpt-6-astra
```

確認是在無正式憑證的隔離VM後，啟動：

```bash
python3 ai-kit/tools/run_pipeline.py \
  --repo . \
  --model gpt-6-astra \
  --allow-network \
  --max-rounds 6 \
  --max-agent-calls 64 \
  --execute \
  --ack-isolated-environment
```

此命令會在你的機器前景執行，不是ChatGPT替你在背景維護的服務。
它依序讀取M0→M6→FINAL prompt，每個round用新的Codex session做builder與reviewer。
不需你逐階段贴prompt，也不必你看review後再手動發修正指令。
不會使用已deprecated的`--full-auto`，不會關閉sandbox，預設Codex是workspace-write + never。
`--allow-network`只為本次Codex呼叫啟用workspace網路；組織policy/沙箱仍可限制Docker等操作。
`never`表示不等人工approval，不表示獲得額外權限。必要能力未授權時，runner會明確BLOCKED。

**安全界線：** verify-phase.sh由外層Python直接執行，不受Codex的workspace sandbox保護。
Docker socket也可能提供廣泛主機權限。因此必須使用隔離VM，不能把此命令當成安全沙箱本身。
不建議用`--yolo`或移除沙箱來解決权限問題；先正確配置獨立測試環境。

## 循環與停止

每phase：fresh builder → 直接跑verify-phase → fresh reviewer → 自動回builder修正 → 重跑。
腳本檢查固定AC IDs、exit code、raw evidence是否存在、JUnit實際test cases與fail/error/skipped數，
以及驗證前後source fingerprint。reviewer不得改source。ai-kit與AGENTS的checksum不允許悄悄改。

預設每phase最多6個round，全案最多64次agent calls；每次指令上限由--timeout-seconds控制。
這些是成本/卡住防護，不是品質保證或完成時間承諾。相同無進展錯誤或超出預算會BLOCKED，不自動標PASS。
遇到API auth/model/quota、被擋的sandbox、真正架構衝突或工具失效，保留狀態後停止。
現有企業5條route內容未知不阻擋示範引擎實作，正式整合保持NOT_RUN。

## 中斷後接續

停止原runner後，用相同命令加`--resume`：

```bash
python3 ai-kit/tools/run_pipeline.py \
  --repo . --model gpt-6-astra --allow-network \
  --max-rounds 6 --max-agent-calls 64 \
  --execute --ack-isolated-environment --resume
```

resume會重驗最後完成phase，而不是相信舊PASS。
已消耗的agent calls會累計；若上限已用完，需明確提高max-agent-calls才會繼續。
不要同時開互動autopilot與runner改同一份repo；不要任意刪state讓計數歸零。

## 只用Codex互動介面

不使用runner時，完整貼入`ai-kit/prompts/00_START_AUTOPILOT.md`。
它會讀逐階段prompt與契約，盡可能自行完成全部loop。
這種方式的跨session繼續取決於Codex產品能力與資源；中斷時貼`11_RESUME.md`。
無fresh reviewer工具時需明示NEEDS_FRESH_REVIEW，不能把同session自我重看叫獨立驗收。

## 逐階段手動模式（選用）

01 M0 → 02 M1 → 03 M2 → 04 M3 → 05 M4 → 06 M5 → 07 M6 → 08 FINAL。
每階段測試完用新的session貼09 review，有問題再交原builder貼10 fix並重跑。
這只是備用，不是推薦你來回手動操作的流程。

## 結果在哪裡

- `.ai-run/state.json`：runner狀態、正在處理phase、累積agent calls、blocker。
- `.ai-run/<run-id>/.../input.md`：實際給builder/reviewer的prompt。
- `.ai-run/<run-id>/.../transcript.log`：原始Codex輸出。
- `.evidence/<run-id>/<phase-round>/verify.log`：外層實際執行的測試輸出。
- `.evidence/.../summary.json`與JUnit/XML：可機器驗證的結果。
- `.ai-run/FINAL_RESULT.json`：最終合併判定與source fingerprint。
- `docs/agent/`：後續agent實際接手文件，由各phase逐步完成。

正常最終狀態是：

```text
ENGINEERING_ACCEPTANCE=PASS
EXTERNAL_ACCEPTANCE=NOT_RUN
PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED
```

ENGINEERING_ACCEPTANCE只對當次source fingerprint與測試環境有效，不等於零bug或正式部署批准。
source修改後需要重新驗證。獨立reviewer仍使用同一模型，fresh context不等於統計完全獨立。

## 本包驗證與限制

`python3 -m unittest discover -s ai-kit/tools -p 'test_runner.py' -v`
只驗證**runner工具**，包含報表/證據/狀態/失敗回圈的test-double測試。
它不是Java application測試，不代表MariaDB/K8s/Ansible功能已經完成或驗收。
本包未在你的Codex帳號與實際repo上呼叫模型；權限/CLI版本差異由M0與runner實際報錯確認。
若CLI flags已變，先根據官方help修正工具，必須保留固定架構與原驗收要求，不能偷偷降低門檻。

模型/CLI主要官方參考見SOURCES.md，查核日期2026-09-25。
