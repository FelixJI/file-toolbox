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

### 推送目标与既有历史

新安装的 pre-push hook 将 Git 提供的实际推送地址 `$2` 通过仅限本次 hook 的环境变量 `AI_FLOW_PUSH_DESTINATION` 传入守卫（手动调用也可用 `--push-destination`），标准输入保持不变。守卫读取该目标当前公布的分支，只排除其中本地可解析提交的祖先；不使用其他 remote 或陈旧 tracking refs 作豁免。查询失败拒绝推送，目标提交尚未 fetch 时保守检查更多历史，可正常 fetch 后重试。tip 始终检查，新增提交中先添加后删除的本机产物仍拒绝。

旧 v3.2 hook 未传目标参数时保留原行为，不能据此声称误报已解除。独立审阅并合并后，使用上述 `--install-hooks` 命令更新带原生守卫标记的本地 hook/fallback；其他 hook 管理器需保留原检查并显式导出 `AI_FLOW_PUSH_DESTINATION="$2"`。本修复不自动安装或绕过当前仓库 hook，也不改写历史。

环境变量交接避免共享 hook 在旧分支上向旧版 guard 传入未知 CLI 参数；旧 guard 会继续原检查，缺少源码的旧分支仍使用共享 fallback。
