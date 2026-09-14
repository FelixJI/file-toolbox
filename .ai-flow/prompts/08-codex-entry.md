# v4.0 Codex：日常入口

读取 `.ai-flow/AGENTS.md`、project.json、当前 Issue/Goal、AI Flow Routing、适用业务规则、真实 Git/PR/CI 状态。先确认无其他实施写入者；查重、核对依赖与范围，再校准 L/R、Recommended implementer 和 Execution mode。Goal 队列只选择用户当前授权的就绪 Task，不自动把整队列跑完。

**先尊重规划分工，再用真实代码校准。** L1/L2 明确施工默认应交 GLM；L3 先由 Codex 判断，可切出的明确施工再交 GLM；L4/L5 Codex 主做。若改变 Issue 中建议实施者，写回证据与理由。不能因已经启动 Codex 就把所有 Task 留给自己。

Codex 自己负责的调查→实现→测试→修复→补证据连续完成；next_actor 仍是当前 Codex 时不停、不 self-handoff。只有确需转 GLM 时，按模板写 Handoff 评论并输出已填真实编号的施工/收尾/阻碍三句，明确“GLM 尚未启动，等待用户手工启动”，然后停止。

实现/验证达到 REVIEW_READY 后，**自动启动新的只读 reviewer 子代理**，不要求用户另开窗口。reviewer 结果自动回到当前 Codex：CHANGES_REQUIRED 就继续整改或把明确施工人工交 GLM；PASS 后核对最新 SHA/CI/门禁；INSUFFICIENT_EVIDENCE 则在当前授权内补证据，真正被外部条件阻塞才停。

不自动调用 GLM、不后台轮询外部进度。达到门禁只 MERGE_READY，不合并。
