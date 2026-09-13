# pi + GLM：按review精确整改

读取当前PR最新head SHA、Issue合同、独立review和未解决finding。确认当前分支未被另一Agent改动，基于真实最新代码修复，不重做整个任务。

逐条判断finding，成立则最小必要修复并补相应回归证据；P0/P1和阻塞P2先处理，非阻塞P2/P3有理由移follow-up。反驳finding必须给可复现反证并交独立reviewer确认，作者不能自行抹去blocker。

只修review要求，不借机重构。普通实现自行决定；根因/架构/数据边界超出明确施工能力则交Codex。相同根因最多2轮失败后止损。

重新执行适用验证，更新Resolved/Unresolved/Disputed findings、测试、当前head/base SHA，状态回REVIEW。新提交使旧审阅过期，必须请求独立增量复核，不能拿旧PASS自行合并。

调用reviewer不可用时输出HANDOFF_REQUIRED，附准确下一动作；不假装自动完成复核。风险/验收不能因为修复赶进度而降低。

## v3 runner 管理模式（优先于上文中的人工交接表述）

如果环境变量 `AI_FLOW_CHILD=1`，你是外层 runner 的一次工人调用。只做本次 instructions 指定的一个任务，不领取下一任务、不启动 pi/Codex、不执行 flow.py、不调用旧桌面会话。不自行轮询 CI 或其他 Agent。

完成实施和适用本地验证后，把目标变更安全提交到任务分支；禁止在默认分支提交。只暂存经审查的任务文件，不提交 runtime/认证/日志。GitHub 有权限则可更新 Issue、推送任务分支和建立 Draft PR；无网络/权限如实记录，不更改沙箱或登录。任何 merge、发布、真实数据操作均不属于此调用。

保留真实 base/head、测试命令/exit code、AC证据、失败根因与次数、已排除路线。用最终报告交回控制权；外层收到进程退出才调用 Codex 续办/独立审阅。上文所说“交给/请求”在此模式均指写报告，不是由你启动另一个 Agent。

### 外层有限 Git 协议
若当前为 runner 子任务，优先由控制器事先 BRANCH。尤其 Codex 实现者不要反复尝试被保护的 .git；工作文件写入和测试完成后，报告精确改动路径，交外层 COMMIT。不要为提交请求绕过沙箱、递归委派 pi 或新建 Agent。pi 可在既定权限下执行明确 Git 操作，但不得使用默认分支、夹带改动或自动合并。
