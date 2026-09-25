# 官方參考資料

查核日期：2026-09-25。此文件是來源索引，不是對使用者帳號權限或未來版本的保證。
所有phase的功能/架構要求源自使用者定案與本包工程驗收設計，不是引用產品聲稱代替測試。

| 用途 | 官方來源 |
|---|---|
| Codex模型選擇、/model、--model | https://developers.openai.com/codex/models |
| GPT-6 Astra模型識別與reasoning能力 | https://developers.openai.com/api/docs/models/gpt-6-astra |
| 非互動exec、stdin、JSON輸出、resume、deprecated full-auto | https://developers.openai.com/codex/non-interactive-mode |
| Codex CLI旗標 | https://developers.openai.com/codex/developer-commands |
| AGENTS.md載入與大小限制 | https://developers.openai.com/codex/agent-configuration/agents-md |
| Subagent/fresh review工作方式 | https://developers.openai.com/codex/agent-configuration/subagents |
| Sandbox與approval邊界 | https://developers.openai.com/codex/agent-approvals-security |
| Workspace network設定 | https://developers.openai.com/codex/config-reference |
| 長工作ExecPlan模式 | https://developers.openai.com/cookbook/articles/codex_exec_plans |
| Spring Boot相容性；M0再固定具體版本 | https://docs.spring.io/spring-boot/system-requirements.html |
| MariaDB FOR UPDATE必須位於transaction | https://mariadb.com/docs/server/reference/sql-statements/data-manipulation/selecting-data/for-update |
| Kubernetes Job生命週期與可能重複啟動 | https://kubernetes.io/docs/concepts/workloads/controllers/job/ |
| Ansible Runner產物與events | https://docs.ansible.com/projects/runner/en/latest/intro/ |

部分OpenAI Developers文件可能重新導向官方ChatGPT Learn站點。使用當前CLI的help核對本機支援，
不要在帳號缺少模型時悄悄切換，也不要為了全自動關閉組織的安全政策。
