# 固定實作契約：Route Engine v1

版本：1.0；本包提供實作指令，不包含已完成的 application。
本文件是本次從零實作的架構基準。沒有授權重新選型或修改核心語意。

## 1. 範圍與技術方向

實作公司內部部署系統，替代建立 Pipeline 後 disable 其他 route 的方式。
一個 Spring Boot 模組化單體，初期一個 application replica，MariaDB/InnoDB 是唯一業務狀態來源。
模組：Control API、Route/Version Registry、Admission Scheduler、Route Engine、Adapters、Reconciler、Audit。
不使用 Temporal、Redis、Kafka、RabbitMQ、外部 workflow engine、leader-election service 或完整 event sourcing。
Kubernetes 已存在；Ansible 以按需 Job 執行。NATS 通知視為既有 HTTP gateway，不假設 NATS 內建 publish REST API。
不做 caller fairness、機台互斥鎖、搶占、全面多租戶、任意程式碼熱載入、大型視覺化編輯器或大型壓測。
API-first；提供 OpenAPI 與可執行 examples，不要求前端 UI。

Java 21 作為預設基線，Maven Wrapper；M0 依官方資料選一組穩定、仍適合使用且互相相容的
Spring Boot / MariaDB / JDBC / Flyway / Kubernetes client / 測試工具版本，記錄並固定。
版本本身不是架構問題，不要為每個 patch 要求使用者確認；禁止 latest、SNAPSHOT、動態版本。
偏向 Spring JDBC + 明確 SQL / TransactionTemplate，不要用 ORM 隱藏 admission 鎖定。
測試可以使用 JUnit、Testcontainers、HTTP fixture、kind；它們不是新增正式 runtime service。
在 Java/依賴不能寫入全域目錄時，使用 workspace-local cache 或已授權測試容器。

## 2. Route / Version / DSL

每條 route 有 routeId、各自遞增 version；DRAFT 可改，PUBLISHED 不可改。
停用/soft delete 禁止新建 execution，但舊 execution / recovery 保留原定義。
接單時就解析並綁定確切 published version，排隊或 recovery 不改用最新版本。
保存 definition hash、dslVersion、engineSemanticsVersion、adapter contract version；
playbook / artifact 使用 immutable version 或 digest，credential 保存引用。
當 engineVersion 不支援時 fail closed，不用新版重新猜測舊執行的語意。

第一版 DSL：SEQUENCE、受限 CONDITION / when、一層 PARALLEL(ALL_SETTLED)、
REST、KUBERNETES、ANSIBLE、有限 onFailure 通知、可選 step rollback。
不支援任意深度 parallel、無限 loop/goto、任意 script/expression eval。
條件使用受控、具型別的欄位比較；branch choice、resolved non-secret input、output 都需持久化。
parallel 分支各自保存 output，不共用可變 Map；join 才合併；branch nodeId 必須唯一。
一條 execution 的所有 parallel 分支共用一個 route permit。
發布時驗證結構、未知欄位/節點、引用、版本、input/output 相依、循環、max node/parallel bounds。
機密值不得出現在 route snapshot、例外、API payload 日誌、Runner 產物索引或 audit。

新增第六條 route 若只使用現有 node 能力，必須純設定發布，不改 Java、不重部署。
新增新 node type / protocol 才需要實作 adapter 與新版本的明確契約。
原本五条企業 route 詳細內容沒有提供：建立五條清楚標記為 DEMO 的範例，不能假裝已搬完原 Pipeline。

## 3. Admission 與 permit

預設 T=100，R=20，HIGH:NORMAL:LOW=6:3:1，均可 config 更新。
只有 CRITICAL 可用保留容量；CRITICAL 也可使用 shared 容量；不做 preemption。
U = 所有 permit_held=true 的 execution 數；N = 其中非 CRITICAL 的數。
永遠維持 U<=T 且 N<=T-R。可用此限制表達 pool，毋須固定 100 張椅子。
有可放行的 CRITICAL queued request 時先放 CRITICAL；非 CRITICAL 使用持久化 weighted round-robin。
預設輪序 HHHHHHNNNL；同 class FIFO；空 class 跳過；只有真正放行才消耗權重並前進。
CRITICAL 不消耗非 CRITICAL 游標；空 queue 不累積無限 credit；權重更新需定義可重現的游標重置規則。
比例代表 admissions，不代表 wall time、CPU 或保證 starvation-free。CRITICAL strict priority 可能餓死其他 class。
原始 execution priority 固定，人工 recovery 不得覆写，recovery 用新的入隊時間。

POST /executions 同時支援 QUEUE 與 NOW_OR_REJECT。
NOW 的唯一承諾：同一 DB transaction 立即取得 route permit，不進業務容量等待 queue。
不承諾第一個 Activity/外部工作 N 秒內開始。不可放行就拒絕，不能留下未來自動啟動的工作。
NOW 不繞過既有 CRITICAL/FIFO/WRR；可在交易中作臨時候選，未獲 permit 的本次請求不留 queue。
GET /capacity 是帶 observedAt/configVersion 的觀測快照，不是 reservation。
不新增 Reservation API。

