# 本地事件驱动 runner

版本 3.1.0。实现：`.ai-flow/scripts/flow.py`，Python 3.9+ 标准库，无额外 Python 依赖。

## 1. 为什么不让 pi 自己回调正在工作的 Codex

“给 Codex 发消息”有两层含义：一是把结果交给下一次 Codex 执行；二是向某个已打开桌面聊天插入新消息。本包实现前者，不假定后者可用。

Codex 官方提供 `exec`、JSON 事件、最后输出文件和输出 schema，可用于脚本编排。[S3] App Server 提供 thread/turn 和双向事件，但那是需要建立连接、持有会话并处理生命周期的另一套集成；不等于任意外部进程能够无冲突地唤醒桌面原会话。[S10]

这里由**一个普通本地 Python 进程**持有控制权。它启动单次 pi/Codex，使用操作系统等待进程结束，收集退出码与完整 JSON 事件，再启动新 Codex 控制会话。等待期间不会发出用于询问进度的模型调用；工作 Agent 自己正常处理任务仍会消耗其配置额度。

pi 扩展的 `agent_end` 之后仍可能自动重试、压缩重试或处理排队内容；直接据此回调容易抢跑。[S9] 本包不装扩展：使用 `pi -p --mode json --no-session`，等待实际进程退出，并从完整 `message_end`/结束事件提取最终报告。[S5][S8] 不把流式半句话当完成，不因中途一次报错就忽略后来成功恢复，也不把最终 error/aborted/length 当成功。

## 2. 三种 Codex 角色

入口会话读取 08-batch-run，核对目标后启动 runner，交出工作区并结束本轮；不在自己的回合里同步等待整批工作。

控制会话是新的 `codex exec` 只读调用，只做任务合同核实、范围校准、路由和下一动作。实现会话默认 workspace-write，完成一个有边界的任务。审阅会话是另一次只读调用，独立读取 diff 与证据，不能沿用实现者结论。

三者共享 intake 快照与证据，不共享正在进行的上下文。Issue 是长期任务合同；intake 是启动时快照。每次控制返回简短 checkpoint，外层在下一轮传入，避免无限续长聊天。没有使用 `codex exec resume --last`，也没有盲目续接桌面 thread_id。

## 3. 调用与权限

实际 pi 命令的固定尾部：

```text
pi [已验证的附加参数] -p --mode json --no-session
```

任务通过 stdin 输入。默认不覆盖 provider/model，使用工作目录、用户设置与环境中已经配置的 GLM。独立 worktree 下的项目级配置可能不同；当前 pi 非交互模式还会按项目信任状态决定是否加载项目资源，未获信任可能忽略项目级设置，接入时必须查证。[S5] 不自动全局信任新资源。套餐实际通道以用户已配置的 provider 及账户说明为准，不凭模型显示名判断。

Codex 调用形态：

```text
codex [已有全局参数] -a never exec --sandbox read-only --json -o <输出> --output-schema <schema> -
codex [已有全局参数] -a never exec --sandbox workspace-write --json -o <输出> -
```

控制器/审阅者用第一类；实现者用第二类。CLI 返回零退出码还必须存在 `turn.completed`、不存在 `turn.failed` 并产生输出。`-a never` 表示不能交互请求提权，不等于取消沙箱。此包不使用全权限绕过，不导入新认证。

**启动环境很重要**：如果父 Codex 工具的操作系统沙箱会限制全部后代，runner 也继承该限制；启动子进程不会自动获得凭据/网络/后台存活能力。一次性接入需要在允许的本地环境验证它，不能通过清空安全环境变量或偷偷换权限逃逸。

## 4. 七类结构化动作

| action | 外层行为 |
|---|---|
| PI | 启动一次已配置 pi，做有界任务 |
| CODEX | 启动一次独立 Codex，实现/调查/验证 |
| REVIEW | 另起只读 Codex，严格校验审阅 JSON 与 base/head |
| BRANCH | 外层执行有限的本地 Git 建/切分支，不调用模型 |
| COMMIT | 外层对显式文件路径执行本地 add/commit，不调用模型 |
| PAUSE | 保存原因和下一步，停止；等待依赖/CI/授权时使用 |
| FINISH | 保存本地批次结果；不代表已合并/部署/最终验收 |

