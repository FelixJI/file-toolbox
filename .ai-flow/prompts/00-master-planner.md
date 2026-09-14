# v4.0 网页版：规划并写入 Issues

针对用户当前目标，先读仓库适用规则、真实代码/测试、相关 Issues 和未合并 PR。复用既有任务，不重复施工，不依赖旧对话猜当前事实。

单语义 PR 用一个主 Issue；确需多个独立 PR 才 Goal + Task Issues。一次梳理完整依赖队列，仅细化近期 1–2 项。合同采用仓库模板，写 Scope/Out of Scope、编号 AC、依赖、L/R 理由、验证策略和必要授权。规划路由只是建议，由本地 Codex 复核。

有 GitHub 写权限就实际写入，并给真实编号/链接；没有权限输出 WRITE_ACCESS_MISSING 和可发布 Issue Draft，不假称已创建。不要另建长期计划文件，不改代码、不启动任何 Agent。

结束给：主 Issue/Goal，必要 Task 队列，一句已填编号的 Codex 入口（见 docs/ONE_SENTENCE_PROMPTS.md）。没有真实 Issue 编号时不得伪造入口：先让用户发布 Draft 后再把真实编号带到 Codex。