Idempotency-Key 按 principal + endpoint/operation scope 唯一；同 key 同內容重回原決策，
不同內容 409；已被拒絕後另次搶位要新 key；回應遺失重送原 key。
拒絕結果可存 admission_requests，不必建立可執行 execution。
DB 不可用 / commit 結果不明與明確 capacity reject 分開；不能回報『確定沒啟動』卻實際已 commit。
M0 固定 HTTP/code 範例：accepted/queued 202；業務 admission reject 409 + ADMISSION_REJECTED；
不相容狀態/冪等衝突 409；不合法 route/action 422；暫不可判斷 503 + request identity。
HTTP 選擇可以在 M0 記錄更一致的非破壞性替代，但不可混淆三種語意。

## 4. Slot 生命週期與安全停止

QUEUED：無 permit。
ADMITTED/RUNNING/WAITING_EXTERNAL/RETRY_WAIT：持有 permit；retry backoff 不釋放。
PAUSING/RECONCILING/CANCELING：仍持有 permit，直到外部工作確定停止/完成。
MANUAL_WAIT：沒有仍自動執行或無法確認是否執行的本 route 工作；原子釋放 permit。
RECOVERY_QUEUED：沒有 permit。
RECOVERING/ROLLING_BACK：取得新的 permit_generation 後執行。
SUCCEEDED/FAILED/CANCELLED：確認終止且無未收斂外部工作後釋放。
FAILED 是不可再恢復的終態，不拿來表示需要人工判斷。

一個 parallel branch 失敗不代表其他 branch 停止；所有已啟動分支 ALL_SETTLED 才能進 MANUAL_WAIT。
不派發其後的 step；成功 branch 結果保留，retry 不重做成功 branch。
HTTP timeout、刪除 Job 請求成功或 worker lease 到期，都不是外部已停止的證據。
IN_DOUBT 表示某個 operation 結果未知；execution 保留 permit，停止不安全的後續操作並告警。
不提供默認的 force-release / force-retry 繞過未知狀態。
提供具 operator audit 的 incident reconciliation/resolve 入口：附證據確認既有 operation
SUCCEEDED/FAILED/STOPPED；它只能解決既有狀態，不能偷偷新建 side effect。
成功後可依狀態機繼續；確認失敗/停止且所有工作收斂才可進 MANUAL_WAIT。

## 5. 人工恢復

POST /executions/{id}/recoveries：incidentId、stepId、action、admissionMode、reason、Idempotency-Key。
四種 action：RETRY / SKIP / ROLLBACK / CANCEL，皆支援 QUEUE / NOW_OR_REJECT。
原始 priority 不變。鎖定 incident/execution，只有一筆有效 pending recovery。
NOW 被拒絕必須保持 MANUAL_WAIT、incident 與 step 決策不變，不留下 pending action。
QUEUE 保存決策，轉 RECOVERY_QUEUED；放行前重驗 incident 是否仍有效。
舊 incident / 重複指令 / 競態不同 action 不得執行兩次。

RETRY：只重做指定失敗 step/branch；辨識 FORWARD 與 ROLLBACK direction。
SKIP：明確 audit；若後續需要輸出，要求合法 replacement output 或拒絕，不讓 null 偷渡。
ROLLBACK：只有該 step 明確定義 rollback 才能用，預設不允許。
僅對目前 incident 合法目標執行 step-level compensation；不是整條 route rollback。
不能補償任意已被後續成功步驟依賴的舊 step。補償 snapshot/必要資料在 forward 前後按契約保存。
rollback 成功回 MANUAL_WAIT 並釋放，標記已補償；不自動重跑後續。
rollback 失敗也有有限 retry 與人工等待；再次 RETRY 指向 rollback 而非 forward。

CANCEL 在 MANUAL_WAIT 以 recovery 提交，遵循其 mode，取得 permit 後完成停止並釋放。
這與『停止已持有 permit 的 running execution』不同：後者不取得第二個 permit，
發 cancel intent、停止新派工、確認已啟動工作收尾後釋放，不隱含 rollback。
撤回尚未 admission 的 QUEUED request 是撤銷請求，不應為此創造第二個 recovery 工作。

## 6. DB 交易與持久化

核心表：routes、route_versions、executions、admission_requests、step_runs、step_attempts、execution_events、scheduler_pool。
可以增加必要明細/索引，但不用增加獨立持久化 broker。
目前狀態+append-only audit，不做 event replay interpreter。
全體 admission/config/permit acquire-release 操作先鎖 scheduler_pool row，使用短 READ COMMITTED transaction。
需要多個 lock 時全案遵守 pool → execution → incident/admission → step 的固定順序。
只更新 step 的 transaction 不得先持 step/execution lock 再倒過來拿 pool。
禁止外部 I/O 在 DB transaction 內；禁止六小時 transaction。
state version / generation 条件更新檢查 affected rows，陳舊更新不得忽略。
lease 時間以 DB server clock 或已驗證的一致策略；測試用 injectable clock 不可導致生產時間漂移。
permit 永久保存到明確釋放，不以 worker heartbeat/TTL 回收。
lease_generation、permit_generation、operation_generation 分離。
改小 T/R 若使目前 U/N 超限則拒絕；不搶占。配置更新 audit、configVersion 同交易一致。
DB 不可用：停止新 admission / 新外部提交；已在外部執行的工作保持可查驗 identity。

