# Issue 阶段更新（评论模板）

时间（含时区）：

Issue / 当前有效 GLM handoff_id 与评论（没有写 none）：

status:

current_actor：web-planner / codex-main / glm / codex-review-subagent / human / external

分支 / base SHA / head SHA / PR：

本轮已做与证据：

尚未做 / 阻碍：

next_actor:

next_action:

user_action_required:

当前实施写入是否已停止：

控制判断：
- `next_actor` 仍是当前 codex-main 或 glm 且在授权范围 → 连续执行，不停止。
- `next_actor = codex-review-subagent` → Codex 内部自动启动新的只读 reviewer，不生成 Handoff、不要求用户操作。
- codex-main ↔ glm → 写 GLM Handoff，停止，等待用户手工启动下一侧。
- human / external → 写决策或恢复条件后停止。

这里只记录任务事实，不是消息总线、进程状态或自动派工协议。
