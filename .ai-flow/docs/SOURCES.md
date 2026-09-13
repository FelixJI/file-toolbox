# 官方技术来源

核对日期：2026-09-13。CLI 和产品能力可能改变，部署以本机 --help、实际权限及冒烟结果为准。下面仅说明机制来源；路由等级、任务大小、上限与具体 runner 设计是本包工程选择。

## Codex / OpenAI

**[S1] Codex GitHub 集成 / Review**
https://learn.chatgpt.com/docs/third-party/github
原文档入口：https://developers.openai.com/codex/integrations/github
用于区分 GitHub Review 与完整任务验收，不把默认 P0/P1 报告当全量验收。

**[S2] AGENTS.md 指令机制**
https://learn.chatgpt.com/docs/agent-configuration/agents-md
原入口：https://developers.openai.com/codex/guides/agents-md
用于入口、层级覆盖与项目约束；AGENTS 不自行提供跨进程调度。

**[S3] Codex Non-interactive mode**
https://learn.chatgpt.com/docs/non-interactive-mode
原入口：https://developers.openai.com/codex/noninteractive/
说明 exec、JSON 事件、-o、--output-schema、权限及本地认证复用；本包采用独立 CLI 调用。

**[S6] Managing usage with GPT-6 Astra in Work and Codex**
https://help.openai.com/en/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex
说明 Work 与 Codex 的用量关系；不据此估算用户未知余额，也不声称所有网页版聊天都与 Codex 分离计费。

**[S10] Codex App Server**
https://learn.chatgpt.com/docs/app-server
原入口：https://developers.openai.com/codex/app-server/
提供双向协议、thread/turn、事件。是另行开发客户端的能力，不是本包已实现桌面回调的证据。

**[S11] Codex CLI developer commands**
https://learn.chatgpt.com/docs/developer-commands?surface=cli
用于核对 CLI 的 --ask-for-approval、sandbox、exec 参数。运行前仍必须读取实际安装版帮助。

**[S12] Building a safe, effective sandbox to enable Codex on Windows**
https://openai.com/index/building-codex-windows-sandbox/
2026-05-13 官方工程文章。解释沙箱约束向子进程传播、工作区写入与 .git/.codex/.agents 等受保护路径。本包不通过提升整个沙箱权限来解决 Git 提交问题。

## pi

**[S5] pi 官方网站与 coding-agent README**
https://pi.dev/
https://github.com/earendil-works/pi/tree/main/packages/coding-agent
https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/README.md
说明 print / JSON / RPC 模式、stdin、--no-session、模型/提供商设置及工具边界。既有安装可能仍使用旧 npm 包路径，接入按实际元数据识别，不强制重装。

**[S8] pi JSON 模式事件**
https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/json.md
用于解析完整 assistant 消息和输出事件，不依赖终端屏幕文本。

**[S9] pi 扩展生命周期**
https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/extensions.md
agent_end 不一定是全部重试/后续队列结束；agent_settled 语义不同。本包选择等待一次性进程退出，不要求用户安装新版扩展钩子。

## GitHub

**[S4] Protected branches**
https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
用于 required checks/reviews、真实审批身份与远端门禁。

**[S7] Automatically merging a pull request**
https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/automatically-merging-a-pull-request
GitHub auto-merge 按实际配置的 reviews/checks 工作，不自动理解本包风险等级。本包没有调用该接口。

## 验证声明

技术文档核对不等于用户环境验证。实际测试清单见包根 TEST_REPORT.md；真实 Windows、Codex/GLM 身份、项目命令、后台存活和 GitHub 权限仍由 BOOTSTRAP 验证。源码中的参数、事件格式不应被当成平台永久承诺。
