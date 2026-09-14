---
name: AI Goal v4.0
about: 跨多个语义 PR 的目标、依赖和显式分工队列
title: "[AI Goal] "
labels: ""
assignees: ""
---

## Goal / Scope / Out of Scope

最终可观察目标及边界：

## Goal Acceptance

- [ ] GAC1：
- [ ] GAC2：

## Task Routing Summary

> 必填。每个 Task 的 L/R、建议实施者和执行模式必须直接在 Goal 中可见，不能只藏在子 Issue。

| 顺序 | Task | L/R | Recommended implementer | Execution mode | Depends on | State |
|---|---|---|---|---|---|---|
| 1 | #... | L?/R? | Codex / GLM / Codex-first → GLM | ... | none | READY |

## Task Dependencies

只列需要独立 Issue/PR 验收的语义任务；用真实编号替换示例。checkpoint 不建新 Issue。

```text
Task A → Task C
Task B → Task C
```

## Existing Issues / PRs

复用、冲突、依赖、当前实际合并状态：

## Integration Validation

跨 PR 集成、兼容和最终用户路径证据：

## Current Stage / Next Action

当前已就绪 Task、等待/阻碍、用户下一次应启动 Codex 还是 GLM：

不会自动执行整个队列；规划建议由 Codex 开始任务时重新校准。正式审阅由 Codex reviewer 子代理自动完成，最终合并仍由用户决定。
