# 驗證紀錄

本文件依 source commit `afd025fe318b1578c13e7438cf8a0a6c8dac215b` 撰寫。

核對日期：2026-09-28。這是文件與範例的限定驗證，不取代 M0–FINAL 工程驗收。

已執行：

- 在現有 Ubuntu／WSL 以 JDK 21、Maven Wrapper 直接執行 `bash ./mvnw -B -DskipTests package`，產生 JAR 並得到 BUILD SUCCESS。該命令略過測試；建置成功不代表完整 gate 通過。
- 全部 HTML Bash 區塊與 Bash 附件通過 `bash -n`；Python 附件與產生器通過語法檢查。
- 合併 SQL 的 V1～V8 各段與來源文字逐段相同，scheduler 初始 INSERT 恰好一次。此項是內容比對，不是遠端 DB 執行結果。
- 真實啟動 Python REST 服務，經 TCP 測試 true／false、相同 operation 重送、不同內容衝突、GET observe、錯誤 identity；重啟程序後仍取得原結果。
- 使用建置產物中的實際 Java `DefinitionRules` 驗證範例 route 與 input/output schema。
- 使用實際 Java `RestAdapter` 對上述服務執行兩種條件值的 submit／observe／replay。
- 實際執行 `configure.py`；用合成、無外部連線的 kubeconfig 驗證產物可被 `AdapterCatalog` 與 `KubernetesAdapter.binding` 載入；app.env 關閉 Flyway 且未保存 DB 密碼。這不是 Kubernetes Job 執行測試。
- 使用已安裝 Edge 的無頭模式檢查 1440px 桌面及 390px 手機版，無 JavaScript 錯誤、無整頁水平溢出；41 個程式碼區塊已有高亮，複製按鈕回報成功。已親自開啟桌面／手機截圖、部署圖、分支圖與 JSON 區塊確認。
- 所有 HTML 章節 anchor 與本機附件連結可解析。獨立唯讀審查已核對 API、DSL、catalog、SQL、Runner、權限及重送語意；下載／解壓縮的錯誤停止條件與文件連結已修正。

原始證據位於 repository 的 `.evidence/ubuntu-sop-20260928/`，不隨 source ZIP 交付。`build.log` 是原始建置輸出；`checks-pass.log`／`checks.json` 是範例驗證；`visual-check.json` 與 PNG 是瀏覽器檢查。初次環境檢查的舊失敗輸出保留，未當成通過。

HTML 設計規則掃描的一項 advisory 把程式碼中的 `--` CLI 選項／SQL 註解計為破折號；它不影響文件語意，未為消除此提示而修改真實指令。

遠端 MariaDB 與既有 Kubernetes／Ansible Job 端到端執行：**NOT_RUN**。使用者尚未提供這些環境與憑證，本次沒有連線或部署到它們。
