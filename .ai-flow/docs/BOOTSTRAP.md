# 一次性升级：在目标仓库交给本地 Codex 执行

你是接入工程师。将此包接入当前 Git 仓库，目标为 `balanced` + `event-driven`，沿用现有 pi+GLM 与 Codex 登录。只做接入，不夹带业务重构，不自动合并。普通技术判断自行完成；确需权限/登录/风险授权时一次汇总。

## 1. 先读实际仓库，不碰用户未提交改动

读取原始目标、包内 README/执行规范、现有根和嵌套 AGENTS/override、Git 状态、远端默认分支、依赖清单、CI、未合并 PR。确认工作区、分支与命令，不假定 default branch=main，也不假定 npm/pnpm。

若有未提交工作，使用干净的独立 worktree；不得 stash/reset/clean，不接管其他会话正在修改的目录。新的 worktree 不会自动拥有原目录的项目级 pi 配置、依赖和 ignored 文件，需要识别并在不复制秘密入库的前提下配置。Git worktree 只是隔离工作文件，不是安全沙箱。

## 2. 安装或升级，保留项目定制

将安装包解压在仓库外。调用包里的 `install.py --repo <真实仓库根目录>` 预览；已有 v2 时加 `--upgrade`。审阅计划后加 `--apply`。

安装器只自动替换与随包 v2 哈希完全相同的文件，并为旧内容备份。定制文件不覆盖；新候选写入 `.ai-flow/upgrade-candidates/`。**已有 project.json 永远保留**，包括未配置的原 v2 文件；必须读取候选并手工语义合并 v3 字段，保留真实项目命令和限制。备份与候选不提交。

将仍在生效的 ZCode/assisted 旧规则、旧模板和 v3 规范协调一致；不能只复制 runner 就说升级成功。根 AGENTS 只升级明确管理的入口块；定制块保留项目约束后合并。不要删除非 AI 模板或项目原有保护。

安装包的 `tests/`、`migration/` 是包级验证/迁移材料，不要求整个包入库。只暂存经过审阅的接入文件，不使用未经检查的 `git add .`。

## 3. 核对本地 CLI 和现有身份

要求 Python 3.9+、Git、可从当前环境调用的 `pi` 与 `codex` CLI。Codex 桌面应用已登录不等于终端 CLI 已登录或可见；分别检查。不要擅自安装最新模型、重建 pi 提供商、复制认证文件、换用 API 计费、追加第三方代理或申请新密钥。

查看 `pi --version/--help`、`codex --version`、`codex exec --help` 的实际能力。运行：

```text
python .ai-flow/scripts/flow.py doctor
```

Windows 的 npm `.cmd` 启动器由 runner 尝试按已安装 package.json 的 bin 元数据解析为 Node 命令；失败时填写实际存在的 `[node.exe绝对路径, CLI.js绝对路径]`，不可猜路径或拼接 shell 字符串。不是 npm 安装则按真实二进制设置。

`.ai-flow/project.json` 中先填写真实 repository/default_branch/baseline、已有验证命令、权限状态。`runner.pi_args=[]` 默认继承现有配置；不要凭印象写 provider id。Codex 多 profile 时使用现有已验证 profile，不改变账户认证。

当前 pi 的非交互模式不会弹出项目信任提示；没有适用信任记录时，可能忽略 `.pi/settings.json`、项目扩展等资源。[S5] 特别是新 worktree，要确认 print 模式实际加载了预期配置。不要擅自设全局 always 信任；只有用户已授权该具体项目、已审查本地资源且当前 CLI 支持时，才记录项目级信任或采用本次限定的 trust 参数。配置来源/工作目录变化后重新核验 provider/model 与通道。

## 4. 一次确认本地执行边界，再进行真实冒烟

解释并确认以下有限授权：在该可信 worktree 启动本地 pi/Codex 子进程；运行仓库现有测试；使用 runner 进行显式路径的本地建分支和提交。**不含自动合并、部署、真实数据操作、新费用、修改安全策略。**

