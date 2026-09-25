# 自主實作、審查與停止政策

## 自行決策
架構已定，不重新比較技術方案。一般 code organization、class 命名、索引、框架用法、
相容 dependency patch、local fixtures、測試資料、非業務性錯誤訊息由 agent 決定，寫 ADR 即可。
不得每個 phase 完成就詢問『是否繼續』。外層 runner 決定下一階段；單 session 模式可依序自動前進。

## 每階段循環
1. 讀契約/目前 repo，建立該階段 ExecPlan 與需求→測試映射。
2. 必須先有可失敗的測試或可重現條件，再實作最小可行範圍。
3. 執行 unit/integration/該階段 acceptance；修正所有必測 failures。
4. reviewer 用新 session/context 審查，引用實際檔案、符號、需求 ID 與重現方法。
5. 實作 agent 修正缺陷並添加 regression；重跑所有該階段與前階段 gates。
6. 測試與 review 都符合，更新狀態/接手文件；否則保留精確 blocker，不偽造 PASS。

每階段 builder 可先做至多三次本地修正；外層預設至多六個 build/test/review round，
總 agent 呼叫上限 64，可由使用者調整。這是資源上限，不是『六次仍失敗也算成功』。
相同無進展故障三次或超過預算，回報 BLOCKED_STALLED，保存重現和下一步，不一直燒額度。

## 可以真正停止的情況
固定契約矛盾、安全完成必須改變業務語意；需要未授權的 secret/外部環境/付費服務；
工具、網路、Docker/本地 K8s 權限在允許範圍無法使用；資料損毀/正式部署等未授權操作；
工具額度、上下文、成本/round budget、時間上限，或同一故障無進展。
缺少企業五條真實 route 不阻礙 DEMO 引擎開發，但不允許聲稱已驗證正式整合。

## 權限邊界
只修改 repository 與授權 workspace-local caches。只建立本 run 專用的容器、測試 DB、
kind cluster、namespace/PVC/Job；所有資源带 run-id，清理只限已驗證屬於該 run 的資源。
不能讀取 ~/.kube 下正式 contexts、其他 repo、production DB、SSH 私鑰或不相關秘密。
不能 git push、force push、reset --hard、刪除使用者檔案或執行生產 migration/deploy。
本地專案可以 commit（明確 paths，不含 secrets/evidence）；不得把 commit 當成測試證據。

CLI unattended 建議 workspace-write + never，預先在隔離開發 VM 配置需要的 network/Docker 權限。
never 不會增加 sandbox 權限；被擋下應回報，不可自动改成 full access / yolo。
外層 runner 執行測試腳本不在 Codex sandbox 內，Docker socket 也可有廣泛權限，
因此只在專用、可丟棄、沒有正式資料的 dev VM 使用此 runner。
認證使用 Codex 已保存的登入；不要把 API key 放 repo 或全域提供給生成的 build scripts。

## 不得作弊
不能刪需求/改固定 ai-kit、跳過 mandatory tests、把 disabledIfDockerUnavailable 當通過、
mock MariaDB/Job 卻說已做真實 integration、把 echo PASS 當 validator、只讀測試而聲稱執行、
改測試預期迎合錯誤實作、吞 assertion、任意 UPDATE permit_held 修補不變量。
合法修改測試須指出原測試與契約不符的原因，保留同 requirement 的等價或更強驗證，交 reviewer 檢查。

## 信心與範圍
fresh reviewer 仍可能漏錯；它不是不同模型的統計獨立保證，也不是人工/安全審核替代品。
沒有任何 prompt 能保證零 bug 或永遠不中斷。以可重跑腳本、真實輸出與具範圍的 gate 作結論。
