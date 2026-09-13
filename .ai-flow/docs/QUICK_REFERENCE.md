# v3.2 快速参考

网页：按仓库 AI Flow 规划【目标】，复用/建立必要 Issues，不另建计划文件。
本地：按 AI Flow 执行 #123，balanced，推进到可交付边界。

| 动作 | 命令 |
|---|---|
| 原生握手，无模型生成 | uv run --frozen python .ai-flow/scripts/flow.py doctor |
| 真实短探针，用现有额度 | uv run --frozen python .ai-flow/scripts/flow.py doctor --live |
| 查看状态 | uv run --frozen python .ai-flow/scripts/flow.py status |
| 人工连续查看 | uv run --frozen python .ai-flow/scripts/flow.py watch |
| 本轮后停 | uv run --frozen python .ai-flow/scripts/flow.py stop |
| 取消当前原生调用 | uv run --frozen python .ai-flow/scripts/flow.py stop --now |
| 恢复 v3.2 已暂停任务 | uv run --frozen python .ai-flow/scripts/flow.py resume --detach |
| 提交检查 | uv run --frozen python .ai-flow/scripts/hygiene.py --staged |
| 已跟踪产物审计 | uv run --frozen python .ai-flow/scripts/hygiene.py --tracked |

工作流源码：Git 管理。local.json/runtime/报告：不提交。brief 交给 Issue/PR，不造证据 commit。
新 worktree 需要本机 local 配置；升级后的 native 运行不能复用 v3.1 pending。
