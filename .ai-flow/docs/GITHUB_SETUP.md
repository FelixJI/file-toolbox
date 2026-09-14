# v4.0 GitHub 接入边界

只需要当前使用者已有的 Issue/PR 读写能力。沿用仓库现有连接或已登录工具，不新增跨工具自动调用服务，不索取或复制私人令牌。没有读写权限时降级为待发布摘要。

安装器提供普通 Markdown Issue / PR 模板，不自动创建标签、不配置 Actions、不改仓库设置、不启用 auto-merge。现有模板若已定制则保留并给候选；接入时在保留业务要求后语义整合。

日常规划前读取真实 open Issues 和未合并 PR。Task 的 `Recommended implementer` 是流程角色，只写 Codex / GLM / Codex-first → GLM，不要求仓库存在同名 GitHub 用户，也不要因此乱设 assignee。

Goal Issue 必须直接汇总 Task 的 L/R、建议实施者、执行模式、依赖和状态。PR 的 reviewer 子代理文本必须定位当前 base/head、AC 证据和 findings；它不是 GitHub 平台批准身份。

保持仓库现有 required checks、审批身份与分支保护，未知配置写“未核实”。合并仍由用户决定。远端合并/CI 结果不会自动唤醒 Codex 或 GLM；用户下一次手工启动时再读取真实结果。
