# AI Flow v4.0：一句话提示词

这些短句以仓库已完成 v4.0 接入为前提。`#123`、`H1` 只是示例；Agent 实际输出必须代入真实编号或评论链接。Handoff 只用于 Codex ↔ GLM，不用于 Codex reviewer 子代理。

**同一 Codex/GLM 在授权范围内直接继续；reviewer 子代理由 Codex 自动调用。只有 Codex ↔ GLM、外部等待、用户决策或人工合并边界才需要你复制短句。**

## 1. 网页版：规划并写入 Issues

```text
按仓库 AI Flow v4.0 规划【目标】，读取现有代码、规则、Issues 和未合并 PR，复用或创建必要的 GitHub Issues；每个 Task 必须写明 Difficulty、Risk、Recommended implementer（Codex / GLM / Codex-first → GLM）和 Execution mode，Goal 中汇总 L/R、建议实施者、依赖与状态；写清验收标准，不另建计划文件，最后给我复制到 Codex 的一句话。
```

## 1.1 规范化已有 Goal / Task 的分工字段

适合你现在这种已经有 #339 及子 Issues、但 L/R 和实施者没有统一展示的情况：

```text
按仓库 AI Flow v4.0 规范化现有 Goal #339 及其当前 Task Issues：读取真实代码、规则、Issues 和未合并 PR，不重建任务、不改业务 Scope/AC；为每个 Task 原地补齐或校准 Difficulty、Risk、Recommended implementer（Codex / GLM / Codex-first → GLM）、Execution mode 和 Routing rationale，并在 Goal #339 增加/更新包含 Task、L/R、建议实施者、执行模式、依赖、状态的汇总表；最后给我当前应启动 Codex 的一句话。
```

## 2. 网页版 → Codex：开始当前 Task

```text
按 AI Flow v4.0 推进 #123，balanced；先核对 Issue 中 L/R、Recommended implementer 和 Execution mode，并按真实代码/PR校准：Codex 自己负责的工作连续完成，明确施工应交 GLM 时写 Handoff 并给我施工、收尾和阻碍三句后停止；实现/验证就绪后自动调用新的只读 reviewer 子代理并接收结果，不让我另开审阅窗口；只在转 GLM、外部等待、用户决策或 MERGE_READY 时停，不自动合并。
```

## 3. Codex → GLM：施工

```text
按 AI Flow v4.0 作为 GLM 执行 #123 的交接 H1，先读该 Issue 的 Handoff 评论和仓库规则，在本次授权范围内连续完成实现、自测和必要修复；只有范围完成、受阻、越界或必须回 Codex 判断时才写回结果，主动给我返回 Codex 的一句话后停止，不调用 Codex/reviewer、不合并。
```

## 4. 要求 GLM 收尾汇报

```text
按 AI Flow v4.0 汇报 #123 / H1 的当前 GLM 结果，安全停止继续修改，列明已完成和未完成验收项、分支与当前 SHA、实际测试及阻碍，写回 Issue/PR，并给我返回 Codex 接收结果的一句话；没有完成就明确未完成。
```

## 5. 要求 GLM 汇报阻碍

```text
按 AI Flow v4.0 汇报 #123 / H1 的 GLM 阻碍，停止继续试错，写清最小复现、实际报错、已尝试方案与失败轮数、现存改动和待处理事项，写回 Issue，给我返回 Codex 排障的一句话；不要调用 Codex 或自行改换工具继续尝试。
```

## 6. GLM → Codex：结果接收

```text
按 AI Flow v4.0 接收 #123 / H1 的 GLM 施工结果，读取对应结果评论、PR 和当前 SHA，核对验收与测试并完成 Codex 应承担的处理；当前 Codex 能继续就直接继续，明确施工再次需要 GLM 时才给我新 Handoff；实现/验证达到 REVIEW_READY 后自动调用新的只读 reviewer 子代理，PASS 后核对门禁并停在 MERGE_READY，不自动合并。
```

受阻时：

```text
按 AI Flow v4.0 处理 #123 / H1 的 GLM 阻碍，读取阻碍评论、实际报错与现存改动，由 Codex 调查根因并连续解决能解决的问题；只有新的明确施工确需 GLM、外部等待或用户决策时才给我一句话，达到 REVIEW_READY 后自动调用 reviewer 子代理，不重复无效尝试、不自动合并。
```

## 7. reviewer 子代理

**无需用户提示词。** Codex 到 REVIEW_READY 后自动启动新的只读 reviewer 子代理；reviewer 结果自动返回主 Codex。若环境不支持该能力，Codex 应标记 `REVIEW_BLOCKED`，而不是让实现者自审或默认要求你另开窗口。

## 8. 用户完成合并或解除外部阻碍后

```text
按 AI Flow v4.0 继续 #123，先核实真实合并/等待状态和最新基线；在当前授权范围内连续推进，明确施工才人工转 GLM，达到 REVIEW_READY 自动调用 reviewer 子代理，只在新的跨工具/外部/用户决策或人工合并边界停止。
```

## 9. 多 PR 目标完成后回网页版核对

```text
按 AI Flow v4.0 核对 #123 的目标完成情况，读取相关 Issues、已合并 PR、reviewer 子代理结论和最终集成验证证据，给出 ACCEPTED、NOT_ACCEPTED 或 EVIDENCE_MISSING；需要补工则更新 Task 的 L/R、Recommended implementer 和必要 Issue，并给我交给 Codex 的一句话，不代替人工合并。
```

## 使用边界

你不用手工抄分支、SHA 和整段结果；交出者必须先写进可定位的 Issue/PR 评论。接收者重新读取并核实，不凭短句认定成功。

无法写入或读取 GitHub 时，Agent 应明确 `WRITE_ACCESS_MISSING` / `READ_ACCESS_MISSING`，输出最小待发布摘要，再给短句。此时你需一并转交摘要或先补发评论。
