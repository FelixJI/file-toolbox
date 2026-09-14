---
name: AI Task v4.0
about: 带显式 L/R 与实施者建议的 AI 开发任务
title: "[AI] "
labels: ""
assignees: ""
---

## Goal / Background

目标、上层 Goal（如有）、已存在相关 Issue/PR：

## AI Flow Routing

> 本区块是任务合同的一部分，规划时必须填写，不能埋到正文末尾。

- Difficulty: L? — 理由：
- Risk: R? — 理由：
- Recommended implementer: Codex / GLM / Codex-first → GLM
- Execution mode：
- Routing rationale：
- Technical owner: Codex
- Review: Codex reviewer subagent（实现/验证就绪后自动调用，只读）
- Merge: human-only

`Recommended implementer` 是规划建议；Codex 开始任务后必须按真实代码/PR重新校准。改变建议时写回理由，不能默默吞掉原本适合 GLM 的施工，也不能把复杂未知根因强行交 GLM。

## Scope / Out of Scope

本次范围：

明确不做：

## Acceptance Criteria

- [ ] AC1：给定……当……则……；可观察证据：
- [ ] AC2：重要失败/边界场景；证据：
- [ ] AC3：必须保持的兼容/不变量；证据：

## Baseline / Dependencies

仓库与目标分支：

已核实 base SHA（未知写 UNVERIFIED）：

依赖的 Issue/PR、是否已真实合并、重叠变更/所有者：

## Validation / Checkpoints

读取真实仓库后确认命令、cwd、回归/集成/用户路径；未确认不编造。必要时分内部 checkpoint，不拆微小 PR。

## Compatibility / Rollback / Authorizations

兼容边界、演练/回滚、需要另行授权的操作：

## Current Stage / Control Pointer

status:

当前 GLM handoff_id / 评论（没有写 none）：

current_actor / next_actor / next_action / user_action_required:

后续 Codex ↔ GLM 交接/结果通过评论追加；reviewer 子代理由 Codex 内部自动调用，不创建人工 Handoff。
