# 從repository接續，不重新設計

閱讀AGENTS、ai-kit固定契約/自治政策、docs/implementation/STATE.json、
當前ExecPlan、docs/agent/HANDOFF.md、最近的evidence與git diff/status。
確認上次真實完成的phase、未通過的gate、未完成工作与source版本。
不要假定其他聊天的M0–M6是本repo進度；不清空資料/覆蓋現有實作。
先重驗當前前置gate，再從最早未通過phase繼續build/test/review/fix。
一般問題自行處理，只有固定契約衝突或必要外部權限才停。
沒有fresh reviewer就明示NEEDS_FRESH_REVIEW，不能冒稱已完成獨立驗收。
一直做到FINAL或有證據的BLOCKED；不要求我逐階段批准。
