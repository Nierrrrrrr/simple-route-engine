# Ubuntu 本機部署 SOP

以瀏覽器開啟 [index.html](index.html)。HTML 本身可離線閱讀，不使用 CDN；保留旁邊的 `files/` 可下載 SQL 與可執行範例。可用目錄跳轉、複製程式碼及列印。

涵蓋 Ubuntu 24.04／Java 21 直接啟動、既有遠端 MariaDB 手動 DDL／初始 DML、真實 REST 範例服務、既有 Kubernetes 上的 Ansible Runner Job、if／else、curl 發布與觸發，以及排錯、重送與停止。

目前 Ansible adapter 需要 Kubernetes，不支援由 Java 直接呼叫 Ubuntu 的 ansible-playbook。此 SOP 不建立 Docker MariaDB 或 Docker Java，也不建立本機 kind。

附件：

- `01-database-and-users.sql`：DBA 建庫及帳號／權限模板。
- `02-schema-v1-v8.sql`：完整 V1～V8 migrations，含唯一必要的 scheduler seed。
- `03-verify-database.sql`：schema、TLS、seed 的只讀查詢。
- `migration-source-sha256.json`：來源 migration SHA-256。
- `kubernetes.yaml`：namespace、PVC、RBAC 模板。
- `configure.py`、`start-java.sh`：本機設定產生與 Java 啟動。
- `rest-example.py`：符合本專案 operation protocol 的 loopback REST 範例。
- `example-route.json`、`publish.sh`、`trigger.sh`、`poll.sh`：route 與 curl 操作。

驗證結果及未執行範圍見 [VERIFICATION.md](VERIFICATION.md)。重新產生 HTML：在 repository 根目錄執行 `python3 docs/user/ubuntu-local-sop/build_sop.py`。
