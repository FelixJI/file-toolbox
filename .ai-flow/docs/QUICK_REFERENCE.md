# AI Flow v4.0 快速参考

入口：`prompts/08-codex-entry.md`。短句全集：`docs/ONE_SENTENCE_PROMPTS.md`。

顺序：网页写 Issues → 用户启动 Codex → 用户启动 zcode/pi（需要时）→ 用户带结果回 Codex → 用户开启独立 Codex 审阅 → 回 Codex 核对 → 用户合并。

技术分工：Codex 负责判断和复杂工作；zcode/pi 负责明确施工。**同主体在当前授权范围内连续执行；只有切换主体/独立角色、等待外部条件或需要用户决策时才由用户再次启动。**

交接：只在跨 actor 时创建。Issue + 唯一交接标识/评论 + 分支/base/head + 工作区归属 + 证据/阻碍 + 下一步/停止条件。`next_actor == current_actor` 时继续，不 self-handoff。

完成 ≠ 验收；审阅 PASS ≠ 已合并；未启动 ≠ 已交给另一侧。当前最新 SHA 缺证据就不能 MERGE_READY。

本包无 runner、无状态监听、无 Agent 互调；保留的 Python 工具只做安装迁移和 Git 产物检查。
