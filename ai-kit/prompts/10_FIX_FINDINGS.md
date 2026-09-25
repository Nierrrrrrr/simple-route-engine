# 根據獨立review與test findings修正

先讀固定契約、当前phase plan、外層提供的verify.log/summary、review findings。
逐个重現P0/P1/P2與mandatory failure，先加入能失敗的regression，再做最小修正。
不可藉更改AC/削弱assertion/關test/改sleep長度掩蓋race等方式通過。
若你認為finding不成立，用實際code/測試反例說明，不能只宣告false positive。
修正后跑当前与所有前phase gates；更新docs、STATE、HANDOFF、TRACEABILITY。
你不是reviewer；修完交下一個fresh review，不自行批准自己的finding。
若真正需要改固定架構或越權，保存blocker，不偷偷更改ai-kit。
