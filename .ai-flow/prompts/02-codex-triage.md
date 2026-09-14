# v4.0 Codex：短调查与技术分工

先读当前 Issue 的 **AI Flow Routing**、交接和真实失败/代码证据。确认最小复现、真实数据流、不变量和最有判别力的验证，不为展示进度先改一堆代码。

分别校准 L 与 R，核对网页版给出的 `Recommended implementer` / `Execution mode`。若改变规划建议，把新的 L/R、建议实施者和理由写回 Issue/PR。不能因为已经进入 Codex 就默认所有任务都由 Codex 实现。

路线明确后：若明确施工应由 GLM 承担，写 GLM Handoff、输出施工/收尾/阻碍三条短句并停止；若下一步仍应由当前 Codex 完成，则直接按 03 连续实施，不 self-handoff，也不要求用户再派一次。

涉及产品目标变化或不可逆授权则 HUMAN_REQUIRED；仅缺环境/权限则 BLOCKED，列能继续的安全调查与恢复动作。任何“交给 GLM”均指材料已准备、用户尚需手工启动，绝不实际调用 GLM。
