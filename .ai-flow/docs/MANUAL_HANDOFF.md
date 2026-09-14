# v4.0：怎样让进度可控

## 人工只管真正的跨工具边界

**先判断是不是 Codex ↔ GLM。阶段/checkpoint 结束本身不是停止条件。reviewer 子代理也不是人工交接点。**

| 当前主体 | 可以连续做什么 | 何时才停给用户 | 给用户什么 |
|---|---|---|---|
| 网页版规划者 | 读仓库、复用/创建 Issues、写 L/R 与建议实施者 | 规划完成要交 Codex，或缺权限/需要决策 | 主 Issue/Goal + Codex 入口 |
| Codex 主执行 | 校准→调查→实现→测试→修复→补证据→自动 reviewer 子代理→接收审阅结果 | 需要 GLM、等待真实外部条件、需要用户决策/授权、人工合并或超出授权 | GLM 三句 / 恢复条件 / MERGE_READY |
| GLM | 在同一 Handoff 范围内实现→自测→修复 | 范围完成、受阻、越界或必须回 Codex 判断 | 结果/阻碍评论 + 返回 Codex 的一句话 |
| reviewer 子代理 | 独立只读审阅最新 PR/代码/证据 | 得出 verdict | 结果自动回 Codex；不要求用户操作 |

`next_actor` 仍是当前 Codex/GLM 且在授权范围时继续，不 self-handoff。`next_actor = codex-review-subagent` 时由 Codex 内部自动调用，也不生成用户短句。只有 `Codex ↔ GLM`、human 或 external 边界才需要人工动作。

**短句不是远程命令。** 你只在 Codex 和 GLM 之间搬运一句话，或在外部等待解除后重新启动相应工具。本包不后台监控另一侧。

## 规划时就能看出谁做

每个 Task 的顶部都必须有：Difficulty、Risk、Recommended implementer、Execution mode、Routing rationale。Goal 还必须有一张汇总表，把所有 Task 的 L/R 和建议实施者放在一起。

建议实施者只写三种：`Codex`、`GLM`、`Codex-first → GLM`。网页版先做一次规划判断；Codex 开始后按真实代码校准。若 Codex改分工，必须写明证据和理由，不能静默把所有任务留给自己。

## GLM 交接质量

一个可定位的 Issue 评论胜过一堆聊天记录。Handoff 需有唯一标识、明确范围、分支/当前 SHA、改动归属、已做/未做、证据/阻碍、下一动作和停止条件。

Codex 转 GLM 固定给三句：施工、收尾汇报、阻碍汇报。GLM 正常完成或受阻时主动给返回 Codex 的一句话。无法发布 GitHub 评论时，额外给待发布摘要，不能只说“看 Issue”。

## reviewer 子代理为何不需要你开窗口

独立性来自**新建、只读、重新读取证据的 reviewer 子代理上下文**，不是来自用户手工开另一个窗口。主 Codex 到 REVIEW_READY 后自动创建新的 reviewer 子代理；reviewer 不修改实现，也不接受主 Agent 的结论作为证明。

CHANGES_REQUIRED 直接返回主 Codex 整改；新提交再启动新的 reviewer 子代理增量复核。若运行环境无法提供新的只读 reviewer 子代理，则标 `REVIEW_BLOCKED`，不能用主 Agent 自审冒充独立审阅。

这样你控制的是成本和风险真正跨边界的 **Codex ↔ GLM**，而不是充当 Codex 内部审阅步骤的人工 Continue 按钮。
