# Windows 桌面版 ChatGPT / Codex 操作補充

日期：2026-09-25。此補充保留原工作包的架構、必測需求與所有原始檔案。
新增桌面入口，不代表 Application 已實作，也不代表已在你的 Windows 電腦完成驗收。

## 一次設定
1. 解壓到專用開發目錄，例如 C:\dev\route-engine。
   AGENTS.md、ai-kit/、WINDOWS_DESKTOP_START.md 要直接位於該目錄。
2. 在支援此功能的 ChatGPT 桌面版中，打開 ChatGPT 下拉選單選 Codex。
3. 新增／開啟本機專案（Windows 可用 Ctrl+O），選上述根目錄。
   這是本機程式資料夾，不是只把 ZIP 上傳到一般聊天或雲端 Project。
4. 新 Codex 對話選 Local。第一版不用 Cloud，也不需要為此新建 GitHub 遠端 repository。
5. 模型選擇你帳號實際提供的 GPT-6 Astra / Astra；prompt 不能代替模型選擇。
6. 原驗收是 Bash／Linux 工具鏈，本案建議用 WSL2。
   已有 WSL2 時，可在 Settings 的 Agent environment 選 WSL，重新啟動 app。
   Agent environment 與 Integrated terminal shell 是不同設定；只換 terminal 不代表 agent 已切換。
   尚未有 WSL2 / Docker 等工具時，先讓啟動指令檢查，不要假裝環境已通過。
7. 只授權專案範圍、必要依賴下載與隔離測試資源；保留 sandbox，不一律提升為管理員。
   Docker 等權限可能影響主機，使用沒有正式 credentials 的專用開發環境。

## 在該專案的 Codex 輸入框貼這段

```text
請讀取並執行專案根目錄 WINDOWS_DESKTOP_START.md。
使用其中的桌面版調度流程，先檢查實際環境，再自動從 M0 推進到 FINAL。
一般實作自行決定；不要每階段要求我確認，也不要啟動另一個 Python runner。
不能執行的測試或獨立審查必須保留未通過狀態，不得降低標準。
```

接續時，請讀取並執行 WINDOWS_DESKTOP_RESUME.md。

## 与原流程的差異
- 原 ai-kit/tools/run_pipeline.py 主程序沒有啟動；它標示支援 Linux / WSL / macOS。
- 主 agent 串接 phase、Builder、Reviewer；真實驗收仍使用腳本與固定 validator。
- gate 原始證據保存至 .evidence/desktop/<run-id>/。
- 最後結果保存至該 run-id 的 FINAL_RESULT.json，不是 .ai-run/FINAL_RESULT.json。
- docs/implementation/STATE.json 与 docs/agent/HANDOFF.md 是接續入口。
- 桌面 agent 不是無限持續的外部排程服務；權限、工具、額度、休眠與安全暫停仍會影響工作。
- 缺少公司實際五條 route／外部環境時，工程 DEMO 可驗證，正式整合不得宣稱已通過。

## 官方操作文件（查閱日期 2026-09-25）
以下網址為本次操作說明的來源；介面與可用功能以帳號及版本為準。

```text
https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
https://learn.chatgpt.com/docs/quickstart
https://learn.chatgpt.com/docs/windows/windows-app
https://learn.chatgpt.com/docs/environments/modes
https://learn.chatgpt.com/docs/agent-configuration/subagents
https://learn.chatgpt.com/docs/model-selection
https://learn.chatgpt.com/docs/agent-approvals-security
```