获授权后可设 `runner.trusted_local_execution=true`；授权本地 Git 再设 `runner.allow_local_git_writes=true`。这不是完整计算机权限的授权；不要替用户开启 danger-full-access 或绕过组织策略。若用户已明确授予同等本地权限，记录该范围，无需重复询问。

运行：

```text
python .ai-flow/scripts/flow.py doctor --live
```

该步骤使用现有模型额度，pi 禁用工具、Codex 用只读检查，各返回一个固定标记。检查退出码、完整事件、模型/提供商字段，确认实际使用的是用户已配置的 GLM 与预期套餐通道。模型名称不足以证明计费通道，需核对本地提供商设置；报告时脱敏。确认仓库未变更。

`doctor --live` 不证明真实 shell/测试/网络权限已全部可用。进一步在专用测试分支做一个可清理的小型业务闭环：Codex 分类→BRANCH→pi 或 Codex 实施→必要时 COMMIT→独立 REVIEW→FINISH。测试数据不接触生产，不为演练创建费用。保留完整证据。

Codex 实现默认 workspace-write；其 `.git` 可能仍只读。[S12] 由已授权 runner 的 BRANCH/COMMIT 处理本地 Git，不开放整个文件系统，不将提交失败误认成模型能力不足。runner 不执行任意 Git/shell 字符串，保留现有 hooks 与签名要求；这些要求阻塞时需如实暂停。

## 5. 验证“一句话交接后是否存活”

先用只读计划（不改文件、直接核验后 FINISH）验证 runner，再测试 `--detach`。必须核对**启动 Codex 入口结束后**进程仍存活，并最终留下完成回执；启动成功不等于宿主允许后台存活。控制器也需要读取本地 Codex/pi 凭据和调用模型网络，不能假定沙箱子进程具备这些能力。

若当前平台阻止后台进程、终端 CLI 或网络凭据读取，不解除平台限制、不改安全策略自救。降为 PARTIAL：在用户已授权的普通本地终端以前台启动同一个 runner，让终端保持打开；这是一个本地调度进程等待，不是 Codex 轮询。若希望以后仍一句话启动，需要用户在此环境一次性配置允许的启动入口，再重做存活演练。

云端 Codex 无法天然调用用户电脑里已配置的 pi；此方案默认本地 Codex/CLI。不能将云端任务状态写成 LOCAL_READY。

## 6. 项目验证、配置完成与合并

运行真实存在的安全基线验证，记录 command/cwd/exit/SHA。基线失败、未跑、网络受限、GitHub 无权限均分别标明。远端 CI、Issue/PR 写入、发布证据能力单独核实；没有这些能力不编造链接。

确认 `.ai-flow/runtime/` 被 Git 忽略；运行日志可能包含代码与敏感内容，不直接上传。确认整个接入修改已在接入分支提交，运行前工作区干净。设置 `mode=event-driven`、`profile=balanced`、`auto_merge.enabled=false`。

只有必要能力实测成立、授权有依据、冲突已协调，才将 `configuration_status=ready` 与 `runner.enabled=true`。状态开关只是软件条件，不是外部授权证明。为了进行受控演练可以临时启用，演练未通过必须关闭并标 PARTIAL。

创建接入 PR（已有授权且具备能力时），否则保留分支与准确 handoff。不擅自修改 branch protection、CI 权限或自动合并设置。来源与 GitHub 门禁建议见 docs/SOURCES.md、GITHUB_SETUP.md。

## 最后只汇总一次

输出 READY / PARTIAL；已验证的 CLI 版本、GLM 提供商通道和调用结果；后台存活结果；业务/审阅闭环证据；未完成的权限/CI/模型限制；真正需要用户一次操作的事项；以后执行的一句话。

日常不要求用户手工拆 L1–L5、启动 pi、复制日志、追问状态或逐条转交审阅。不能完成的能力必须标明，不能以“理论支持”冒充实测。
