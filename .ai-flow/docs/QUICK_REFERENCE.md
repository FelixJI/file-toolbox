# AI Flow v4.0 快速参考

入口：`prompts/08-codex-entry.md`。短句全集：`docs/ONE_SENTENCE_PROMPTS.md`。

顺序：**网页写带 L/R 与建议实施者的 Issues → 用户启动 Codex → 必要时用户启动 GLM → 用户带 GLM 结果回 Codex → Codex 自动 reviewer 子代理 → MERGE_READY → 用户合并。**

分工：L1/L2 明确施工默认 GLM；L3 Codex 判断后可转 GLM；L4/L5 Codex。每个 Task 显式写 `Recommended implementer`，Goal 汇总可见。Codex 可按真实代码校准，但要写理由。

交接：只在 Codex ↔ GLM 跨工具时创建 Handoff。reviewer 子代理不需要人工 Handoff，也不需要新窗口。

完成 ≠ 验收；review PASS ≠ 已合并；未启动 ≠ 已交给另一侧。当前最新 SHA 缺证据就不能 MERGE_READY。

本包无 runner、无状态监听、无 Codex↔GLM 自动互调；保留的 Python 工具只做安装迁移和 Git 产物检查。
