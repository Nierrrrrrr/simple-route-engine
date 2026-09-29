#!/usr/bin/env python3
"""Build the offline Traditional Chinese SOP from its executable attachments."""
from pathlib import Path
import hashlib
import html
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILES = HERE / 'files'

# Preserve the migration text and order; do not synthesize a final schema.
migrations = sorted((ROOT/'src/main/resources/db/migration').glob('V*__*.sql'), key=lambda p: int(p.name.split('__')[0][1:]))
combined = '-- Fresh empty database only. Stop on the first SQL error. Do not use --force.\nSET NAMES utf8mb4;\nSET time_zone = \'+00:00\';\n\n'
for path in migrations:
    combined += f'-- BEGIN SOURCE {path.name}\n{path.read_text(encoding="utf-8").strip()}\n-- END SOURCE {path.name}\n\n'
(FILES/'02-schema-v1-v8.sql').write_text(combined.rstrip()+'\n', encoding='utf-8', newline='\n')
(FILES/'migration-source-sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in migrations}, indent=2)+'\n', encoding='utf-8')

def esc(s): return html.escape(str(s))
count = 0
def code(text, lang='bash', title=None):
    global count
    count += 1
    return f'<div class="code"><div class="codebar"><span>{esc(title or lang)}</span><button type="button" class="copy" data-code="code-{count}" aria-label="複製程式碼區塊 {count}">複製</button></div><pre tabindex="0"><code id="code-{count}" data-lang="{lang}">{esc(text.strip())}</code></pre></div>'
def attachment(name, lang):
    return f'<p class="filelink"><a href="files/{name}" download>下載 {name}</a></p>'+code((FILES/name).read_text(encoding='utf-8'),lang,name)
def note(title, text, kind='note'):
    return f'<aside class="{kind}"><strong>{title}</strong><p>{text}</p></aside>'
sections=[]
def section(id, title, body): sections.append((id,title,body))

section('scope','00｜先看部署範圍', '''
<p class="lead">在 Ubuntu 直接建置與啟動 Java，連上既有的遠端 MariaDB，發布一條包含 REST、Ansible 與 if / else 的 route，最後用 curl 觸發並確認完成。</p>
<div class="topology" role="img" aria-label="curl 呼叫 Ubuntu 的 Java API，Java 連線遠端 MariaDB、Ubuntu REST 範例服務及既有 Kubernetes Ansible Job">
<div class="local-zone"><span class="zone-label">你的 Ubuntu 主機</span><div class="node small">curl<span>建立・發布・觸發</span></div><div class="arrow">↓ HTTP :8080</div><div class="node engine">Route Engine<span>Java 21 / Spring Boot</span><small>127.0.0.1:8080</small></div><div class="arrow">↓ HTTP :9081</div><div class="node small">REST 範例服務<span>Python 3・僅 loopback</span></div></div>
<div class="connections"><span>JDBC + TLS →</span><span>Kubernetes API →</span></div>
<div class="remote-zone"><div class="node remote">既有遠端 MariaDB<span>route_engine_sop</span><small>引擎狀態、版本、排隊、稽核</small></div><div class="node remote">既有 Kubernetes<span>Ansible Runner Job</span><small>probe playbook + 持久化 PVC</small></div></div></div>
<p class="caption">圖 1　Java 與 MariaDB 均不使用 Docker。Ansible Job 在既有 Kubernetes 的容器執行環境內執行。</p>
'''+note('必要前提：Ansible 需要既有 Kubernetes','目前程式的 <code>ANSIBLE</code> 節點會建立 Kubernetes Job，<strong>不支援直接呼叫 Ubuntu 的 ansible-playbook</strong>。只安裝 Java、遠端 MariaDB 與本機 Ansible，無法完成這個範例。若沒有可用的叢集、Runner 映像與 PVC，請先完成第 04 節；這不是可用環境變數切換的模式。','important')+'''
<p>本文以 <strong>Ubuntu 24.04 LTS、Bash、Java 21</strong> 為操作基準。Java／MariaDB 的服務都不透過 Docker 啟動；本機不建立 kind、不安裝 Docker daemon。Ansible 的 localhost 指的是 <strong>Job Pod 內部</strong>，不是你的 Ubuntu，也不是遠端正式機器。</p>
<table><thead><tr><th>元件</th><th>本 SOP 的使用方式</th></tr></thead><tbody>
<tr><td>Java / Spring Boot</td><td>JDK 21；由 Maven Wrapper 建置；直接 <code>java -jar</code></td></tr>
<tr><td>MariaDB</td><td>使用既有遠端服務上的專用空白 database；來源版本基準為 11.4.13，其他版本先驗證 migrations</td></tr>
<tr><td>REST</td><td>附可執行的 Python 範例服務，實際走 HTTP operation protocol</td></tr>
<tr><td>Ansible</td><td>既有 Kubernetes + 本專案 Runner 映像；包裝的 probe playbook</td></tr>
<tr><td>輸出</td><td>HTML 可離線閱讀；SQL、JSON、YAML、Python 與 Bash 附件；語法高亮與複製按鈕</td></tr>
</tbody></table>
<p>本手冊與附件依目前 source commit <code>afd025fe318b1578c13e7438cf8a0a6c8dac215b</code> 核對，撰寫日期 2026-09-28。本文的「預期結果」是你執行後要驗證的內容，並非已連線到你的環境。</p>
''')

section('prepare','01｜準備環境與取得原始碼','''
<h3>1.1　先向管理員取得這些資料</h3>
<table><thead><tr><th>項目</th><th>要取得的值</th><th>用途</th></tr></thead><tbody>
<tr><td>MariaDB</td><td>DNS 名稱、port、CA 憑證、DBA / migration / app 帳號</td><td>建表、TLS 連線；DBA 放行 Ubuntu 對外 IP</td></tr>
<tr><td>Kubernetes</td><td>專用 kubeconfig、context、測試 namespace、可用 StorageClass</td><td>建立 Job、查詢 Pod、保存 Runner 產物</td></tr>
<tr><td>Runner 映像</td><td>可拉取的 <code>registry/repo@sha256:…</code></td><td>必須包含本專案 entrypoint 與 playbooks</td></tr>
<tr><td>網路</td><td>Ubuntu → DB / K8s；建置端 → Maven Central；K8s 節點 → registry</td><td>各連線須獨立可達；本機 REST 不必對外公開</td></tr>
</tbody></table>
<h3>1.2　Ubuntu 安裝本機工具</h3>
<p>下列命令只安裝 MariaDB <strong>client</strong>，不安裝 MariaDB server。<code>openjdk-21-jdk</code> 用於編譯與執行；Maven 版本由專案 Wrapper 管理。</p>
'''+code('''sudo apt-get update
sudo apt-get install -y openjdk-21-jdk git curl jq python3 \
  mariadb-client unzip ca-certificates openssl nano
java -version
javac -version
python3 --version
mariadb --version''')+'''
<p class="expect">確認 <code>java</code> 與 <code>javac</code> 都是 21。若機器有多個 JDK，先用 <code>sudo update-alternatives --config java</code> 與 <code>sudo update-alternatives --config javac</code> 選擇 21。</p>
<h3>1.3　解壓縮交付的 source code</h3>
<p>可使用隨本手冊交付的原始碼 ZIP，或以下方的 Git 方式取得原始碼。將交付的 <code>route-engine-ubuntu-sop.zip</code> 放到 Ubuntu 的 <code>~/Downloads</code>。ZIP 包含原始碼及本手冊；不含本機帳密、build cache 或 evidence。請使用尚不存在的目的資料夾。</p>
'''+code('''mkdir -p "$HOME/work"
test ! -e "$HOME/work/simple-route-engine" || { echo '目的資料夾已存在，請另選新路徑後重新開啟 Bash'; exit 1; }
# 上一步成功才繼續；不要覆蓋既有 checkout。
unzip "$HOME/Downloads/route-engine-ubuntu-sop.zip" -d "$HOME/work" || exit 1
cd "$HOME/work/simple-route-engine" || exit 1
export PROJECT_DIR="$PWD"
test -f pom.xml && test -f .mvn/wrapper/maven-wrapper.jar || exit 1
test -f docs/user/ubuntu-local-sop/files/example-route.json || exit 1
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
bash ./mvnw -version''')+'''
<details><summary>改從 Git 儲存庫下載</summary><p>本專案的儲存庫為 <a href="https://github.com/Nierrrrrrr/simple-route-engine">Nierrrrrrr/simple-route-engine</a>。<code>REPO_URL</code> 可填入 <code>https://github.com/Nierrrrrrr/simple-route-engine.git</code>，或你有權限讀取的公司鏡像網址；選用的分支／commit 必須包含本手冊與 V1～V8。ZIP 的引擎 source commit 如上；Git 版本請以 <code>git rev-parse HEAD</code> 記錄實際下載的 commit。</p>'''+code('''read -r -p 'Git repository URL: ' REPO_URL
git clone "$REPO_URL" "$HOME/work/simple-route-engine" || exit 1
cd "$HOME/work/simple-route-engine" || exit 1
export PROJECT_DIR="$PWD"
git rev-parse HEAD
ls src/main/resources/db/migration/V*__*.sql''')+'''</details>
<h3>1.4　建立本次操作目錄</h3><p>以下步驟都在同一個 Bash 視窗執行，直到手冊明確要求另開終端機。設定與認證檔放在使用者自己的目錄；不寫入版本控制。</p>
'''+code('''umask 077
export SOP_HOME="$HOME/route-engine-sop"
mkdir -p "$SOP_HOME" "$SOP_HOME/logs" "$SOP_HOME/requests"
export SOP_FILES="$PROJECT_DIR/docs/user/ubuntu-local-sop/files"
printf '%s\\n' "$PROJECT_DIR" > "$SOP_HOME/project-path.txt"''')+'''
<p>此處固定使用 <code>route_engine_sop</code> 作為 database、<code>ubuntu-rest-ansible-demo</code> 作為 route ID。若你要改名稱，請同步修改 SQL、設定產生器與腳本；第一次建議保留。</p>''')

section('database','02｜遠端 MariaDB：DDL 與必要 DML','''
<h3>2.1　由 DBA 建立專用 database 與帳號</h3>
<p>在既有 MariaDB 服務上新增<strong>空白、專用</strong> database。將下列模板的三種 <code>CHANGE_ME</code> 全部替換。Host 應是 MariaDB 看得到的 Ubuntu 對外來源 IP（含 NAT 後位址），不是 localhost。兩個密碼請不同。</p>
'''+attachment('01-database-and-users.sql','sql')+'''
<p>這一段含 DDL 與權限設定 DCL。帳號建立交給 DBA；不要把管理員帳號用來啟動 Java。schema migration 會建立 trigger，若遠端啟用 binary log 或限制 DEFINER，DBA 必須依政策代為匯入或授權；不要自行更動整台 DB 的設定。保留 trigger 的 DEFINER 帳號，勿在建表後直接刪除它。</p>
<h3>2.2　設定連線並先驗證 TLS</h3>
<p>取得 MariaDB CA 檔後，放到 <code>$SOP_HOME/mariadb-ca.pem</code>。請填憑證所涵蓋的 DNS 名稱；下方 <code>db.example.internal</code> 是需替換的範例。</p>
'''+code('''export SOP_DB_HOST='db.example.internal'   # 改成實際 DNS 名稱
export SOP_DB_PORT='3306'
export SOP_DB_CA="$SOP_HOME/mariadb-ca.pem"
test -s "$SOP_DB_CA"
mariadb --host="$SOP_DB_HOST" --port="$SOP_DB_PORT" \
  --user=re_sop_migrate --password \
  --ssl-ca="$SOP_DB_CA" --ssl-verify-server-cert \
  --database=route_engine_sop \
  --execute="SELECT VERSION(), DATABASE(); SHOW SESSION STATUS LIKE 'Ssl_cipher'; SHOW TABLES;"''')+'''
<p class="expect">密碼會互動輸入。<code>Ssl_cipher</code> 應有值，<code>SHOW TABLES</code> 應沒有任何表。若連線或驗證失敗，先修正 DNS、CA、來源 IP、port 或權限。</p>
<h3>2.3　匯入完整 V1～V8</h3>
<p><a href="files/02-schema-v1-v8.sql" download>下載完整 02-schema-v1-v8.sql</a>。這不是省略版示意 SQL，而是按順序合併 source 的八個 migrations（包含 <code>DELIMITER</code>、foreign key、check、index 與 trigger）。唯一必要的初始 DML 是 V1 的 <code>INSERT INTO scheduler_pool(id) VALUES(1);</code>，已包含在檔案中，<strong>不要再執行一次</strong>。</p>
'''+code('''# 再次確認是空白專用 database，且前一步無錯誤。
mariadb --host="$SOP_DB_HOST" --port="$SOP_DB_PORT" \
  --user=re_sop_migrate --password \
  --ssl-ca="$SOP_DB_CA" --ssl-verify-server-cert \
  --database=route_engine_sop \
  < "$SOP_FILES/02-schema-v1-v8.sql"''')+note('SQL 執行失敗時就停止','MariaDB 的多數 DDL 會隱含 commit，整份匯入並非單一可回復交易。請保留錯誤，讓 DBA 檢查已套用的位置；不要加 <code>--force</code>、反覆重跑整份檔案或直接在既有環境重建。若這是可拋棄的新 database，由 DBA 確認後重新提供空白 database。')+'''
<table><thead><tr><th>版本</th><th>用途</th></tr></thead><tbody>
<tr><td>V1 / V2</td><td>Route、版本、執行、step、attempt、稽核、容量初始資料與 FIFO</td></tr>
<tr><td>V3 / V4</td><td>持久化 retry、incident 與外部 operation identity</td></tr>
<tr><td>V5 / V6</td><td>Adapter plan、停止意圖、發布版本的 adapter binding</td></tr>
<tr><td>V7 / V8</td><td>Recovery / operator command 與維運查詢索引</td></tr>
</tbody></table>
<h3>2.4　確認 schema 與 seed</h3>
'''+code('''mariadb --host="$SOP_DB_HOST" --port="$SOP_DB_PORT" \
  --user=re_sop_migrate --password \
  --ssl-ca="$SOP_DB_CA" --ssl-verify-server-cert \
  --database=route_engine_sop \
  < "$SOP_FILES/03-verify-database.sql"''')+attachment('03-verify-database.sql','sql')+'''
<p class="expect">預期有 12 個 InnoDB 業務表、11 個 trigger；非 InnoDB 查詢為空。scheduler_pool 只有 id=1：100 slots、保留 20、權重 6:3:1、cursor 0、configVersion 0、admission_enabled=1。</p>
'''+note('手動 schema 模式必須關閉 Flyway','第 06 節會設定 <code>SPRING_FLYWAY_ENABLED=false</code>。本次沒有建立 <code>flyway_schema_history</code>；若保留預設自動 migration，啟動會遇到非空 schema／缺少歷史紀錄錯誤。不要用 <code>baseline-on-migrate</code> 隨意略過。未來升級由 DBA 依已記錄版本套用新增 migration；若要轉為 Flyway 管理，須先逐項比對 schema，再另行規劃 baseline。','important')+'''
<p>route、route version、execution 與 adapter binding 都透過 API 建立；不用手寫 DML 灌入 published route 或更改 permit。這些資料涉及 hash、版本不可變規則及稽核。</p>
<details><summary>展開完整 schema SQL（較長）</summary>'''+code(combined,'sql','02-schema-v1-v8.sql')+'''</details>''')

section('build','03｜直接建置 Java JAR','''
<p>回到 Ubuntu 的原始碼目錄。第一次建置會下載 Maven 3.9.11 與依賴；目前 source 固定 Spring Boot 3.5.16、MariaDB JDBC 3.5.8、Flyway 11.8.2。</p>
'''+code('''cd "$PROJECT_DIR"
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
bash ./mvnw -B -Dmaven.repo.local="$PROJECT_DIR/.cache/m2" -DskipTests package
test -s target/route-engine-0.1.0.jar
ls -lh target/route-engine-0.1.0.jar''')+'''
<p class="expect">Maven 最後應顯示 <code>BUILD SUCCESS</code>，並產生 <code>target/route-engine-0.1.0.jar</code>。這裡的 <code>-DskipTests</code> 是單純封裝，不代表測試或完整工程驗收通過。完整專案 gate 需要獨立的測試環境；本 SOP 不啟動其 Docker／kind 測試基礎設施。</p>
''')

section('kubernetes','04｜準備 Ansible Runner 與既有 Kubernetes','''
<h3>4.1　安裝相容的 kubectl</h3>
<p>若平台已提供 kubectl，可略過安裝。否則請向管理員取得與 API server 相容的確切版本（kubectl 通常須在 server 的前後一個 minor 版本內），再執行：</p>
'''+code('''read -r -p 'kubectl 版本，例如 v1.36.4（須符合你的叢集）: ' KUBECTL_VERSION
[[ "$KUBECTL_VERSION" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]] || { echo '版本格式不正確'; exit 1; }
ARCH=$(dpkg --print-architecture)
mkdir -p "$SOP_HOME/downloads" "$HOME/.local/bin"
cd "$SOP_HOME/downloads"
curl --fail --location --output kubectl \
  "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/$ARCH/kubectl" || exit 1
curl --fail --location --output kubectl.sha256 \
  "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/$ARCH/kubectl.sha256" || exit 1
printf '%s  kubectl\\n' "$(cat kubectl.sha256)" | sha256sum --check || exit 1
# 只有 checksum 通過才安裝。
install -m 0755 kubectl "$HOME/.local/bin/kubectl"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_DIR"''')+'''
<h3>4.2　使用平台提供的專用 kubeconfig</h3>
<p>把 kubeconfig 放到 <code>$SOP_HOME/kubeconfig</code>，權限 600。這份檔案必須讓在 Ubuntu 執行的 Fabric8 Java client 也能驗證；若使用 exec credential plugin，相關程式必須存在於 Java 的 PATH。不要拿平台管理員 kubeconfig 長期當成應用程式身分。</p>
'''+code('''export SOP_KUBECONFIG="$SOP_HOME/kubeconfig"
chmod 600 "$SOP_KUBECONFIG"
kubectl --kubeconfig="$SOP_KUBECONFIG" config get-contexts
read -r -p '本次專用 context 名稱: ' SOP_KUBE_CONTEXT
export SOP_KUBE_CONTEXT
export SOP_NAMESPACE='route-engine-sop'
kubectl --kubeconfig="$SOP_KUBECONFIG" --context="$SOP_KUBE_CONTEXT" version''')+'''
<h3>4.3　取得本專案的 Runner 映像</h3>
<p>此映像必須包含 <code>/opt/route/entrypoint.py</code>、<code>playbooks/probe.yml</code> 與鎖定版本的 Ansible Runner。<strong>任意 ansible 或 Python 官方 image 不能直接替代。</strong>平台若已建置本 source 的 Runner，直接填入可拉取的 digest；不要使用浮動 tag。</p>
'''+code('''read -r -p 'Runner 映像（registry/repo@sha256:完整 digest）: ' RUNNER_IMAGE
export RUNNER_IMAGE
[[ "$RUNNER_IMAGE" =~ @sha256:[a-f0-9]{64}$ ]]''')+'''
<details><summary>沒有既有 Runner 映像：用 Buildah 建置（不需 Docker daemon）</summary>
<p>此步驟可交給有權限的建置端／CI；須有 registry push 權限。Buildah 只建置 Runner，沒有把 Java 或 MariaDB 容器化。CPU 架構須符合排程到的 Kubernetes 節點；跨架構請由平台產出合適映像。若 rootless user namespace 被主機政策限制，請交由平台建置，不要關閉安全機制。</p>
'''+code('''sudo apt-get install -y buildah uidmap fuse-overlayfs
cd "$PROJECT_DIR"
read -r -p '映像 repository，例如 registry.example.internal/tools/route-runner: ' RUNNER_REPO
read -r -p 'Registry 主機，例如 registry.example.internal: ' REGISTRY_HOST
buildah login "$REGISTRY_HOST"
buildah bud -f config/runner/Dockerfile -t "$RUNNER_REPO:ubuntu-sop" config/runner
buildah push --digestfile "$SOP_HOME/runner-image.digest" \
  "$RUNNER_REPO:ubuntu-sop" "docker://$RUNNER_REPO:ubuntu-sop"
export RUNNER_IMAGE="$RUNNER_REPO@$(cat "$SOP_HOME/runner-image.digest")"
printf '%s\\n' "$RUNNER_IMAGE"''')+'''
<p><code>docker://</code> 是 Buildah 的 registry transport 名稱，不會啟動 Docker daemon。若 registry 私有，平台必須先讓 namespace 的 default ServiceAccount 設定適當的 imagePullSecrets，或讓節點具備 pull 權限；目前 catalog 沒有可指定 imagePullSecrets 的欄位。</p></details>
<h3>4.4　namespace、PVC 與 RBAC</h3>
<p>下載下面的 YAML，交由平台管理員套用。先替換 StorageClass 與 kubeconfig 的實際 User identity；context 名稱不一定等於 username。若是 ServiceAccount 身分，subjects 必須改成 <code>kind: ServiceAccount</code> 並補上其 namespace。</p>
'''+attachment('kubernetes.yaml','yaml')+'''
<p>範例選擇 <strong>ReadWriteMany</strong>，讓多個 Job 即使落在不同節點也能寫同一份 PVC。若只有 ReadWriteOnce，先請平台提供合適的共享儲存方案；不要假設兩個 Job 必定排到同一節點。StorageClass／檔案系統須支援 UID/GID 1000 與 fsGroup 1000 寫入。這是附件 YAML 中要依環境調整的值。</p>
'''+code('''# 以下由平台管理員使用「其已授權的 context」執行。
# 請先編輯副本並替換 CHANGE_ME；不要直接套用模板。
cp "$SOP_FILES/kubernetes.yaml" "$SOP_HOME/kubernetes.yaml"
nano "$SOP_HOME/kubernetes.yaml"
read -r -p '平台管理員 kubeconfig 絕對路徑: ' PLATFORM_KUBECONFIG
read -r -p '平台管理員 context: ' PLATFORM_CONTEXT
kubectl --kubeconfig="$PLATFORM_KUBECONFIG" --context="$PLATFORM_CONTEXT" \
  apply -f "$SOP_HOME/kubernetes.yaml"
# PVC 可能因 WaitForFirstConsumer 暫時 Pending，第一個 Job 建立後才繫結。
kubectl --kubeconfig="$PLATFORM_KUBECONFIG" --context="$PLATFORM_CONTEXT" \
  -n "$SOP_NAMESPACE" get pvc runner-artifacts''')+'''
<h3>4.5　建立 probe 使用的非機密示範 Secret</h3>
<p>目前 probe playbook 會確認 <code>/run/route-secrets/value</code> 非空，因此 <code>secretName</code> 不能漏掉。這裡放的是明確的測試字串；真實機密不要貼進 route input。</p>
'''+code('''kubectl --kubeconfig="$PLATFORM_KUBECONFIG" --context="$PLATFORM_CONTEXT" \
  -n "$SOP_NAMESPACE" create secret generic runner-probe \
  --from-literal=value=local-sop-probe-only

# 切回 Java 實際使用的身分，確認權限。以下每個結果都應為 yes。
kubectl --kubeconfig="$SOP_KUBECONFIG" --context="$SOP_KUBE_CONTEXT" \
  -n "$SOP_NAMESPACE" auth can-i create jobs.batch
kubectl --kubeconfig="$SOP_KUBECONFIG" --context="$SOP_KUBE_CONTEXT" \
  -n "$SOP_NAMESPACE" auth can-i get jobs.batch
kubectl --kubeconfig="$SOP_KUBECONFIG" --context="$SOP_KUBE_CONTEXT" \
  -n "$SOP_NAMESPACE" auth can-i delete jobs.batch
kubectl --kubeconfig="$SOP_KUBECONFIG" --context="$SOP_KUBE_CONTEXT" \
  -n "$SOP_NAMESPACE" auth can-i list pods''')+'''
<p>Java 建立的 Job Pod 不掛載 Kubernetes token。建立 Job 的是 Ubuntu 上 kubeconfig 的身分；不是 Pod 裡的預設 ServiceAccount。Job 保留至引擎確認結果，不要用自動清理工具提早刪除。</p>
<h3>4.6　Ansible 實際做了什麼</h3>
'''+code((ROOT/'config/runner/playbooks/probe.yml').read_text(),'yaml','config/runner/playbooks/probe.yml')+'''
<p>它在 Pod 的 localhost 檢查檔案引用、寫入 <code>/tmp/route-engine-probe</code>，並輸出無機密的完成訊息。Runner 的 <code>rc</code>、<code>status</code>、<code>stdout</code> 與 <code>job_events</code> 保存在 PVC 的 operationId 目錄。現有 adapter 不會將 route input 傳成任意 extra-vars，也不支援讓 route 填遠端 inventory、自訂 shell 或 playbook 路徑。</p>''')

section('rest','05｜啟動真實 REST 範例服務','''
<p>REST adapter 使用固定 operation protocol。引擎 POST 的 JSON 含 <code>operationId</code>、<code>direction</code>、<code>operationGeneration</code>、<code>input</code>；對端須回傳相同 operationId 與終態。普通 <code>{"ok":true}</code> 或單純 HTTP 200 並不足以讓引擎判定成功。</p>
'''+code('''{
  "operationId": "由引擎提供的 UUID",
  "status": "SUCCEEDED",
  "output": {"allowed": true, "message": "Check requested branch"}
}''','json','回應格式示意，operationId 必須與請求一致')+'''
<p>附件 <a href="files/rest-example.py" download>rest-example.py</a> 使用 Python 標準函式庫，提供 POST /operations 與 GET /operations/{operationId}。相同 operationId 與內容重送會回傳原結果；結果存在 <code>rest-state</code>，重啟服務後仍可查。這些檔案是範例外部服務的 operation 紀錄，不是 Route Engine 的狀態資料庫。</p>
<h3>終端機 A：讓 REST 服務持續執行</h3>
'''+code('''# 另開一個 Bash 視窗執行；保留原本的設定視窗。
export SOP_HOME="$HOME/route-engine-sop"
export PROJECT_DIR="$(cat "$SOP_HOME/project-path.txt")"
python3 "$PROJECT_DIR/docs/user/ubuntu-local-sop/files/rest-example.py" \
  --port 9081 --state-dir "$SOP_HOME/rest-state"''')+'''
<h3>回到原設定視窗：確認服務</h3>
'''+code('''curl --fail-with-body --silent --show-error http://127.0.0.1:9081/health | jq .''')+'''
<p class="expect">應回傳 <code>{"status":"UP"}</code>。此服務只綁定 loopback，沒有開放至外部網路；它是教學用 API，不是通用業務系統 gateway。保留同一份 rest-state，直到所有執行完成並完成證據查驗。</p>''')

section('configure','06｜設定認證、catalog 與 Java 連線','''
<h3>6.1　建立本機管理員 token</h3>
<p>範例用單一管理員執行建立／發布／觸發，方便完整演練。Java 只取得 SHA-256；curl 用權限 600 的設定檔帶入原 token，避免直接把 token 寫在命令列參數。不要啟用 shell <code>set -x</code>。</p>
'''+code('''umask 077
# 只在第一次建立，重啟時沿用原 token。
test -s "$SOP_HOME/admin-token.txt" || openssl rand -hex 32 > "$SOP_HOME/admin-token.txt"
printf 'header = "Authorization: Bearer %s"\\n' \
  "$(cat "$SOP_HOME/admin-token.txt")" > "$SOP_HOME/curl-auth.conf"
chmod 600 "$SOP_HOME/admin-token.txt" "$SOP_HOME/curl-auth.conf"''')+'''
<h3>6.2　產生 catalog 與 app.env</h3>
<p>確認第 01～04 節設定的變數仍在原 Bash 視窗中。設定產生器會檢查 image digest、讀取 probe 的 SHA-256，並寫出可重載的本機設定；DB 密碼稍後啟動時才互動輸入。</p>
'''+code(''': "${PROJECT_DIR:?}" "${SOP_HOME:?}" "${SOP_DB_HOST:?}" "${SOP_DB_CA:?}"
: "${SOP_KUBECONFIG:?}" "${SOP_KUBE_CONTEXT:?}" "${SOP_NAMESPACE:?}" "${RUNNER_IMAGE:?}"
python3 "$SOP_FILES/configure.py"
source "$SOP_HOME/session.env"
jq . "$SOP_HOME/adapter-catalog.json"''')+'''
<table><thead><tr><th>設定</th><th>含義</th></tr></thead><tbody>
<tr><td>ROUTE_DB_URL</td><td>JDBC + <code>sslMode=verify-full</code> + CA 檔案；同時驗證主機名稱</td></tr>
<tr><td>ROUTE_DB_USER</td><td><code>re_sop_app</code>；只給日常 DML 權限</td></tr>
<tr><td>SPRING_FLYWAY_ENABLED=false</td><td>資料表已透過第 02 節手動建立</td></tr>
<tr><td>ROUTE_ADAPTERS_CONFIG</td><td>部署者控管的 catalog，route 只能引用名稱</td></tr>
<tr><td>ROUTE_BIND_ADDRESS / ROUTE_PORT</td><td><code>127.0.0.1:8080</code></td></tr>
<tr><td>ROUTE_ENGINE_ENABLED / ROUTE_SCHEDULER_ENABLED</td><td>都為 true，持久化工作會被自動掃描執行</td></tr>
</tbody></table>
<p>這裡使用真正的 REST 與 Kubernetes adapters，無須 <code>engine-development</code> profile，也不引用 <code>dev.success</code>。若外部 shell 已設定其他 Spring profile、datasource 或 Flyway 變數，請先確認不會覆蓋這組設定。</p>
<details><summary>查看設定產生器的完整內容</summary>'''+attachment('configure.py','python')+'''</details>
'''+note('發布後不要直接改 catalog 目標','發布時會凍結 adapter 的語意與 kubeconfig 雜湊。修改 image、playbook、namespace、endpoint 或 kubeconfig 檔案內容後，既有 published／queued execution 可能因 binding drift 進入 IN_DOUBT。即使只是 credential 更新導致 kubeconfig 內容變更，也應先處理既有工作並規劃新版本；不要以釋放 permit 或更換請求 key 繞過。')+'''
<h3>6.3　終端機 B：直接啟動 Java</h3>
'''+code('''export SOP_HOME="$HOME/route-engine-sop"
source "$SOP_HOME/session.env"
bash "$PROJECT_DIR/docs/user/ubuntu-local-sop/files/start-java.sh"''')+'''
<p>輸入 <code>re_sop_app</code> 的 MariaDB 密碼。腳本載入 app.env，最後直接執行 <code>java -jar target/route-engine-0.1.0.jar</code>。視窗會停留在前景輸出；保留執行。DB 密碼只放在這個程序的環境，不寫到 app.env。</p>
<h3>6.4　原設定視窗：檢查 ready 與接單狀態</h3>
'''+code('''source "$SOP_HOME/session.env"
curl --fail-with-body --silent --show-error "$API_BASE/actuator/health/readiness" | jq .
curl --fail-with-body --silent --show-error --config "$SOP_HOME/curl-auth.conf" \
  "$API_BASE/capacity" | tee "$SOP_HOME/capacity.json" | jq .''')+'''
<p class="expect">readiness 為 <code>UP</code>；capacity 的 <code>admissionEnabled</code> 為 true。<strong>Ready 只表示 Java／DB 可服務，不代表 Kubernetes、PVC 或 Runner 已驗證成功</strong>；後面的 true 分支才會實際檢驗這些項目。</p>
<details><summary>如果既有專用 database 的 admissionEnabled 是 false</summary><p>先確認沒有其他操作者正在維護，再用 API 更新。讀取最新 configVersion、保留當下容量與權重；不要直接 UPDATE scheduler_pool。</p>'''+code('''curl --fail-with-body --silent --show-error --config "$SOP_HOME/curl-auth.conf" \
  "$API_BASE/capacity" > "$SOP_HOME/capacity.json"
jq '{totalSlots,criticalReserved,highWeight,normalWeight,lowWeight,configVersion,
     admissionEnabled:true,reason:"Enable isolated Ubuntu SOP demo"}' \
  "$SOP_HOME/capacity.json" > "$SOP_HOME/enable.json"
curl --fail-with-body --silent --show-error --config "$SOP_HOME/curl-auth.conf" \
  -X PUT -H 'Content-Type: application/json' --data-binary "@$SOP_HOME/enable.json" \
  "$API_BASE/capacity/config" | jq .''')+'''</details>''')

section('route','07｜理解並發布 example route','''
<div class="route-diagram" role="img" aria-label="prepare REST 後判斷 allowed，true 走 Ansible probe，false 走 REST recordSkip，最後都走 finish REST">
<div class="flow-step">prepare <b>REST</b><small>input.runAnsible → output.allowed</small></div><div class="flow-arrow">↓</div>
<div class="flow-condition">if steps.prepare.allowed == true</div>
<div class="fork"><div><span class="branch-tag">then · true</span><div class="flow-step yes">runProbe <b>ANSIBLE</b><small>既有 K8s 上執行 probe</small></div></div><div><span class="branch-tag">else · false</span><div class="flow-step">recordSkip <b>REST</b><small>記錄本次未要求 Ansible</small></div></div></div>
<div class="flow-arrow">↓ 任一分支完成後</div><div class="flow-step">finish <b>REST</b><small>Route finished</small></div></div>
<p class="caption">圖 2　第一次用 true，確保 Ansible 確實執行；第二次用 false，驗證 else。</p>
<p>CONDITION 的 <code>then</code>／<code>else</code> 會保存選擇，重啟不會重新挑分支。prepare 明確宣告 boolean 輸出型別及 required 欄位，讓條件引用能通過 DSL validation。finish 不讀取僅在其中一個分支才存在的輸出。</p>
'''+attachment('example-route.json','json')+'''
<h3>7.1　curl 依序建立 route、草稿、發布</h3>
<p>下列附件是完整可執行命令：先 POST /routes，接著以 <code>{"definition": ...}</code> 包住 JSON 建草稿，最後使用草稿回傳的 stateVersion 發布。不能把裸 definition 當成建立 route 的 body。</p>
'''+attachment('publish.sh','bash')+code('''source "$SOP_HOME/session.env"
bash "$PROJECT_DIR/docs/user/ubuntu-local-sop/files/publish.sh"''')+'''
<p class="expect">首次建立與草稿 API 為 HTTP 201；發布 API 為 HTTP 200。最後輸出應有 <code>status: "PUBLISHED"</code> 與 <code>version: 1</code>。API 會把 route 的預設版本指到最新發布版；trigger 腳本還會明確指定 routeVersion。</p>
'''+note('publish.sh 只用於首次建立','若 route ID 已存在，腳本會在 409 停止。不要將所有 409 當成成功。先 GET route 與 versions 確認執行到哪裡；若已有草稿，使用該草稿的 stateVersion 完成發布。若要修改已發布內容，建立 version 2 的新草稿並同步修改 definition.version，再發布；既有 execution 保留原版。')+'''
<h3>7.2　確認發布結果</h3>
'''+code('''curl --fail-with-body --silent --show-error --config "$SOP_HOME/curl-auth.conf" \
  "$API_BASE/routes/ubuntu-rest-ansible-demo/versions/1" \
  | jq '{routeId,version,status,definitionHash}' ''')+'''
''')

section('trigger','08｜用 curl trigger，驗證 if 與 else','''
<h3>8.1　先執行 true 分支</h3>
<p>腳本先保存請求 body 與 key，再執行 curl。下列 POST 是真正的觸發方式；<code>QUEUE</code> 代表沒容量時可排隊，HTTP 202 只代表接單，不代表 route 已完成。</p>
'''+attachment('trigger.sh','bash')+code('''source "$SOP_HOME/session.env"
bash "$PROJECT_DIR/docs/user/ubuntu-local-sop/files/trigger.sh" true
cp "$SOP_HOME/last-request.txt" "$SOP_HOME/true-request.txt"''')+'''
<p class="expect">應收到 HTTP 202，body 中有 <code>executionId</code> 與 admission 決策。key、body、response、HTTP headers 均保存在這次的 requests 子目錄。</p>
<h3>8.2　查到 SUCCEEDED，且 permit 已釋放</h3>
'''+code('''bash "$PROJECT_DIR/docs/user/ubuntu-local-sop/files/poll.sh"''')+'''
<p>poll.sh 每 2 秒 GET /executions/{id}，最多觀察約 6 分鐘（HTTP 呼叫時間另計）。成功條件是 <code>state=SUCCEEDED</code> 且 <code>permitHeld=false</code>。遇到 RECONCILING、MANUAL_WAIT 或失敗終態會停止觀察並提示檢查；不會自動重送、刪除 Job 或改資料庫。</p>
<h3>8.3　確認 Ansible Job 的結果</h3>
'''+code('''kubectl --kubeconfig="$SOP_KUBECONFIG" --context="$SOP_KUBE_CONTEXT" \
  -n "$SOP_NAMESPACE" get jobs,pods \
  -l route-engine.run-id=ubuntu-sop -o wide''')+'''
<p class="expect">在只有這次操作的專用 namespace，true 分支會建立一個 <code>re-&lt;operationId&gt;</code> Job；應顯示 Complete／1/1，Pod 為 Succeeded。Job 的 operationId 與 executionId 是不同身分，不可混用。此 template 的 activeDeadlineSeconds 為 300、backoffLimit 為 0；若拉映像／掛載儲存耗時過久，Job 可能失敗。</p>
<h3>8.4　再執行 false 分支</h3>
'''+code('''# 等 true 分支成功再執行，這是另一個明確的新 execution。
bash "$PROJECT_DIR/docs/user/ubuntu-local-sop/files/trigger.sh" false
cp "$SOP_HOME/last-request.txt" "$SOP_HOME/false-request.txt"
bash "$PROJECT_DIR/docs/user/ubuntu-local-sop/files/poll.sh"''')+'''
<p class="expect">第二個 execution 也應 SUCCEEDED、permitHeld=false；它會執行 prepare → recordSkip → finish，不應新增 Ansible Job。</p>
<h3>8.5　用只讀 SQL 確認實際選中的分支</h3>
<p>execution API 不回傳所有 step 明細，因此這裡用 SELECT 查詢，不憑 Job 數量猜測。請先驗證 ID 格式；將上面的 true／false execution 分別檢查。</p>
'''+code('''ATTEMPT=$(cat "$SOP_HOME/true-request.txt")  # 查 else 時改為 false-request.txt
EXECUTION_ID=$(cat "$ATTEMPT/execution-id.txt")
[[ "$EXECUTION_ID" =~ ^[a-f0-9-]{36}$ ]] || { echo 'execution ID 格式錯誤'; exit 1; }
mariadb --host="$SOP_DB_HOST" --port="$SOP_DB_PORT" \
  --user=re_sop_app --password --ssl-ca="$SOP_DB_CA" --ssl-verify-server-cert \
  --database=route_engine_sop --execute="
SELECT node_id,state,branch_choice,output_json
FROM step_runs WHERE execution_id='$EXECUTION_ID'
ORDER BY ordinal_number,node_id;
SELECT r.node_id,a.operation_id,a.external_uid,a.state
FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id
WHERE r.execution_id='$EXECUTION_ID';"''')+'''
<table><thead><tr><th>請求</th><th>decision.branch_choice</th><th>應存在且成功的 leaf steps</th></tr></thead><tbody>
<tr><td>runAnsible=true</td><td>then</td><td>prepare、runProbe、finish</td></tr>
<tr><td>runAnsible=false</td><td>else</td><td>prepare、recordSkip、finish</td></tr>
</tbody></table>
<p>未選中的分支不會被展開成 step_run；不能要求它一定顯示 SKIPPED。true 分支的 runProbe output 會包含 <code>artifacts.pvc</code> 與 operationId 目錄 <code>artifacts.path</code>。</p>
<h3>8.6　查驗 Runner 的持久化產物</h3>
<p>請平台管理員透過既有 PVC 檔案檢視工具或受控維運 Pod，以<strong>唯讀</strong>方式掛載 <code>runner-artifacts</code>。查閱剛才 operationId 目錄下的 <code>rc</code>（應為 0）、<code>status</code>（successful）、<code>stdout</code>（含 route-engine-probe-complete）與 job_events。Runner 使用 quiet 模式，<code>kubectl logs</code> 可能沒有完整輸出；不能把空 log 當成 Ansible 未執行。</p>
''')

section('retry','09｜回應遺失與重送規則','''
<p>如果 POST /executions 逾時、斷線或回 503，先保留原請求目錄。<strong>不要再次執行 trigger.sh</strong>，因為那會建立新 key。先用同一 principal 查原 key 的 admission decision：</p>
'''+code('''ATTEMPT=$(cat "$SOP_HOME/last-request.txt")
KEY=$(cat "$ATTEMPT/key.txt")
curl --fail-with-body --silent --show-error --config "$SOP_HOME/curl-auth.conf" \
  --get --data-urlencode "key=$KEY" "$API_BASE/admission-requests" | jq .''')+'''
<p>需要重送時，沿用完全相同的 key、body 與認證身分。請確認 ATTEMPT 是那次失去回應的請求，尤其你已經跑過其他分支時。</p>
'''+code('''curl --fail-with-body --silent --show-error --config "$SOP_HOME/curl-auth.conf" \
  -D "$ATTEMPT/retry-headers.txt" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(cat "$ATTEMPT/key.txt")" \
  --data-binary "@$ATTEMPT/body.json" "$API_BASE/executions" \
  > "$ATTEMPT/retry-response.json"
jq . "$ATTEMPT/retry-response.json"
jq -er '.executionId' "$ATTEMPT/retry-response.json" > "$ATTEMPT/execution-id.txt"
# 如果要使用 poll.sh，把該請求目錄重新指定為目前觀察對象。
printf '%s\\n' "$ATTEMPT" > "$SOP_HOME/last-request.txt"
bash "$PROJECT_DIR/docs/user/ubuntu-local-sop/files/poll.sh"''')+'''
<p>同 key、不同 body 會 409。若原本的 NOW_OR_REJECT 因容量而明確被拒絕，原 key 重送仍會回原拒絕；只有明確決定發起另一次工作時，才用新 key。<code>IN_DOUBT</code> 是 operation／incident 狀態，execution 常見為 <code>RECONCILING</code>，permit 會保留；外部結果不明不代表「沒執行」。</p>
''')

section('troubleshoot','10｜排錯與重啟','''
<table><thead><tr><th>看到的現象</th><th>先檢查什麼</th></tr></thead><tbody>
<tr><td>Java 編譯 release 21 不支援</td><td>java / javac / JAVA_HOME 是否一致指向 JDK 21</td></tr>
<tr><td>DB Access denied / connection timeout</td><td>來源 IP grant、帳密、DNS、3306 防火牆與網路；用同一個 app 帳號測試</td></tr>
<tr><td>DB TLS / hostname validation 失敗</td><td>CA、DNS 是否匹配憑證；不要直接停用憑證驗證</td></tr>
<tr><td>非空 schema／找不到 Flyway history</td><td>手動建表模式應為 SPRING_FLYWAY_ENABLED=false；不要混用自動 migrate</td></tr>
<tr><td>Table / column 不存在</td><td>V1～V8 是否完整成功；是否連錯 database；保留第一個 SQL 錯誤</td></tr>
<tr><td>Invalid adapter catalog</td><td>JSON 拼字、絕對路徑、image@digest、namespace、pvc、playbook=probe、可讀 kubeconfig</td></tr>
<tr><td>401 / 403</td><td>curl config 原 token 與 Java hash 是否匹配；角色是否具有發布或維運權限</td></tr>
<tr><td>422 發布失敗</td><td>sop.rest / sop.probe 是否存在且類型正確；definition body、version、stateVersion、input 型別</td></tr>
<tr><td>QUEUED 很久</td><td>admissionEnabled、容量與原排隊順序；不是手動增加 permit 的理由</td></tr>
<tr><td>RECONCILING / IN_DOUBT</td><td>REST operation protocol、服務是否存活、K8s 網路/RBAC、catalog drift、Job 是否被刪</td></tr>
<tr><td>Job Pending / ImagePullBackOff</td><td>映像 digest／節點架構／pull 權限；PVC 與 RWX；資源配額與 admission policy</td></tr>
<tr><td>Job Failed / MANUAL_WAIT</td><td>runner-probe Secret key=value 是否存在；PVC 可寫；Runner image 是否含正確套件與檔案；300 秒 deadline</td></tr>
</tbody></table>
<h3>10.1　讀取應用程式 log 與 incidents</h3>
'''+code('''tail -n 100 "$SOP_HOME/logs/route-engine.log"
ATTEMPT=$(cat "$SOP_HOME/last-request.txt")
EXECUTION_ID=$(cat "$ATTEMPT/execution-id.txt")
curl --fail-with-body --silent --show-error --config "$SOP_HOME/curl-auth.conf" \
  "$API_BASE/executions/$EXECUTION_ID/incidents" | jq .
kubectl --kubeconfig="$SOP_KUBECONFIG" --context="$SOP_KUBE_CONTEXT" \
  -n "$SOP_NAMESPACE" get jobs,pods -l route-engine.run-id=ubuntu-sop''')+'''
<p>若需 events、logs 或 describe，而應用程式 kubeconfig 未授權，請平台操作員用自己的權限檢查指定 Job／Pod。不要為排錯直接給 Java cluster-admin。</p>
<h3>10.2　重啟順序</h3>
<ol><li>保留 MariaDB、catalog、kubeconfig、token、rest-state、Job 與 PVC。</li><li>確認 REST 範例服務在 9081 啟動；沿用原 rest-state。</li><li>Java 視窗以 Ctrl+C 停止；需要再啟動時，source session.env，再執行 start-java.sh。</li><li>確認 readiness 後，查詢<strong>原 executionId</strong>；不必重建 route 或再次 trigger。</li></ol>
<p>執行中的外部 Job 不會因 Java 重啟就被當作失敗，也不會因 worker lease 到期自動釋放 permit。需要人工 recovery 時，先確認外部結果，依 <a href="../../operations/RUNBOOK.md">RUNBOOK</a> 與 API 契約處理；本 SOP 不提供強制釋放 SQL。</p>
''')

section('finish','11｜完成條件與停止方式','''
<div class="checklist">
<label><input type="checkbox"> 遠端專用 database 已完成 V1～V8，seed 與 schema 查詢符合預期。</label>
<label><input type="checkbox"> Java 直接啟動，readiness=UP，admissionEnabled=true。</label>
<label><input type="checkbox"> example route 已 PUBLISHED，固定版本與 definitionHash 可查。</label>
<label><input type="checkbox"> true 分支 SUCCEEDED、permitHeld=false，Job Complete，Ansible 產物可讀。</label>
<label><input type="checkbox"> false 分支 SUCCEEDED、permitHeld=false，DB 中 branch_choice=else。</label>
<label><input type="checkbox"> 保存兩次的 executionId、key、body、response 與必要證據。</label>
</div>
<p class="caption">勾選只協助閱讀與記錄，不會連線或執行任何部署，也不代表自動驗證。</p>
<h3>停止與保留資料</h3>
<p>先等兩次 execution 都完成；在 Java 的終端機 B 按 Ctrl+C，再在 REST 的終端機 A 按 Ctrl+C。保留 database、PVC、rest-state 與請求紀錄，方便重啟與追蹤。這兩個服務在前景執行，關閉視窗會停止它們；本文件未設定開機自啟。</p>
<p>若要清理教學資源，先用 SELECT 確認專用 DB 中沒有持有 permit 或尚未收斂的 execution，再由平台確認 namespace 僅有本次測試資源後移除其 Job／Secret／PVC；PVC 可能依回收政策刪除資料。DB 刪除由 DBA 執行。不要用廣域刪除指令或在存在未知外部工作時清理。</p>
<h3>本份交付的驗證界線</h3>
<p>驗證紀錄見 <a href="VERIFICATION.md">VERIFICATION.md</a>。我們可核對 source、建置 JAR、驗證範例 DSL／腳本、實際呼叫 REST fixture 並檢查 HTML；你的遠端 DB、Kubernetes、registry 與憑證尚未提供，因此<strong>完整部署與 Ansible Job 端到端執行尚未在你的環境驗證</strong>。請以上述完成條件逐項判定。</p>
<h3>來源與延伸閱讀</h3>
<ul class="sources">
<li><a href="https://ubuntu.com/developers/docs/howto/java-setup/">Ubuntu：Java 開發環境</a></li>
<li><a href="https://mariadb.com/docs/connectors/mariadb-connector-j/using-tls-ssl-with-mariadb-java-connector">MariaDB：Connector/J TLS 設定</a></li>
<li><a href="https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/">Kubernetes：Linux kubectl 安裝</a>、<a href="https://kubernetes.io/releases/version-skew-policy/">版本相容政策</a></li>
<li><a href="https://github.com/podman-container-tools/buildah/blob/main/docs/buildah-build.1.md">Buildah build</a>、<a href="https://github.com/podman-container-tools/buildah/blob/main/docs/buildah-push.1.md">push 與 digestfile</a></li>
<li>專案實作：<code>src/main/resources/application.yaml</code>、<code>db/migration/V1…V8</code>、<code>AdapterCatalog.java</code>、<code>KubernetesAdapter.java</code>、<code>RestAdapter.java</code>、<code>RouteController.java</code>、<code>AdmissionController.java</code>。</li>
</ul>
''')

CSS = r'''
:root{--ink:#172a43;--muted:#526379;--blue:#194fb8;--pale:#edf3fc;--line:#cdd8e6;--nav:#142a46;--code:#14243b;--green:#217158;--paper:#fff;--body:#f4f7fb}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:32px}body{margin:0;color:var(--ink);background:var(--body);font-family:"Noto Sans TC","Microsoft JhengHei","PingFang TC",sans-serif;font-size:16px;line-height:1.85}a{color:var(--blue);text-underline-offset:4px}a:hover{text-decoration-thickness:2px}button,input{font:inherit}button{cursor:pointer}button:focus-visible,a:focus-visible,summary:focus-visible,input:focus-visible,pre:focus-visible{outline:3px solid #e2a438;outline-offset:4px}.skip{position:fixed;top:-100px;left:20px;z-index:50;background:white;padding:10px}.skip:focus{top:10px}
.rail{position:fixed;left:0;top:0;bottom:0;width:260px;background:var(--nav);color:#eaf2ff;padding:34px 22px;overflow:auto}.brand{font-size:21px;font-weight:750;letter-spacing:.03em;line-height:1.3;margin-bottom:12px}.brand small{display:block;font-size:12px;font-weight:400;margin-top:10px;color:#bbcee8;letter-spacing:0}.edition{font-size:12px;color:#c0d0e5;padding:16px 0 22px;border-bottom:1px solid #466079}.rail nav{margin-top:20px}.rail nav a{display:block;color:#cbd8eb;text-decoration:none;padding:8px 10px;margin:3px 0;border-radius:5px;font-size:14px;line-height:1.7}.rail nav a:hover,.rail nav a.active{background:#274767;color:#fff}.rail-bottom{font-size:12px;color:#bccde1;margin-top:30px}.print{background:transparent;border:1px solid #7e99b6;color:#fff;padding:6px 12px;border-radius:5px;width:100%;margin-top:12px}
main{margin-left:260px;padding:52px clamp(24px,5vw,90px) 80px;max-width:1440px}.masthead{display:flex;justify-content:space-between;gap:20px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:16px;font-size:13px;color:var(--muted)}.masthead strong{color:var(--blue)}h1{font-size:clamp(32px,3.5vw,49px);line-height:1.35;letter-spacing:-.025em;margin:38px 0 18px;font-weight:800}h1 span{display:block;color:var(--blue)}.subtitle{font-size:18px;color:var(--muted);max-width:720px}.chips{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0 40px}.chips span{background:#e6edf8;color:#24486d;border-radius:4px;font-size:12px;padding:3px 9px}.chapter{background:var(--paper);padding:36px 40px;margin:28px 0;border:1px solid var(--line);border-radius:8px;min-width:0}h2{font-size:27px;line-height:1.45;margin:0 0 24px;letter-spacing:-.015em;color:#153c6a}h3{font-size:20px;margin:36px 0 12px;line-height:1.6}p{margin:14px 0}p.lead{font-size:18px;line-height:1.9}p.caption{font-size:13px;color:var(--muted);margin-top:12px}p.expect{color:#236049;background:#edf8f1;padding:14px 18px;font-size:15px}.note,.important{padding:18px 22px;margin:24px 0;background:#edf3fc;border:1px solid #b8cdea;border-radius:6px}.important{background:#fff6e5;border-color:#e4c381}.note p,.important p{margin:6px 0 0;font-size:15px}code{font-family:"Cascadia Code","Consolas","DejaVu Sans Mono",monospace;font-size:.88em;overflow-wrap:anywhere}p code,td code,li code,aside code{background:#eaf0f6;border-radius:3px;padding:2px 4px}table{border-collapse:collapse;width:100%;font-size:14px;margin:24px 0;line-height:1.8}th{text-align:left;color:#254568;background:#edf2f8;font-weight:700}td,th{padding:12px 14px;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}td:first-child{font-weight:600;min-width:105px}details{border:1px solid var(--line);border-radius:6px;padding:14px 18px;margin:20px 0}summary{cursor:pointer;color:var(--blue);font-weight:650}details[open] summary{margin-bottom:20px}.code{margin:20px 0 24px;border-radius:7px;overflow:hidden;background:var(--code);color:#e4edf9;min-width:0}.codebar{background:#213852;display:flex;justify-content:space-between;align-items:center;padding:9px 15px;gap:15px;font-size:12px;color:#d0deed}.copy{border:1px solid #7990a8;color:#eef4fc;background:transparent;border-radius:4px;padding:2px 11px;min-width:60px;font-size:12px}.copy:hover{background:#355777}.code pre{padding:19px 20px;margin:0;overflow-x:auto;line-height:1.75;tab-size:2;max-height:680px}.code code{font-size:13px;white-space:pre;overflow-wrap:normal}.tok-comment{color:#9cb1ca}.tok-string{color:#abe2bc}.tok-number{color:#ffd58d}.tok-keyword{color:#aebfff}.tok-variable{color:#9edff3}.filelink{font-size:13px}.topology{display:grid;grid-template-columns:1.12fr .5fr 1fr;gap:12px;align-items:center;margin-top:25px}.local-zone{border:1px solid #abc2df;border-radius:8px;padding:20px;background:#f4f8fe}.zone-label{display:block;font-size:12px;color:#345a89;margin-bottom:15px}.node{text-align:center;border-radius:6px;padding:15px 12px;background:#e6eef9;color:#1b436f;font-weight:750;line-height:1.6}.node span,.node small{display:block;font-size:12px;font-weight:400;margin-top:4px}.node.engine{background:#2058b9;color:white;padding:24px 10px}.arrow{text-align:center;font-size:12px;color:#53739c;margin:8px 0}.remote-zone{display:grid;gap:28px}.node.remote{background:#e9f1f4;color:#235762;border:1px solid #bed4d9;padding:30px 8px}.connections{display:flex;flex-direction:column;gap:120px;font-size:11px;color:#426689;white-space:nowrap;text-align:center}.route-diagram{max-width:650px;margin:10px auto 26px;text-align:center}.flow-step{padding:16px;background:#eef3fb;border:1px solid #b9cee8;border-radius:6px;font-weight:700;font-family:"Cascadia Code","Consolas",monospace}.flow-step b{font-size:11px;padding:3px 7px;margin-left:9px;background:#d3e2f8;border-radius:3px;color:#194c90}.flow-step small{display:block;font-size:12px;font-weight:400;font-family:"Microsoft JhengHei",sans-serif;margin-top:5px}.flow-condition{padding:17px;border:1px solid #dbb879;background:#fff7e9;border-radius:6px;font-family:"Consolas",monospace;font-size:14px}.flow-arrow{font-size:13px;color:var(--muted);padding:8px}.fork{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:14px 0}.branch-tag{display:block;font-size:12px;color:var(--muted);padding:4px}.flow-step.yes{background:#e8f5ef;border-color:#a5ceb9}.yes b{background:#c7e8d7;color:#245d41}.checklist label{display:flex;gap:13px;align-items:baseline;border-bottom:1px solid #e0e7ef;padding:13px 0;font-size:15px}.checklist input{accent-color:var(--blue);width:17px;height:17px;flex:none}.sources{font-size:14px;padding-left:22px}.status{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);padding:9px 20px;background:#173d5e;color:white;border-radius:6px;font-size:14px;z-index:30}.status:empty{display:none}.footer{color:var(--muted);font-size:13px;border-top:1px solid var(--line);padding-top:24px}.progress{height:3px;background:#76aaff;position:fixed;top:0;left:260px;width:0;z-index:20}.mobile-menu{display:none}ol,ul{padding-left:24px}li{margin:7px 0}
@media(max-width:1050px){.rail{width:220px;padding:26px 14px}main{margin-left:220px;padding:35px 22px}.progress{left:220px}.chapter{padding:28px 24px}.topology{grid-template-columns:1.1fr .35fr 1fr;gap:7px}.connections{font-size:9px}}
@media(max-width:760px){.rail{position:relative;width:auto;padding:22px 20px}.brand{font-size:20px}.brand small{display:block;margin-left:0;margin-top:7px}.edition,.rail-bottom{display:none}.rail nav{display:flex;overflow:auto;gap:8px;margin-top:18px;padding-bottom:5px}.rail nav a{white-space:nowrap;font-size:12px;padding:6px 8px;background:#1e3e60}.print{width:auto;position:absolute;top:13px;right:20px;font-size:11px;padding:4px 8px}main{margin-left:0;padding:23px 14px 45px}.progress{left:0}h1{font-size:33px}.masthead{font-size:11px}.subtitle{font-size:16px}.chapter{padding:25px 17px;border-radius:6px;margin:18px 0}h2{font-size:23px}h3{font-size:18px}.topology{grid-template-columns:1fr}.local-zone{padding:16px}.connections{flex-direction:row;gap:15px;justify-content:space-around;font-size:11px;margin:5px}.remote-zone{grid-template-columns:1fr 1fr;gap:12px}.node.remote{padding:20px 8px}.fork{gap:10px}.flow-step{padding:13px 7px;font-size:13px}.flow-step b{display:block;width:fit-content;margin:5px auto}.flow-condition{font-size:12px}.code pre{padding:15px 13px}.code code{font-size:12px}table{font-size:12px}td,th{padding:9px 7px}td:first-child{min-width:0}.note,.important{padding:15px}details{padding:12px}body{font-size:15px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{body{background:#fff;font-size:10pt;color:#000}.rail,.progress,.copy,.status,.skip{display:none}main{margin:0;padding:0;max-width:none}.chapter{border:0;padding:0;margin:22pt 0;break-inside:auto}h1{font-size:28pt}h2{font-size:18pt;break-after:avoid}h3{font-size:13pt;break-after:avoid}.code{background:#f2f4f7;color:#172a43;border:1px solid #ccc;break-inside:auto}.codebar{background:#e5e9ef;color:#172a43}.code pre{overflow:visible;max-height:none;white-space:pre-wrap}.code code{white-space:pre-wrap;font-size:8pt;overflow-wrap:anywhere}.tok-comment{color:#516477}.tok-string{color:#165737}.tok-keyword{color:#343b8a}.tok-variable{color:#135474}.tok-number{color:#805018}table{font-size:9pt}a{color:#174e87}.topology,.route-diagram{break-inside:avoid}.footer{font-size:9pt}}
'''
JS = r'''
// Local lexical highlighting: no network, CDN or external library required.
const escapeHTML=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const token=/#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\$\{[^}]*\}|\$[A-Za-z_][\w]*|\b(?:true|false|null|if|then|else|fi|for|do|done|export|source|read|exec|set|def|class|return|import|from|with|try|except|raise|assert|CREATE|TABLE|ALTER|ADD|DROP|SELECT|FROM|WHERE|INSERT|INTO|VALUES|GRANT|ON|TO|NOT|NULL|DEFAULT|PRIMARY|KEY|FOREIGN|REFERENCES|CHECK|INDEX|BEGIN|END|SET|DELIMITER|SHOW|ORDER|BY|JOIN|AND|OR|AS|UPDATE|DELETE)\b|\b\d+(?:\.\d+)?\b/g;
document.querySelectorAll('pre code').forEach(el=>{const raw=el.textContent;el.dataset.raw=raw;let last=0,out='';const grammar=el.dataset.lang==='sql'?new RegExp('--[^\\n]*|'+token.source,'g'):token;for(const m of raw.matchAll(grammar)){out+=escapeHTML(raw.slice(last,m.index));const s=m[0];let cls=(s.startsWith('#')||s.startsWith('--'))?'comment':(s[0]==='"'||s[0]==="'")?'string':s[0]==='$'?'variable':/^\d/.test(s)?'number':'keyword';out+='<span class="tok-'+cls+'">'+escapeHTML(s)+'</span>';last=m.index+s.length;}el.innerHTML=out+escapeHTML(raw.slice(last));});
const status=document.getElementById('status');let statusTimer;
function announce(s){status.textContent=s;clearTimeout(statusTimer);statusTimer=setTimeout(()=>status.textContent='',2600);}
document.querySelectorAll('.copy').forEach(button=>button.addEventListener('click',async()=>{const el=document.getElementById(button.dataset.code);const raw=el.dataset.raw||el.textContent;try{if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(raw);else{const ta=document.createElement('textarea');ta.value=raw;ta.style.position='fixed';ta.style.left='-10000px';document.body.append(ta);ta.select();const copied=document.execCommand('copy');ta.remove();if(!copied)throw Error('copy');}button.textContent='已複製';announce('已複製完整程式碼');setTimeout(()=>button.textContent='複製',1700);}catch(e){announce('瀏覽器不允許複製，請選取程式碼後按 Ctrl+C');}}));
document.getElementById('print').addEventListener('click',()=>window.print());
const links=[...document.querySelectorAll('nav a')],chapters=[...document.querySelectorAll('.chapter')];
function track(){const total=document.documentElement.scrollHeight-innerHeight;document.getElementById('progress').style.width=(total>0?scrollY/total*100:0)+'%';let current=chapters[0].id;chapters.forEach(c=>{if(c.getBoundingClientRect().top<180)current=c.id;});links.forEach(a=>{const active=a.hash==='#'+current;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});}window.addEventListener('scroll',track,{passive:true});track();
'''
nav=''.join(f'<a href="#{i}">{esc(t)}</a>' for i,t,_ in sections)
body=''.join(f'<section class="chapter" id="{i}" aria-labelledby="heading-{i}"><h2 id="heading-{i}">{t}</h2>{b}</section>' for i,t,b in sections)
document=f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Ubuntu 直接啟動 Java、既有遠端 MariaDB、REST 與 Ansible route 的台灣繁體中文操作手冊"><title>Route Engine｜Ubuntu 本機部署 SOP</title><style>{CSS}</style></head>
<body><!-- Read mode: sequential field manual; navy wayfinding, white reading surface, restrained blue actions. Source facts govern diagrams and instructions. -->
<a class="skip" href="#content">跳至主要內容</a><div class="progress" id="progress" aria-hidden="true"></div>
<aside class="rail"><div class="brand">ROUTE ENGINE<small>操作手冊 / Ubuntu</small></div><div class="edition">本機 Java × 遠端 MariaDB<br>REST・Ansible・條件分支</div><nav aria-label="章節目錄">{nav}</nav><div class="rail-bottom">依序完成 01—08<br>09—11：重送、排錯與收尾<br>2026.09.28 / Source v0.1.0</div><button class="print" id="print" type="button">列印 / 另存 PDF</button></aside>
<main id="content"><div class="masthead"><strong>部署・設定・驗證</strong><span>台灣繁體中文 / 可離線閱讀</span></div><header><h1>把第一條 Route，<span>從原始碼跑到完成。</span></h1><p class="subtitle">Ubuntu 本機部署 SOP<br>一步一步建表、啟動、發布，再用 curl 走完兩個分支。</p><div class="chips"><span>Java 21 直接啟動</span><span>既有遠端 MariaDB</span><span>既有 Kubernetes</span><span>完整 SQL / JSON / 指令附件</span></div></header>{body}<footer class="footer">Route Engine / Ubuntu Local SOP · 文件與範例屬教學部署用途。所有成功狀態都需以你的實際執行結果確認。</footer></main><div class="status" id="status" role="status" aria-live="polite"></div><script>{JS}</script></body></html>'''
(HERE/'index.html').write_text(document,encoding='utf-8',newline='\n')
print(f'Built {HERE / "index.html"}: {len(sections)} sections, {count} code blocks')
