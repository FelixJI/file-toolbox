# v4.0 网页版：规划并写入 Issues

针对用户当前目标，先读仓库适用规则、真实代码/测试、相关 Issues 和未合并 PR。复用既有任务，不重复施工，不依赖旧对话猜当前事实。

单语义 PR 用一个主 Issue；确需多个独立 PR 才 Goal + Task Issues。一次梳理完整依赖队列，仅细化近期 1–2 项。合同采用仓库模板，写 Scope/Out of Scope、编号 AC、依赖、验证策略和必要授权。

**规划阶段必须完成第一次可见分工：**
- 每个 Task 都填写 `Difficulty`、`Risk`、`Recommended implementer`、`Execution mode`、`Routing rationale`。
- `Recommended implementer` 只能是 `Codex`、`GLM`、`Codex-first → GLM`。
- balanced 默认：L1/L2 明确施工优先 GLM；L3 根据未知程度选择 Codex 或 Codex-first → GLM；L4/L5 Codex。R3 等高风险可把简单任务保留给 Codex，但要写理由。
- Goal Issue 必须有 `Task | L/R | Recommended implementer | Execution mode | Depends on | State` 汇总表。不能只在子 Issue 尾部写 L/R，也不能只写顺序/状态。
- 规划路由是建议，本地 Codex 必须基于真实工作区和最新 PR 再校准；但不能因“只是建议”而省略字段。

已有 Goal/Task 若缺少上述标准字段，**原地补齐/校准，不重新创建重复 Issue**；Goal 的汇总表也要同步更新。若旧正文已有 L/R 或“Codex 主做/可交施工”等信息，转写成标准字段并保留有用理由，不制造第二套并行分工描述。

有 GitHub 写权限就实际写入，并给真实编号/链接；没有权限输出 WRITE_ACCESS_MISSING 和可发布 Issue Draft，不假称已创建。不要另建长期计划文件，不改代码、不启动任何 Agent。

结束给：主 Issue/Goal、带分工的 Task 队列、一句已填编号的 Codex 入口（见 docs/ONE_SENTENCE_PROMPTS.md）。没有真实 Issue 编号时不得伪造入口。
