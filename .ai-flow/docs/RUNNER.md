# v3.2 Native Coordinator

## 1. 协议生命周期

Codex 以 `codex app-server` 建立私有 stdin/stdout JSONL；先 initialize、等待响应、再 initialized。每个连接只握手一次。
thread/start 建立独立角色会话，thread/resume 只使用这个 run 保存的明确 ID，不使用 resume --last、不接管活动桌面 thread。
turn/start 携带输入与可选 outputSchema；根据请求 ID 匹配响应，提前抵达的 notifications 会缓存而非丢弃。
只有匹配当前 thread/turn 的 turn/completed 才结束当前调用；failed/interrupted 不是成功。最终文本来自完成的 agentMessage，而不是未完成 streaming delta。

Pi 使用 `pi --mode rpc --session-dir <ignored目录>`，保留既有 pi_args 中验证过的 GLM 配置。get_state 做一次握手。
每个 task 用独立 session；同任务整改复用，切任务通过 new_session/switch_session；检查 session switch cancelled 结果。
prompt 的 success response 只证明收到了命令，不能当完成。message_end/agent_end 收集报告，**agent_settled** 才表示本轮重试/压缩/排队工作已结束。
完成后只做一次 get_state 边界校验，确保 isStreaming/isCompacting 为 false 且 pendingMessageCount=0，并保存 sessionId/sessionFile。
这不是轮询；不每秒调用 get_state，也不由 Codex 反复问 pi 好了没有。

默认不支持悄悄回退到旧版 agent_end：缺少 settled 的版本应在 doctor --live 中暴露，再核对安装版本/协议。

## 2. 长连接不等于无限后台守护

每个 runner 生命周期通常一个 Codex server、一个 Pi RPC process。Controller thread 复用、Worker 按 task 隔离、每次 Review 新 thread。
PAUSE/FINISH/STOP/error 会收起本 runner 创建的子进程；下次 resume 重新握手，仅恢复已记录的本 run 会话身份。
留有 pending 的崩溃禁止自动重放。需确认没有孤儿写进程、核对代码/远端副作用、人工确认 --ack-interrupted；这不是自动 exactly-once 保证。
v3.1 的进程式 run 不可由 v3.2 resume，版本不匹配会拒绝。

state.json 仍是可重建的调度 checkpoint；wire 事件是活跃会话的事实来源；receipt/SUMMARY 是审计输出，不是 Agent 间传输文件。
checkpoint 含队列与当前任务，避免依赖纯聊天记忆。进程级退出只处理失败/关闭，不作为正常任务完成信号。

## 3. 配置

共享 project.json：default_branch/profile、验证命令、风险路径、worker/controller 上限、backend=native。
本机 local.json：enabled、trusted_local_execution、allow_local_git_writes、CLI argv、model/provider/effort、能力核验。全部必须 ignored 且未被 Git 跟踪。
绝不能把 secret/API key 写入项目配置；认证由原 CLI 保存。本包不调用登录，不把 Codex 切到 GLM，不把 GLM 换成另一个收费通道。
controller/review 用 read-only，worker 用 workspace-write；approvalPolicy=never。networkAccess 默认 false，需要原有范围的网络权限时明确核验 local 设置。
Pi 没有由本包提供的系统沙箱；信任确认和 worktree 都不能限制它访问本机其它路径。需要强隔离时另行设计，不能声称 Codex sandbox 覆盖 Pi。

## 4. 查看

```text
uv run --frozen python .ai-flow/scripts/flow.py status
uv run --frozen python .ai-flow/scripts/flow.py status --run <run-id>
uv run --frozen python .ai-flow/scripts/flow.py watch
```

status 包含运行阶段、runner/active agent 的进程存活、pending.protocol、thread_id/turn_id/session_id、最新协议事件和相关本机日志目录。
WAITING_PI 意味着当前派给 Pi 的调用尚未完成；“pi 进程还活着”在长连接架构也可能只是 idle，不能单靠 PID 宣称在工作。
watch 是人使用的快照刷新，默认 1 秒，无模型请求；最后事件长时间不变可能是模型/网络/工具等待，需要查看日志，不能据此直接认定挂死。
Ctrl+C 只退出 watch，不终止任务。

## 5. 停止 / 取消

```text
uv run --frozen python .ai-flow/scripts/flow.py stop
uv run --frozen python .ai-flow/scripts/flow.py stop --now
uv run --frozen python .ai-flow/scripts/flow.py resume --detach
```

stop 在当前任务完成后不再派发。--now 设置本机 CANCEL 标记；一个非模型线程只检查这个控制标记，发送 turn/interrupt 或 clear_queue+abort。
取消后等待有限时间，必要时终止**当前进程句柄对应的本 runner 子进程树**；不根据状态文件中的任意旧 PID 杀进程。
实现中这个控制标记检查和人工 watch 刷新是本机 I/O，不是 Agent 状态轮询；正常完成完全由 wire 事件触发。
取消不撤销已经发生的文件/网络/Git 操作；恢复前仍要核查。权限/输入请求拒绝后 PAUSE，不默认接受或猜测用户回答。

## 6. 提交与审阅

保留 v3.1 BRANCH/COMMIT 有限动作：精确路径、默认分支禁写、不能夹带其它改动、不能顺手改 runner/CI/凭据/AGENTS。
新增临时产物路径检查；业务 COMMIT 拒绝 BOOTSTRAP_RESULT.md 等文件。所有业务改动绑定真实 HEAD/base 的新独立 Review。
只读审阅不能执行的测试必须依赖可核验的既有日志或标明证据不足，不能关闭 sandbox 来“审阅通过”。
本 runner 不含 MERGE/DEPLOY。发布 Issue/PR/推送只在现有授权下作为边界明确动作，不由收到完成事件自动授权。

## 7. 日志位置

```text
.ai-flow/local.json                              # 不提交
.ai-flow/runtime/probes/<probe>/doctor.json      # 不提交
.ai-flow/runtime/runs/<run>/state.json           # 不提交
.ai-flow/runtime/runs/<run>/protocol/codex/      # wire + stderr
.ai-flow/runtime/runs/<run>/protocol/pi/         # wire + stderr + sessions
.ai-flow/runtime/runs/<run>/001-controller/      # prompt / result / progress / receipt
.ai-flow/runtime/runs/<run>/SUMMARY.md
```

wire 日志可能包含模型文本、命令输出与主机路径，只有本地审计用途。公开摘要先检查敏感内容，不能整份上传 PR。
协议依据见 SOURCES.md [N1]–[N3]。

## File Toolbox 适配

所有 Python 入口通过 `uv run --frozen python` 执行。BRANCH 使用 `codex/` 前缀。工作区变化比较 Git HEAD、分支、status、二进制 diff 和未跟踪内容；策略变化直接比较本地内容快照，不计算额外 SHA-256。快照留在 ignored runtime，旧包运行记录不复用。COMMIT 精确核对暂存区与工作区的全部变化。项目质量命令以 `.ci/project.json` 为准。
