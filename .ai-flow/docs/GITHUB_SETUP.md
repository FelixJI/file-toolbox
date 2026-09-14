# v4.0 GitHub 接入边界

只需要当前使用者已有的 Issue/PR 读写能力。沿用仓库现有连接或已登录工具，不新增自动调用服务，不索取或复制私人令牌。没有读写权限时如实降级为待发布摘要。

安装器提供普通 Markdown Issue / PR 模板，不自动创建标签、不配置 Actions、不改仓库设置、不启用 auto-merge。现有模板若已定制则保留并给候选；由接入 Codex 在保留业务要求后语义整合。

日常规划前读取真实 open Issues 和未合并 PR，避免重叠施工。任务的 `implementer` 是工作角色，不要求仓库存在名为 Codex/pi/zcode 的真实 GitHub 用户；不要因此乱设 assignee。共享账号的不同会话不是两个独立 GitHub 批准身份。

正式审阅文本必须定位当前 PR 的 base/head、AC 证据和 finding；它不是平台权限。保持仓库现有 required checks、审批身份与分支保护，未知配置写“未核实”。

合并仍由用户决定。远端合并/CI 结果不会自动唤醒本工作流，用户下一次手动启动 Codex 时再读取实际结果。
