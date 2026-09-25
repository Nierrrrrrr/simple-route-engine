# 固定驗收矩陣

每個 ID 必須對應真正檢查，不得刪除或改判斷標準。phase gate 是累積驗收。

## M0

| ID | 需求 | 最低證據 |
|---|---|---|
| AC-001 | 契約與 phase 邊界固定 | 有 ADR/defaults/狀態草圖/需求 traceability，不新增未核准 runtime service。 |
| AC-002 | 工具與隔離 preflight | 實際執行版本、Docker、local workspace/network 權限檢查；未提供正式 credentials 不構成引擎 blocker。 |
| AC-003 | 可機器驗證的 gate | verify-phase 與 report schema 真正檢查檔案/需求，缺檔/失敗/未跑返回非零；不以 echo PASS 代替。 |
| AC-004 | 可恢復的 agent 工作紀錄 | ExecPlan、STATE.json、DECISIONS、HANDOFF 初始檔案一致，明確當前階段與未完成清單。 |

## M1

| ID | 需求 | 最低證據 |
|---|---|---|
| AC-005 | 可重現 build | Maven Wrapper、固定相容依賴、實際 compile/unit test、非空測試集合。 |
| AC-006 | 真實 MariaDB migrations | 從空 InnoDB DB 成功 migrate 並重啟持久化；不能用 H2 或 mock DB 代替。 |
| AC-007 | route CRUD 與 immutable version | draft 可改、published 不可改、停用只禁止新建、原 execution reference 可保存。 |
| AC-008 | API/data schema 基礎 | OpenAPI 與 validation 一致，UTC timestamps、request id、合法錯誤格式。 |
| AC-009 | 持久化事件與唯一性 | unique key/foreign key/state version 以及 execution_events 與狀態同交易寫入；rollback 不留半筆事件。 |
| AC-010 | 本地可啟動環境 | app+MariaDB compose/等價脚本啟動成功；不要求正式外部服務。 |

## M2

| ID | 需求 | 最低證據 |
|---|---|---|
| AC-011 | 最後一個 slot 競爭 | 真實 DB 同時至少 200 個 competing requests，只有 1 个取得最後 permit，U/N 不超限。 |
| AC-012 | 100/20 硬保留 | 80 個 non-critical 用滿後拒絕其他 non-critical，CRITICAL 可用剩餘20；CRITICAL 也可占 shared。 |
| AC-013 | CRITICAL strict priority | 排隊 CRITICAL 先於所有 non-critical 放行；不搶占 running route。 |
| AC-014 | 6:3:1 持久化 WRR | 三 queue 持續非空時 100 次非CRITICAL admissions 得 60/30/10，空 queue 跳過；重啟游標不歸零。 |
| AC-015 | class 內 FIFO 與 NOW 不插隊 | NOW 按同一 scheduler 競爭，不能越過舊同class或CRITICAL；被拒不消耗權重。 |
| AC-016 | NOW 原子成功或拒絕 | accepted 同交易持有 permit；reject 沒有 pending execution/action，之後 tick 不會啟動。 |
| AC-017 | QUEUE 與 capacity snapshot | QUEUE 可持久化等待且不占 permit，capacity 標記 observedAt/version 但不保證未來 admission。 |
| AC-018 | 冪等與回應遺失 | 同 key 並行/重送只有一份結果；不同 body 衝突；reject 原key仍拒絕、新key可重新競爭；commit回應丟失可查原結果。 |
| AC-019 | 配置更新與縮減 | 非法 T/R/weight 拒絕；導致 U/N 超限的更新拒絕；合法配置與游標規則原子/audit。 |
| AC-020 | permit generation | 重複 release 冪等；舊 generation 不能釋放新 permit；lease expiry 不釋放 permit。 |
| AC-021 | 跨程序交易正確 | 兩個獨立 JVM/進程並發 admission，共用 MariaDB；不能只測同 JVM synchronized。 |
| AC-022 | DB outage fail closed | DB 故障與 reject 不混淆；不從 cache 新放行；deadlock/lock timeout 不成為超发或重複 request。 |

## M3

