# v4.0 产物与 CI

本文守卫命令在目标仓库根目录执行。

| 内容 | 位置 | 是否提交 |
|---|---|---|
| 规则、模板、实际验证命令、守卫源码 | `.ai-flow/` | 是，按项目真实验证要求处理 |
| 任务、状态、交接 | Issue 正文/评论 | 不另造报告提交 |
| 代码、测试、独立审阅证据 | PR diff / 正文 / 评论 | 代码按正常 PR 提交，沟通记录不另存仓库 |
| 临时诊断、迁移备份、升级候选 | 被忽略的 runtime/backups/candidates | 否 |
| 旧 `local.json` 和旧协议日志 | 精确迁移后本地保留 | 否；v4.0 不依赖 |

不为 BOOTSTRAP_RESULT.md、能力状态、进度或聊天回执开 commit/PR。不引入 `[skip ci]`，也不整体跳过 `.ai-flow/**`，其中仍有可执行脚本和政策。

`.gitignore` 不取消已有跟踪。先运行 `hygiene.py --tracked` 和 `--migrate` 预览，再经核对执行 `--migrate --apply`：只处理明确识别的本机产物，不批量删 Markdown，不覆盖无关暂存。迁移会修改 Git index，但安装器本身不会；已跟踪产物的删除应与这次真实升级合并提交。

提交前 `uv run --frozen python .ai-flow/scripts/hygiene.py --staged`。可选安装本地 hooks：`uv run --frozen python .ai-flow/scripts/hygiene.py --install-hooks`；不得覆盖现有 hooks 或 hooksPath。已有管理器需显式整合 guard；pre-push 的标准输入应完整保留。

分支 diff 检查不能证明提交历史里没有先添加后删除的报告。保留的 pre-push 检查会核对当前推送范围中的提交；历史含本机产物时说明准确位置，不自动改写共享历史或强推。用户确认处置前暂停推送。

守卫是窄路径协作检查，不扫描所有密钥、不隔离权限、不阻止用户手工绕过。不要将测试守卫的探针提交放进真实业务仓库；使用临时测试仓库。
