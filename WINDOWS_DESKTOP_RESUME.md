# Windows 桌面版接續指令

請先讀 WINDOWS_DESKTOP_START.md、AGENTS.md、固定 ai-kit 契約，
以及 docs/implementation/STATE.json、docs/agent/HANDOFF.md 和最後 evidence。
先確認沒有其他 Builder 正在修改相同 checkout。
保持桌面版調度：不啟動原 Python runner，不使用 .ai-run/。
核對實際 source fingerprint、環境和最後通過階段，重新執行必要 gate，
從第一個未通過階段繼續 plan → 實作 → 測試 → fresh review → 修正。
不要重建整個專案，不把舊 PASS 當成本版本證據，不問一般實作決策。
沿用原 run-id 或建立有明確 predecessor 的新 run-id，保留原證據。
若遇到平台安全暫停，必須先遵循介面的查驗／恢復要求，不嘗試繞過。
