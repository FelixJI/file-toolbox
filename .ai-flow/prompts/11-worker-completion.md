# v4.0 GLM：完工 / 收尾结果

安全结束当前修改，核对真实 Git 状态和当前 Handoff，不把未完成伪装成交付。按 WORKER_RESULT 模板写 Issue/PR：handoff_id、任务/分支/base/head、提交与 PR、工作区 clean/dirty 及归属、逐项 AC 完成/未完成、实际 command/cwd/exit code/证据、剩余事项与风险。

全部本次施工范围完成且适用自测已做才记 GLM_DONE；因用户要求收尾而仍有剩余记 HANDOFF_READY；缺关键条件记 BLOCKED。均不能自己验收、批准、启动 reviewer、合并或顺手推进下一任务。

发布成功后给确切评论位置；失败标 WRITE_ACCESS_MISSING 并输出可粘贴摘要。结尾必须主动给一条填入真实 Issue/handoff_id/评论的短句：

`按 AI Flow v4.0 接收 #<实际编号> / <实际交接标识> 的 GLM 施工结果，读取 <实际结果评论位置>、PR 和当前 SHA，核对验收与测试并完成 Codex 应承担的处理；若实现/验证就绪则自动调用 reviewer 子代理，只有再次需要 GLM、外部等待或用户决策时才给我手工提示词，不合并。`

明确本会话已停止写入、Codex 尚未启动；无法确认任务已停时不能谎称。此短句由用户复制，不是由 GLM 运行。