Step 執行：交易內 intent+attempt+lease → commit → 交易外 I/O → 短交易保存結果/下一步/事件。
下一步待辦和前一步結果同一 DB transaction，DB 待辦即 durable queue。
本地 scheduler 只負責喚醒，不負責永久保存未完成工作；重啟必須重掃 DB。

## 7. Adapter 與外部副作用

Adapter contract 必須包含 submit、observe/reconcile、cancel 能力、success/failure 定義、retryability、
idempotency 支援、可否安全重新提交、output schema、secret/log redaction、compensation 能力。
HTTP 2xx/202 不直接代表業務工作完成；accepted operation 需追蹤 terminal result。
有穩定 idempotency key/operation ID 才能在回應遺失時安全查驗/重送。
對無 dedupe/無查詢且不能安全重複的操作，未知狀態進 IN_DOUBT，不自動 retry。
不宣稱 exactly-once side effect；tests 證明的是限定 adapter 契約下的去重行為。
Transport retry 沿用同一次 operation identity；確知前次失敗後的新業務嘗試按 adapter 契約換 generation。
不是每一次 network retry 都換 key，也不是所有 business retries 永遠用同 key。
worker lease 過期先 reconcile；舊 worker 結果以 fencing generation 阻擋，且文件寫明 DB fencing 不會撤銷已發 HTTP。

REST：受控 endpointRef，TLS/auth/timeouts，allowed host/redirect policy，回應大小上限，不讓任意 URL/headers 洩漏憑證。
Kubernetes：使用明確 context、namespace/資源 allowlist；提交後確認對應 generation/UID 的業務完成狀態；
處理 resourceVersion conflict；第一版 polling 即可；禁用 wildcard cluster-admin 作正式預設。
Ansible：穩定 Job name/operation labels，保存 UID，重送先查同 identity 的既有 Job；
已知過去提交但 Job 被 GC 找不到時，不當作『从未執行』盲目新建。
Job 不以 Application Pod 為 owner；Pod 重啟不可連帶刪除長工作。
runtime image/playbook pinned；backoffLimit 與 Application retry 避免雙重自動重跑，仍承認 Job 可能重複啟動。
實際 ansible-runner 產出 stdout/rc/status/events；不能只用 shell echo 代替 Ansible 整合測試。
不使用未追蹤的 async poll:0；使用時必須保存並確認所有 remote job 完成。
Notifications：有限 retry，主錯誤不被通知錯誤覆蓋，不遞迴通知自己；permit 釋放前收斂。

## 8. 安全與維運

角色：caller/operator/admin；priority caller 自定，不加 fairness。
本地測試使用臨時身份與 secret；正式 credential 只引用環境/Secret；不 hardcode；未配置 auth 正式模式拒啟。
可用 Spring Security 提供簡單 bearer principal 驗證，不為第一版新增 IAM server；M0 記錄 token 生成/雜湊/輪替辦法。
單一 execution 的一般 exception 要隔離，不停止 scheduler 整批；OOM/DB outage 不承諾零影響。
有界 executor、本地 HTTP / Job 資源上限與 route permit 明確分離。
一個 replica/Recreate 是運維選擇，不是互斥證明，測試仍涵蓋重疊兩程序。
DB migrations versioned；rollback migration 不破壞已發布定義/舊 execution。
runner artifacts 用持久化儲存/PVC，不只 Pod logs；大 stdout 不直接塞 execution row。
audit 至少涵蓋 caller、operator、reason、version、admission、permit、step attempt、retry、incident、補償、config。
metrics 至少 queue depth、U/N、admission reject、retry、IN_DOUBT、stalled execution、lease/reconcile、scheduler lag。
health/readiness 區分 DB unavailable，不因目標 API 錯誤一直重啟整個 Application。

## 9. 接受的驗收範圍

必做：真實 MariaDB 整合、獨立程序 crash/restart、真實 local Kubernetes(kind) Job/rollout、
實際 Ansible Runner 對隔離 fixture 執行、REST fixture 驗證行為、API authorization、文件與新增第六條 route 演練。
六小時相關邏輯用可控制時鐘驗證 durable timing，另有短 wall-clock restart/async tests；不冒稱跑了六小時 soak。
不必取得公司正式 API/機台/正式 K8s 權限即可完成工程驗收。
未提供的真實 endpoints / 五條 routes / 正式 credentials 用 EXTERNAL_ACCEPTANCE=NOT_RUN 明確列出。
完整 final gate 是 ENGINEERING_ACCEPTANCE=PASS，不是 PRODUCTION_ACCEPTANCE=PASS；正式部署永遠 NOT_AUTHORIZED。
