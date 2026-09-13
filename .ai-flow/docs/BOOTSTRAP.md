# 安装 / 升级 AI Flow v3.2 Native

这是交给**本地 Codex**执行的一次性接入任务，不是业务 runner 的子任务。交付包必须解压在目标仓库外。
执行目标：Codex App Server + Pi RPC；保留 Issue-first、balanced、单写入者、独立审阅和既有登录。
本文件授权范围是安装/迁移本工作流、本地 hooks 与验证；不授权自动合并、部署、真实数据操作、付费服务或放宽 CI/安全策略。

## 一句话升级

> 按附件 AI Flow v3.2 的 BOOTSTRAP.md 将当前仓库升级为 Codex App Server + Pi RPC，保留现有规则和 Codex/pi+GLM 登录，迁移已跟踪的沟通过程文件及本机状态，完成协议与提交守卫验证；只提交持久化代码/规则的必要变更，不提交报告，不为进度另开 PR。

## 一句话全新安装

> 按附件 AI Flow v3.2 的 BOOTSTRAP.md 在当前仓库安装 Codex App Server + Pi RPC 工作流，沿用已配置的 pi+GLM 和 Codex 登录，完成本机接入与提交守卫验证；运行报告只留本地，日常使用 Issue-first、balanced。

## 1. 安全接管与读取

读取当前项目 AGENTS/override、已有 .ai-flow、Git status、相关接入 Issue/PR。明确仓库根目录和本次集成分支。
有活动 runner 先请求其在完成边界停止；核对它实际停止并释放仓库锁。不能只删除锁文件。
不要在旧 pi/Codex 仍写入时覆盖调度器，不要把 v3.1 pending 记录直接交给 v3.2 resume。
用户未提交工作不能 stash/reset/clean。用干净专用 worktree；不要把整个压缩包复制进仓库。

如果这个仓库是 FelixJI/file-toolbox，另读 FILE_TOOLBOX_MIGRATION.md，先核实 #86 的当前状态与真实 diff。
不要假定它仍 open，也不要机械 cherry-pick 只有本机状态的提交。优先复用已有接入分支/PR承载真正升级；必要时才建一个集成 PR。

## 2. 预览与安装

在解压包目录运行；Windows 可把 python 替换为 py -3，项目使用 uv 时沿用该项目的 Python 启动方式。

```text
uv run --frozen python install.py --repo "<仓库根目录>" --upgrade
uv run --frozen python install.py --repo "<仓库根目录>" --upgrade --apply
```

全新安装省略 --upgrade。需要 Python 3.10+，仅标准库；复用现有 Git、Codex CLI、pi CLI。
升级器按 v2/v3.1 文件哈希替换未经定制的规则，保留项目业务内容；定制文件给出 ignored 的 upgrade-candidates。
逐项语义合并候选，不能看到脚本文件已更新就忽略仍引用旧 exec/print 行为的定制提示词。
升级器在写入时获取与旧 runner 相同的仓库锁；不改远端、登录、模型全局设置或现有 CI。

## 3. 分离共享配置与本机状态

共享 `.ai-flow/project.json` 只保留项目稳定配置：仓库、默认分支、profile、验证命令、风险路径、运行上限、安全/合并边界。
本机 `.ai-flow/local.json` 被 Git 忽略：CLI 路径/参数、ready/partial、enabled、信任授权、能力探测、模型/提供商核验。
临时产物、当前 baseline/head、安装报告、日志、receipt、会话索引全部位于 `.ai-flow/runtime/`。

升级自动把旧 project.json 中本机字段迁到 local.json/legacy，并重置为 partial、enabled=false；这不是丢配置，而是不能拿 exec 的测试证明 RPC 已就绪。
既有 pi_command/pi_args、Codex command/global args 优先保留。凭据继续由原 CLI 管理，绝不复制 auth.json 到 local.json。
legacy.codex_exec_args 若非空，逐项转换：model/provider/effort 转 local.runner 对应字段；exec 专属参数不能盲目拼到 app-server；无法确认的参数留缺口，不悄悄删除有效限制。
不强制更换 npm 包名、GLM 通道或付费方案；仅在实际 CLI 缺协议能力时说明必要升级，保留原认证。

## 4. 清理历史沟通过程文件，安装提交守卫

先预览，再执行精确迁移：

```text
uv run --frozen python .ai-flow/scripts/hygiene.py --tracked
uv run --frozen python .ai-flow/scripts/hygiene.py --migrate
uv run --frozen python .ai-flow/scripts/hygiene.py --migrate --apply
uv run --frozen python .ai-flow/scripts/hygiene.py --install-hooks
```

migrate 只处理识别到的本机产物，不扫描删除所有 .md。它备份当前内容到 ignored runtime/legacy，然后 git rm --cached 精确取消跟踪并移走原报告；local.json 取消跟踪后仍保留原位，以免丢失正在使用的本机配置；不使用 -f、不动无关暂存内容。
删除历史已跟踪的报告是一次有意义的迁移变更，应与本次升级一起提交；之后报告不再进入版本控制。
**.gitignore 不会取消对已跟踪文件的跟踪。** 不要仅加 ignore 就宣称已解决。

