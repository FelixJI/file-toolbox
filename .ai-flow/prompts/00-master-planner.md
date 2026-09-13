# GPT 网页版：目标 → GitHub Issue 任务合同

目标：【用户自然语言目标】

按当前仓库 AI Flow v3 规划。你可以直接读取仓库，因此先读取适用规则、真实代码/测试、相关 open Issues 与未合并 PR；不要把仓库规则重新抄进输出，也不要另建一套与 Issue 重复的人工计划文件。

默认以 GitHub Issue 作为长期任务合同：

- 单一可独立验收、预计一个语义 PR 完成的目标：创建或复用一个主 Issue。
- 确实需要多个独立 PR 的目标：创建一个 Goal Issue，并只为需要独立验收/独立 PR 的语义任务创建 Task Issues。
- checkpoint、文件级修改、Agent 内部步骤不创建 Issue。
- 优先复用已有相关 Issue；发现重叠 PR 时记录冲突/依赖，不重复施工。
- 依赖、难度/风险、AC、验证策略等具体格式直接遵守仓库现有 AI Flow v3 模板与规则。Codex 执行时可基于新证据重新校准路由。

具备 GitHub 写权限时，直接创建/更新这些 Issues；没有写权限时，输出可直接提交的 Issue Draft，并明确 `WRITE_ACCESS_MISSING`。不要退化成另一份长期 plan.md。

完成后只告诉用户：
1. Goal Issue / 主 Issue 编号与标题；
2. 创建或复用的 Task Issues（如有）；
3. 一句话执行入口：`按 AI Flow v3 执行 #<编号>，balanced，推进到可交付边界。`

本网页回合只负责规划和建立任务合同，不实施代码，也不声称已经启动本地 Codex/pi。
