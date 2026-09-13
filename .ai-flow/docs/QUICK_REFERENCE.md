# 日常速查

**网页版**：读取仓库规则与现状，使用 `prompts/00-master-planner.md` 创建/更新 GitHub Issue 任务合同。单 PR 用一个主 Issue；多 PR 才使用 Goal Issue + 必要 Task Issues。没有写权限时输出 Issue Draft。不要另维护重复计划 Markdown。

**本地 Codex**：

> 按 AI Flow v3 执行 #123，balanced，推进到可交付边界。

Codex 读取 Issue/关联 Task Issues/相关 PR 和代码，固化 `.ai-flow/runtime/intake.md` 后启动 runner。Issue 是长期真相源；intake 是本次运行快照。

入口：`prompts/08-batch-run.md`。控制器：`prompts/10-event-controller.md`。完成交接：`prompts/11-completion-intake.md`。

## 判断表

L1/L2 + R0/R1 → pi；L3 未知根因/跨模块/状态 → Codex；明确拆出的 L3 可 pi；L4/L5 或 R2/R3 → Codex。正式审阅另起 Codex。复杂任务不能为了省额度降级给 pi。

一个 PR 一个语义变化；checkpoint 不建 Issue、不强制拆 PR。依赖未真实合并不推进依赖任务。pi 总派发默认 2 次/任务，执行含审阅总 8 次/任务，控制 24 次/批，超限暂停。

## 命令

```text
python .ai-flow/scripts/flow.py doctor
python .ai-flow/scripts/flow.py status
python .ai-flow/scripts/flow.py stop
python .ai-flow/scripts/flow.py resume --detach
```

运行结果：`.ai-flow/runtime/runs/<run-id>/SUMMARY.md`。状态、日志按需读，不定时问 Codex。

如果是中断而非正常暂停：先查 pending/孤儿进程/Git 状态，再 `resume --ack-interrupted --detach`。不凭报错就重跑整批。

PASS 不是 merge；FINISHED 不是 ACCEPTED；SUBMITTED 不是 RUNNING。当前包不自动合并、不自动在 CI/人工合并后唤醒、不向原桌面聊天注入消息。