| ID | 需求 | 最低證據 |
|---|---|---|
| AC-023 | 持久化順序推進 | 前步完成與後步待辦原子，commit後kill/restart仍可推進，不漏不重覆初始化 node。 |
| AC-024 | 條件與上下文固定 | when/condition 決策與輸出持久化；重啟/外部資料改變不重新選已選的分支。 |
| AC-025 | 受限 parallel ALL_SETTLED | 各 branch 狀態獨立，一失敗他支仍跑時不釋放；成功分支不因他支重試而重跑。 |
| AC-026 | durable retry 與時鐘 | max attempts/elapsed/backoff 存DB；retry等待占slot；用可控時鐘驗證6小時語意及短實時restart。 |
| AC-027 | 安全 MANUAL_WAIT | 停止派發後續，所有外部工作已收斂才進人工且釋放；狀態與permit同交易。 |
| AC-028 | step 認領與 fencing | lease過期重查；舊 worker 結果被CAS拒絕；兩個execution不共用mutable context。 |
| AC-029 | 一般例外隔離 | 某route拋exception不令其他route失敗、不令整批scheduler停止；executor有界。 |
| AC-030 | 未知結果不盲目重送 | simulation驗證IN_DOUBT保留permit/停止不安全後續，不偽造manual或success。 |
| AC-031 | DSL 發布驗證 | 未知node、重複ID、循環、非法相依、超出parallel深度、非法expression均拒絕。 |

## M4

| ID | 需求 | 最低證據 |
|---|---|---|
| AC-032 | REST真實HTTP行為 | 實際fixture server：同步/非同步/輪詢/4xx/5xx/timeout/response lost；HTTP accepted不等於完成。 |
| AC-033 | 副作用與冪等查验 | 對端已產生副作用後kill app，restart用原operation查验/dedupe；可證明side effect counter不重覆。 |
| AC-034 | 無冪等的未知操作 | 無dedupe/查詢的fixture發生不明結果後不再次submit，保留permit並產生incident。 |
| AC-035 | 實際Kubernetes rollout | 在專用kind namespace操作真實resource並驗證generation/UID完成；處理conflict與failed rollout。 |
| AC-036 | Job建立/回應遺失 | 真實Job穩定identity、重查既有UID；app重啟不刪Job；提交過但GC找不到不盲目重建。 |
| AC-037 | 真實Ansible執行 | 真實ansible-runner在Job對隔離localhost/fixture執行無害playbook，產出rc/status/events；不是echo成功。 |
| AC-038 | Job取消與remote工作 | 取消請求不當成已停止；所有remote async工作可追蹤；確認terminal後才釋放permit。 |
| AC-039 | 外部重試世代 | transport retry與新的business attempt身份分離；rollback direction不誤用forward key。 |
| AC-040 | 失敗通知有限且隔離 | NATS HTTP fixture通知成功/失敗/重送；不遞迴、不覆蓋主錯誤；permit釋放前收斂。 |
| AC-041 | artifact與secret保護 | 取得真實Runner artifacts，DB保存引用，Pod刪除後可讀必要證據；secret不出現在日誌/事件。 |

## M5

| ID | 需求 | 最低證據 |
|---|---|---|
| AC-042 | recovery NOW原子拒絕 | 沒容量時保持MANUAL_WAIT/incident/step不變，沒有未來action；有容量時決策+新permit同commit。 |
| AC-043 | recovery QUEUE原priority | 使用原priority、新enqueue時間，放行前重驗incident；不可由body提升/降低priority。 |
| AC-044 | recovery冪等/競態 | 同incident兩不同人工指令并发只有一个有效；重送/舊incident不重覆執行。 |
| AC-045 | RETRY與SKIP | 只重試失敗step/branch；SKIP必須滿足output依賴或拒絕，完整audit。 |
| AC-046 | ROLLBACK預設禁止 | 無定義拒絕；僅合法incident step補償，不做全route rollback、不動已被後續依賴的舊step。 |
| AC-047 | rollback完成/失敗 | 成功回MANUAL_WAIT並釋放，失敗有限retry/人工；retry補償不跑forward；重複命令不重覆補償。 |
| AC-048 | CANCEL多狀態語意 | manual CANCEL遵循mode；running cancel不搶第二permit且確認停止再釋放；queued撤回不建立新工作。 |
| AC-049 | IN_DOUBT人工查驗 | resolve需operator/evidence，僅確認既有operation，不隱含new submit；安全收斂後正常轉態。 |
| AC-050 | 舊permit延遲回應 | 首次permit延遲release/worker callback抵達第二次recovery時不破壞新permit/狀態。 |

## M6