BRANCH/COMMIT 需要 `runner.allow_local_git_writes=true` 的一次授权。这是避免 workspace-write 内 `.git` 受保护时反复失败的**有限本地操作接口**，不是解除 Codex 沙箱。[S12] `instructions` 必须是 JSON 数据，不执行模型输出的 shell 命令：

```json
{"branch":"codex/issue-123","start_sha":"真实完整commit SHA"}
```

```json
{"message":"fix: 修复目标行为","paths":["src/example.ts","tests/example.test.ts"]}
```

BRANCH 只允许安全的 `codex/` 分支名；新分支从明确 SHA 建立。切已有分支仅允许本 run 创建过的分支；工作区必须干净且无待审阅任务。不要据此绕过依赖“实际合并”的要求。若当前已有干净的专用 feature branch 可直接使用，禁止接管其他人的活动分支。

COMMIT 拒绝默认分支/detached HEAD；显式路径必须精确覆盖当前全部改动，不能夹带未解释的用户修改、目录通配符、工作流/凭据路径。不强推、不推送、不合并。保留项目已有 hooks 与签名要求；钩子可能有副作用，因此仍只能用于可信本地仓库。路径限制不是通用秘密扫描，不保证自动识别代码中的密钥。

外层在写入前记录 pending，完成后记录回执；中断时可能已建分支或已经暂存，必须人工/入口 Agent 核对真实 Git 状态，不能重放不明操作。

## 5. 配置

`project.json` 的 `configuration_status=ready`、`runner.enabled=true`、`runner.trusted_local_execution=true` 同时成立才可运行。初始全部未启用，必须由 BOOTSTRAP 按实测结果设置。已有 v2 配置保留，需要合并候选。

`pi_command`、`codex_command`、`pi_args`、`codex_global_args`、`codex_exec_args` 都是参数数组，不接受一整段 shell 字符串。不要把 API key 放进数组。Windows npm shim 按 package.json 解析为 Node + 实际入口；无法解析则填现有绝对路径，不自动下载或重装。

默认上限：控制决策 24 次/批、执行与审阅合计 8 次/任务、pi 调用 2 次/任务；控制/工作/审阅超时分别 900/3600/1800 秒。它们是停止保护值，不是模型性能承诺。需要更大队列时应在批次启动前按范围调整，不由业务 Agent 自改配置。超限后不会自动新建 run 刷新额度。

pi 的“总派发 2 次”比规范中的“同根因 2 轮失败”更保守：通常初次实现 + 一次定向整改，之后交 Codex。L4/L5 或 R2/R3 的 PI 路由被脚本拒绝。难度、风险与 task_id 仍由模型判定，稳定 ID/诚实分类依靠协议与审阅，不是不可篡改的外部安全判定。

## 6. 命令速查

全局 `--repo` 必须放在子命令前；默认当前工作区根目录。

```text
uv run --frozen python .ai-flow/scripts/flow.py doctor
uv run --frozen python .ai-flow/scripts/flow.py doctor --live
uv run --frozen python .ai-flow/scripts/flow.py start --intake .ai-flow/runtime/intake.md --detach
uv run --frozen python .ai-flow/scripts/flow.py status --run <run-id>
uv run --frozen python .ai-flow/scripts/flow.py stop --run <run-id>
uv run --frozen python .ai-flow/scripts/flow.py resume --run <run-id> --detach
```

`doctor` 只检查本地 CLI 帮助与版本；`--live` 使用现有额度做无工具标记响应。它不自动改 ready、不证明实际业务工具/网络可用。

`start` 要求干净专用 worktree；intake 不超过 128 KB，推荐放在 ignored `.ai-flow/runtime/intake.md`。`--plan` 仅作为旧版兼容别名。`--detach` 只把普通本地进程与当前终端分离，不是服务安装，不保证宿主会允许它存活。返回 SUBMITTED 后最多进行一次启动状态检查，不能让入口 Codex 为等到 RUNNING 而不断查询。

后台存活被阻止时，使用用户已授权的普通本地终端以前台 start，保持终端；不要在受限宿主中继续尝试绕过权限。macOS/Linux 使用新会话，Windows 使用分离进程标志，但**真实 Windows 存活行为必须在用户机器验证**。

