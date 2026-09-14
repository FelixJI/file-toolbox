# AI Flow v4.0 接入与 v3.2 迁移

执行者：本地 Codex。接入阶段不调用 GLM；正式运行后，Codex ↔ GLM 仍由用户手工跨工具启动。正式审阅由 Codex 内部自动启动新的只读 reviewer 子代理，不要求用户另开 Codex 窗口。

## 1. 先停止旧链路，保留真实工作

读取现有 AGENTS/override、`.ai-flow/`、Git status、未完工 Issue/PR 和本次迁移范围。不要盲拷整个包，不 hard-code 仓库名、PR 编号或某条旧会话状态。

确认旧 runner 与其实际写入任务已结束/安全停止，核对真实进程与改动归属；安装器不会杀进程，也不会删除旧锁“解锁”。不停止无关 Codex/node/Python，不改全局登录/模型配置。若已有本机自启/计划任务/自定义桥接，只停用**确认属于旧 AI Flow 且获授权**的条目。

保留用户未提交内容。优先使用已有合适接入分支/干净 worktree，不默认 stash/reset/clean；旧任务保留分支、diff 和必要证据，之后按 Issue 人工续办，不重放旧 run。

## 2. 预览与应用

包解压到目标仓库外，需 Python 3.10+ 与 Git；只用标准库，不发模型请求。

```text
uv run --frozen python install.py --repo "<仓库根目录>" --upgrade
```

全新安装省略 `--upgrade`。本仓只用安装器预览与静态检查；应用时按差异语义合并定制文件，保留项目守卫。不要直接运行分发包的 `--apply`，其备份实现不符合本仓 UUID 约定。

分发包预览用已有清单识别旧版内容；本仓迁移通过语义差异确认替换范围，必要备份保存在 UUID 子目录。未知定制文件不直接覆盖/删除。退出码 2 / unresolved 不等于升级完成，必须继续语义合并。

备份在 `.ai-flow/migration-backups/`；候选在 `.ai-flow/upgrade-candidates/`。它们不提交。历史 migration manifest 可能出现旧工具名，只用于识别/清理旧版文件；**当前有效规则的施工角色统一称 GLM。**

## 3. 需要删除的活动旧入口

具体路径清单在 `migration/retired-paths.json`。重点：旧调度器、原生协议客户端、event-controller/completion-intake、batch-run/resume、旧通信 schema、旧 runtime 状态与过时模板。

规则、文档、project.json 和根 AGENTS 入口必须一致；根标记更新为 `AI-FLOW-V4`。自定义 AGENTS/override、MCP 配置、项目脚本或外部启动项中若还有**用于编排 Codex↔GLM 的互调**，查清后精确停用。不能把业务中合法使用 RPC/API 的代码误删。

共享配置只保留长期政策：仓库、默认分支、profile、验证命令、风险路径、人工跨工具边界、reviewer 子代理规则等；不保存凭据、CLI 路径、ready/enabled、当前 SHA 或进度。

## 4. Issue 模板与分工字段

安装后检查 `.ai-flow/templates/AI_TASK.md` 和 `GOAL_ISSUE.md` 已生效：

- 每个 Task 必须显式有 `Difficulty`、`Risk`、`Recommended implementer`、`Execution mode`、`Routing rationale`。
- 建议实施者只能是 `Codex`、`GLM`、`Codex-first → GLM`。
- Goal 必须有 `Task | L/R | Recommended implementer | Execution mode | Depends on | State` 汇总表。
- Codex 启动后重新校准，但不能因为建议可调整就把字段留空。

## 5. reviewer 子代理门禁

实现/验证达到 REVIEW_READY 时，Codex 必须自动启动一个**新的只读 reviewer 子代理**。reviewer 自行重新读取 Issue/PR/最新 base/head/diff/代码/验证证据；不改实现、不调用 GLM、不合并。

审阅结论三选一：PASS / CHANGES_REQUIRED / INSUFFICIENT_EVIDENCE。新提交后需新的 reviewer 子代理增量复核。若运行环境无法创建新的只读 reviewer 子代理，标记 `REVIEW_BLOCKED`；不能用主 Agent 自审替代，也不把“默认另开窗口”当标准流程。

## 6. 处理本机报告与 Git 守卫

以下命令在目标仓库根目录执行：

```text
uv run --frozen python .ai-flow/scripts/hygiene.py --tracked
uv run --frozen python .ai-flow/scripts/hygiene.py --migrate
uv run --frozen python .ai-flow/scripts/hygiene.py --migrate --apply
```

只有查到已跟踪本机产物才执行精确迁移。可选 `--install-hooks`；遇现有 hook 管理器不覆盖。报告不进入 Git、PR 或 CI；真正可复用的规则、脚本或测试配置变更正常验证。

## 7. 验证与交付

分发包目录运行：

```text
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python install.py --repo "<仓库根目录>" --check
```

`--check` 只验证静态结构，不证明外部旧进程已停、GitHub 权限可用或 reviewer 子代理在当前 Codex 产品环境实际可创建。

基于当前真实 Issue 做一次**只读规则演练**：网页版规划能产生显式 L/R + 建议实施者；Codex 能给实际填号的 GLM 施工/收尾/阻碍短句；GLM 规则能给返回 Codex 的短句；Codex 规则在 REVIEW_READY 会自动调用 reviewer 子代理而不是要求用户另开窗口。演练不能假称真实施工/审阅已发生。

核对完整 diff、适用项目测试、提交守卫；只提交必要持久化迁移文件，不为安装报告另开 PR，不自动合并。

## File Toolbox 适配说明

在分发包目录执行命令时，为 uv run 添加 --project 指向目标仓库，复用其锁定环境。保留仓库现有 hygiene.py、uv hooks、共享 fallback 和推送目标历史检查；不得用分发包守卫覆盖项目修复。本仓定制文件按语义合并，备份使用 UUID，不引入按本地文件 hash 命名的备份目录。安装器的哈希备份方式不适用于本仓，不直接执行其 --apply。