| ID | 需求 | 最低證據 |
|---|---|---|
| AC-051 | 正式模式身份與權限 | caller/operator/admin分界；未配置auth拒啟；negative tests、rotation/secret refs記錄。 |
| AC-052 | 命令/URL/namespace邊界 | controlled endpoint/playbook/resource、禁任意shell/eval/URL，redirect/credential不外洩，K8s最小權限。 |
| AC-053 | 啟停與重疊Pod | graceful停止認領、強制kill亦可恢复；一replica不作唯一互斥保證，重疊程序測試。 |
| AC-054 | 版本與DB升級相容 | 舊route/排隊/人工等待fixture在migration與engine升級後仍保原語意，不直接改published內容。 |
| AC-055 | 監控/audit/持久化與runbook | metrics/health/records完整，logs有界持久，backup/restore於隔離DB演練或可驗證腳本；不碰正式DB。 |
| AC-056 | 部署與測試可重現 | 固定image/version、local compose/kind、全新DB與工作目錄可建置；清理只限本run資源。 |
| AC-057 | Agent接手文件完整 | DOCS_DELIVERABLES所有檔案存在，實際路徑/命令/schema相符，不以TBD充数。 |
| AC-058 | 範例與外部驗收標示 | 五條DEMO涵蓋現有能力；未提供企業route/端點清楚列NOT_RUN，不能聲稱production驗收。 |

## FINAL

| ID | 需求 | 最低證據 |
|---|---|---|
| AC-059 | 乾淨環境全量累積驗收 | 重新建置並跑所有mandatory suites，無fail/error/skip/NOT_RUN；真實MariaDB與kind/Ansible證據存在。 |
| AC-060 | 獨立整體審查 | fresh session從固定需求反推code/test/故障路徑，P0/P1/P2與mandatory缺口全部關閉，只有有理由的P3可記錄。 |
| AC-061 | 第六條route接手演練 | fresh session只讀repo文件，純新增fixture/config發布執行DEMO route6，不改任何引擎Java；前五route回歸。 |
| AC-062 | fault matrix與長時語意 | 提交前後/回應遺失/落DB前後/parallel/manual/recovery crash點皆有實測，6小時虛擬時鐘與非soak界線清楚。 |
| AC-063 | 交付清單與真實證據 | 需求ID→測試→命令→原始log/報表→source fingerprint完整，沒有硬編碼success或篡改驗收器。 |
| AC-064 | 上線界線 | ENGINEERING_ACCEPTANCE=PASS只在全部滿足；EXTERNAL_ACCEPTANCE=NOT_RUN、PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED。 |


## Evidence contract
`bash scripts/verify-phase.sh PHASE EVIDENCE_DIR` 必須真正執行檢查並寫 `EVIDENCE_DIR/summary.json`。
EVIDENCE_DIR 在 repo 的 `.evidence/` 下面；不得寫 `.ai-run/`（外層runner專用）。
環境變數 `ROUTE_SOURCE_FINGERPRINT` 由 runner 注入；報表原樣記錄，runner 前後再計算檔案hash比對。

報表格式：
```json
{
  "phase": "M2",
  "source_fingerprint": "環境變數的值",
  "production_authorized": false,
  "checks": [
    {"id": "AC-001", "status": "PASS", "evidence": "logs/contracts.log"}
  ],
  "suites": [
    {"name": "mariadb-integration", "tests": 10, "failures": 0, "errors": 0,
     "skipped": 0, "report": "junit/TEST-Admission.xml"}
  ]
}
```
上面的單個check僅示例，實際必須包括 PHASE 及所有前階段的全部 ID，不能只送 AC-001。
每個 evidence/report 路徑相對 EVIDENCE_DIR，檔案實際存在、非空且不在目錄外。
各suite數字由實際測試runner報表解析，不得硬編碼；M0可只有非空doc/preflight validations。
M1後必須至少一個 tests>0 的真實suite，且強制項目不能 skip。FINAL 必須包含全部正式驗收項。
full suite 需要 Docker/kind 卻不可用：非零退出，明確環境blocker，不允許變成unit-only PASS。
測試腳本不能改source/spec來得到綠燈；只寫build/log/測試產物，fixture程式應由builder先寫入。
`.evidence/`、`.ai-run/`、`target/`、`.tools/`、`.cache/`、`.local/` 不應加入 Git。
`docs/implementation/TRACEABILITY.md` 維護 requirement→test file/symbol→command，不取代真正結果。

驗收模式：requirements.json 中 verification_mode=EXECUTABLE 由腳本出checks；REVIEW項由fresh reviewer確認並在結果verified_requirements列出。脚本不得預先偽造獨立review通過。FINAL_ACCEPTANCE.md在review前只能標CANDIDATE；最終判定由外層runner的FINAL_RESULT.json寫出。