若已有 pre-commit/pre-push 或 core.hooksPath/Husky/pre-commit 管理器，脚本拒绝覆盖；在本次接入中保留原有检查并整合以下检查：
- pre-commit 调用 hygiene.py --staged。
- pre-push 调用 hygiene.py --pre-push，并完整转交原始 stdin 四列 ref 数据；不要让前一个 hook 消耗 stdin 后再传空输入。

验证守卫实际被 Git 执行；不能仅在 AGENTS.md 写“禁止提交”。使用临时独立 Git 仓库测试，别在真实 PR 制造探针提交。
提交规则：精确文件列表，不用 git add . / -A；不提交 local.json、runtime、备份、候选、BOOTSTRAP_RESULT.md；不为了安装状态单独生成 PR。
短摘要放在本次对话或已有 Issue/PR 的正文/一条评论；不要把完整日志、主机路径或账户信息公开。

## 5. 协议、模型与运行验证

先运行离线测试（在解压包目录）：

```text
uv run --frozen python -m unittest discover -s tests -v
```

在目标仓库运行不发起模型生成的协议握手：

```text
uv run --frozen python .ai-flow/scripts/flow.py doctor
```

doctor 会启动 CLI、加载已有配置/扩展并做 initialize/initialized 或 get_state；不是只 grep --help，也不是验证了真实模型调用。
Pi 仍继承本机文件/进程权限，Codex sandbox 并不能包住 Pi。确认用户已有可信本地执行意图后，设置 local.runner.trusted_local_execution=true；不得给未信任项目静默启用。
然后运行短的真实模型探针（会使用原有额度）：

```text
uv run --frozen python .ai-flow/scripts/flow.py doctor --live
```

两个 Agent 各连续两轮，在同一进程中返回固定短标记。所装 CLI 的协议以本机生成的 schema 和真实响应为准；`thread/start.sandbox` 使用 `read-only`/`workspace-write`；`turn/start.sandboxPolicy.type` 使用 `readOnly`/`workspaceWrite`，以本机 schema 为准。核对 Codex 原登录通道、Pi 实际 provider/model 是用户已配置 GLM；还要核对静态/动态结果和工作树未变化。
新版 Pi 必须支持 agent_settled；agent_end 后仍可能继续重试。探针失败不得自动回退到“收到 agent_end 就成功”。
Windows npm shim 由包内元数据解析到 node + CLI 入口，不把 prompt 插进 cmd.exe。解析失败时填本机实际绝对 node/CLI 路径到 local.json，不能编造路径。

权限/输入请求会被拒绝并暂停，不会默认 Accept；先调查具体原因，不用 full access 或关闭保护“修好”探针。
独立审阅验证使用新 thread，绑定实际 base/head。角色有独立上下文，不要求为每轮重启 Codex 进程。
接入业务演练采用一个可回滚的小任务；本地验证、提交、独立审阅后再一次性 push。只读/无代码探针不需要新 PR。

完成后将实际能力与局部启用状态写 local.json，而不是 project.json。每个 worktree 的 local.json 都是本机文件；新 worktree 按已验证配置复制并重新核对路径/基线，不能以为 Git 会传播它。
允许运行条件：local.configuration_status=ready，local.runner.enabled=true，trusted_local_execution=true。有限本地分支/提交另由 allow_local_git_writes=true 明确授权。

## 6. 后台存活与显示

若需要脱离入口 Codex 回合持续运行，必须在用户实际 Windows/Codex 宿主验证。SUBMITTED 和 launcher PID 不是存活证明。
不能在当前会话内凭口头预测断言“关闭这个会话以后一定继续”。未验证时用普通可信终端前台运行，并把缺口只记录本地。
不要为更新这项能力再提交一个“ready PR”。

```text
uv run --frozen python .ai-flow/scripts/flow.py status
uv run --frozen python .ai-flow/scripts/flow.py watch
```

watch 是人工查看入口，每秒刷新本机快照，不调用模型或询问 Agent 进度。原 Codex 桌面会话不会自动出现 Pi 子 Agent 卡片。
要退出 watch 用 Ctrl+C；它不停止任务。stop 在本轮后停止；stop --now 向当前协议会话发送 interrupt/abort。

## 7. CI 与交付

本次基础包不改现有 CI/required checks，先消除报告/本机配置的提交。不得用 [skip ci] 或将必需 workflow 整体 paths-ignore 来掩盖无意义提交。
确需后续优化时按 docs/ARTIFACTS_AND_CI.md 对现有 plan/重任务/required 汇总分层；不能笼统跳过 .ai-flow/**，这里有真正可执行代码和安全规则。
提交前执行 hygiene.py --staged；推送前核对相对真实基线的 diff、当前 SHA 审阅和本地验证；push 后仅有新实际修改才再 push。

最终向用户给：已安装版本/协议、已验证与未验证事项、本地报告路径、确实发生的代码/规则变更、一个日常入口。安装报告可保存到 `.ai-flow/runtime/bootstrap/BOOTSTRAP_RESULT.md`，不得提交。

日常：**按 AI Flow 执行 #123，balanced，推进到可交付边界。**
