# 一句话入口：Codex 接收 Issue 并启动批次

你是用户当前实际打开的 Codex。用户通常只会说：

> 按 AI Flow v3 执行 #123，balanced，推进到可交付边界。

读取项目适用 AGENTS/override、`.ai-flow/AGENTS.md`、`project.json`、指定 Goal Issue/主 Issue、关联 Task Issues、相关代码/测试和未合并 PR。Issue 是任务合同；不要重复生成一份长期人工计划。不存在的远端事实不能编造。

先核对 `.ai-flow/docs/RUNNER.md`。默认 balanced + event-driven；复杂工作 Codex，边界清楚的工作 pi+已配置GLM。用户不再分别启动 pi，也不逐项复制施工提示词。

## 有效本地 runner 已接入

1. 校准 Issue 中的目标、AC、依赖、当前基线、相关 PR 与实际风险。若 Issue 明显过时，先按权限更新任务合同或记录需要更新的事实；不要悄悄改变产品目标。
2. 将本次执行所需内容固化为 `.ai-flow/runtime/intake.md`：Issue/Task Issue 编号与读取时刻、baseline SHA、当前依赖状态、当前可执行范围、必要 AC/约束和相关 PR。它是当前 run 的执行快照，不是新的长期真相源；不要复制密钥/认证材料。
3. 使用干净、专用 Git worktree/分支。不得清理或 stash 用户未提交内容；确认没有其他写入者。
4. 一次调用：`uv run --frozen python .ai-flow/scripts/flow.py start --intake .ai-flow/runtime/intake.md --detach`。旧版 `--plan` 仅保留兼容。本仓所有 Python 入口统一使用锁定的 uv 环境。不要在控制器子会话中再次调用本入口。
5. 启动输出 SUBMITTED 不是 RUNNING。仅允许一次启动确认读取 `status`/日志；不能反复轮询。确认不足则如实说明“已提交，运行存活待验证”。
6. 当前桌面会话结束本轮；把工作区写入权交给 runner。不要与 runner 同时改代码、不要启动 `codex exec resume --last`、不要每隔几秒读取日志。runner 会在工作进程退出后启动新的 Codex CLI 控制/实施/独立审阅会话。

批次完成输出 `.ai-flow/runtime/runs/<run-id>/SUMMARY.md`。只汇总待合并、真实阻断和需决策项。这里不是自动把消息写入原桌面聊天。

## 兼容入口

若用户提供的是旧版计划文件/粘贴正文而不是 Issue，可将其视为一次性 intake 来源继续执行，但不得据此建立第二套长期计划体系。若任务应长期追踪且具备 GitHub 写权限，优先补建/关联 Issue。

## runner 尚未通过接入/缺本地进程能力

先执行接入与只读检查；不重复配置已有 pi+GLM、不擅自更换费用/认证路径。无法启动本机 CLI 的云端 Codex 不能冒充能调用本地 pi。

若缺少真实调用入口，输出 HANDOFF_REQUIRED 和一项准确安装/启动操作；可继续当前工具允许的分析，不无限等待，也不把普通技术决策推给用户。禁止伪称“已通知/已接手”。
