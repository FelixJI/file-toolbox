# Codex Reviewer Subagent Result

用途：PR 审阅评论；由新的只读 reviewer 子代理生成，不能替代平台批准或合并授权。

Issue / PR / 待审版本：

reviewed_head_sha / reviewed_base_sha：

reviewer context：fresh Codex review subagent（不可得的内部标识不编造）

审阅范围 / 首审或增量复核 / 实际验证范围：

| AC | 证据 / 缺口 |
|---|---|
| AC1 | |

| Finding ID | 定位与复现证据 | 影响 | 严重性 | 是否阻塞 |
|---|---|---|---|---|
| | | | | |

未解决 blockers / 待核实反证：

Verdict: PASS / CHANGES_REQUIRED / INSUFFICIENT_EVIDENCE

只读审阅：不改实现、不调用 GLM、不合并。结果自动返回 Codex 主执行；无需用户另开窗口或复制审阅提示词。