## 7. 状态、日志与审阅

```text
.ai-flow/runtime/latest.json
.ai-flow/runtime/runs/<run-id>/
  intake.md                本次运行的 Issue/基线执行快照
  state.json               权威本地运行状态
  events.jsonl             事件审计投影
  runner.log               detached runner 自身日志（如适用）
  001-controller/ ...      每次调用独立目录
    prompt.txt
    stdout.jsonl
    stderr.log
    result.json / result.md
    receipt.json
  SUMMARY.md               批次停止/完成摘要
```

正常状态：SUBMITTED → RUNNING/WAITING_* → PAUSED/FINISHED。失败可为 CALLBACK_FAILED、PROTOCOL_ERROR、BLOCKED、POLICY_CHANGED、LIMIT_REACHED、ERROR、INTERRUPTED、STOPPED。等待工作进程不是卡死，也不是模型轮询；按需查看即可。

state.json 原子替换，event_id 去重；events.jsonl 是可重建审计副本，不作为自动重放队列。本包不承诺数据库级 exactly-once：进程可能在提交成功、回执尚未持久化时中断。遇到 pending，只复核事实再接续，不自动重做。

任何实施变更标记待独立审阅。审阅前要求干净且提交明确，base 是 head 祖先；PASS 必须精确匹配当前 SHA、AC 证据非空、无 P0/P1 或其他 blocker。新增提交或外部改动不能用旧审阅完成 FINISH。所有实际代码变更都经审阅，本 runner 比一般 R0 文档最低门禁更保守。

本地 SHA 校验不等于验证远端 CI 成功；所声称的命令/测试证据还需审阅者核实。本包没有提供可信 GitHub check publisher、远端签名审阅身份或服务器强制门禁。

## 8. 停止与恢复

stop 写一个停止标记。当前子进程允许完成或到超时，下一派发边界停止。它不会撤销代码、丢弃文件或立即杀掉业务进程。

正常 PAUSE：原因解除后按需 resume；不会定时检查 CI 或合并状态。FINISHED 再次 resume 不执行。任务已达调用上限，不因 resume 重置计数。

中断 pending：先检查 state 中 role/PID、输出、Git diff 和日志；确认没有仍在运行的 pi/Codex/子测试进程；必要时通过操作系统终止。然后：

```text
uv run --frozen python .ai-flow/scripts/flow.py resume --run <run-id> --ack-interrupted --detach
```

该标志表示你已确认不会与孤儿进程并发；脚本不可靠地推测 PID 是否重用。它记录 RECOVERY，让新的 Codex 控制会话核对实际改动、补验证/审阅，不原样重放旧任务。

超时会尝试终止子进程树。父 runner 被强制杀死、机器重启或工作 Agent 自行脱离子进程树时，仍可能留下残余活动/不完整输出。不要仅凭锁空闲就认为没有写入者。

## 9. 自动化边界

锁位于 Git common directory，保守地串行化同仓库所有 worktree 的本 runner。它是协作锁，不约束用户终端、其他 Agent 或恶意代码。入口会话交接后不能继续修改工作区。子 Agent 设置 AI_FLOW_CHILD=1，规则要求只交结果，不再次启动 runner/其他 Agent；脚本也拒绝嵌套启动，但同权限恶意进程可以改变环境，不能称作安全隔离。

无 HTTP 监听端口，无对外回调服务，无额外云端密钥。日志含源码/工具输出，应留本地并按需脱敏；不要自动上传整份 prompt/stdout。

没有自动 merge/deploy 动作，没有远端 CI/合并唤醒，没有系统任务服务、通知客户端或原桌面消息注入。相互独立的已就绪任务可接着做；有未合并依赖、必需 CI 未回、缺授权/身份时 PAUSE。用户决定恢复后，控制器重新核实真实基线与结果，不视为全部完成。

## 本仓适配

所有 Python 入口通过 `uv run python` 执行。BRANCH 使用 `codex/` 前缀。工作区变化比较 Git HEAD、分支、status、二进制 diff 和未跟踪内容；策略变化直接比较本地内容快照，不计算额外 SHA-256。快照留在 ignored runtime，旧包运行记录不复用。实际项目质量命令以 `.ci/project.json` 为准。
