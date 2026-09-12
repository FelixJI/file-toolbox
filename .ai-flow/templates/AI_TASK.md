---
name: AI Task v2
about: 带边界、证据和交接记录的AI开发任务
title: "[AI] "
labels: ""
assignees: ""
---

## Goal

一句话描述可观察的行为变化。

## Background / Baseline

- Goal ID / 上层目标：
- 目标仓库与默认分支：
- 已核实的基线 SHA（未核实写 UNVERIFIED）：
- 关联/重叠 PR（先查重）：

## Scope

当前行为范围。

## Out of Scope

不做哪些变化。

## Acceptance Criteria

- [ ] AC1：给定……，当……，应……。证据：
- [ ] AC2：失败/边界场景应……。证据：
- [ ] AC3：保持……兼容/不变量。证据：

## Validation Strategy

实际命令、工作目录、回归/集成/用户路径证据；未知写“接手后读取真实仓库”，不虚构命令。

## AI Routing

```yaml
AI_ROUTING:
  profile: balanced
  difficulty: L2
  difficulty_reason: 单模块且方案清楚
  risk: R1
  risk_reason: 可逆的普通运行时行为变化
  implementer: zcode
  independent_review: codex
  human_merge_required: true  # 初始auto-merge关闭；不是由此字段授权自动合并
```

## Dependencies

依赖的 Issue / PR；默认需合并后才能开工。

## Checkpoints

任务较大时写内部施工段，不拆微小PR；简单任务可无。

## Compatibility / Rollback / Authorizations

高风险变更需要演练、回滚与授权边界。生产部署与真实数据操作另行授权。

## Latest Handoff

状态、领取者、分支/head/base SHA、证据、未解决问题和next_action。可按 STATUS.example.json 追加状态记录。
