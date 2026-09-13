# 恢复本地运行 / 交接

先读 AGENTS、project.json、原始计划和 `.ai-flow/runtime/runs/<run-id>/state.json`，再核对实际 Git 状态与最近回执。旧聊天不是恢复依据。

正常 PAUSE：确认外部原因已解除，使用 `flow.py resume --run <id> --detach`。不得重新 start 相同批次来重置次数或重做完成任务。

pending 中断：检查 PID、是否存在孤儿子进程、已提交/未提交 diff、调用输出；确认不会并发写入后，才使用 `resume --ack-interrupted`。这个标志是确认已核对，不是自动杀进程。Git 操作可能已生效而回执未写，不能重放 add/commit/建分支。

若工作流/CI 政策已变更，旧 run 不继续；审查差异后用明确 handoff 建立新 run。保留基线、当前分支/head、已完成任务、旧 review/CI 绑定 SHA、待办、已尝试失败和真正需要授权的事项。

入口完成交接后结束本轮，不轮询。FINISHED 不重放。外部依赖/CI 未变就 PAUSE，不忙等。详情见 docs/RUNNER.md。
