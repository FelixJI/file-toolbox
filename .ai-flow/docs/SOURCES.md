# 协议与设计依据

核查日期：2026-09-13。实际接入以本机安装版本与 doctor --live 为准；链接可能随官方重定向。

[N1] OpenAI — Codex App Server
https://developers.openai.com/codex/app-server/
initialize/initialized、thread/start/resume、turn/start/outputSchema、turn/completed、item/completed、turn/interrupt、server-initiated approvals。
实现采用核心稳定 API；不把另起一个 App Server 等同于附着当前桌面 thread。

[N2] Pi upstream — RPC Mode
https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md
原 badlogic/pi-mono 地址当前重定向到上游此仓库。RPC JSONL、prompt/get_state、new_session/switch_session、session-dir、abort/clear_queue、extension UI。

[N3] 同一 RPC 文档的 agent_end / agent_settled 事件约定
agent_end 只结束低层 run，可能还重试/压缩/继续队列；agent_settled 才是本包采用的完整结算边界。

[N4] GitHub — Troubleshooting required status checks
https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
必需 workflow 被 paths/branches/commit-message 整体跳过可能留下 Pending；job 条件与 workflow 过滤不能混为一谈。

[N5] GitHub — Workflow syntax for GitHub Actions
https://docs.github.com/actions/reference/workflow-syntax-for-github-actions
路径过滤、事件、concurrency 与 required 检查相关行为。基础包不自动修改用户 CI。

[N6] 用户仓库读取快照（非本包执行变更）
https://github.com/FelixJI/file-toolbox/pull/86
https://github.com/FelixJI/file-toolbox/blob/main/.github/workflows/ci.yml
已通过 GitHub 连接读取 #86 diff/元数据与 ci.yml；见 FILE_TOOLBOX_MIGRATION.md，安装时应再取最新事实。

## 继承规范中的来源标记

[S1] Codex GitHub code review 文档：https://developers.openai.com/codex/integrations/github/
[S2] Codex 指令发现：https://developers.openai.com/codex/guides/agents-md/
[S3] v3.2 运行接口现在对应 [N1]，不再以 exec 为运行核心。
[S4] GitHub required checks / 分支保护相关要求对应 [N4] 及仓库实际规则。
[S5] Pi 接口现在对应 [N2]。
[S6] 额度以用户实际账户 Usage 页面为准，不硬编码套餐权益或假定不同界面独立计费。
[S7] GitHub auto-merge：https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/automatically-merging-a-pull-request
[S8][S9] Pi 事件语义对应 [N2][N3]；旧版等待 print 进程退出的描述已由 native 协议替代。
