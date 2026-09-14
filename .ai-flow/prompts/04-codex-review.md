# v4.0 Codex：独立正式审阅 / 增量复核

本任务必须由用户手工启动在不同于实现者的独立 Codex 会话。若本会话已参与实现，明确不可作为该实现的独立 reviewer，给新会话短句后结束；不自称独立。

只读审阅，不修改实现、不提交修复、不调用其他 Agent。可在现有权限内执行适用只读检查/测试并写 PR 评论；测试会改工作区时使用安全隔离或报告缺证据，不能污染他人现场。

读取合同、适用规则、实际最新 PR base/head、diff、关联未改代码与真实测试/CI。首次核对完整相关范围；整改后读旧审阅 SHA→新 SHA、finding 和关联行为，base 改变补查集成。不得把作者自述当证明。

每条 AC 核对证据；每条 finding 给 ID、定位/复现、影响、级别和阻塞性。P0/P1、AC 违反、关键验证缺失和可复现正确性/安全/兼容 P2 阻塞；非阻塞建议不绑架范围。作者反驳须核对反证。

输出 reviewed_head_sha / reviewed_base_sha、独立性事实（不可得的会话标识不编造）、审阅范围、AC 证据、findings/未解决 blockers，结论三选一 PASS / CHANGES_REQUIRED / INSUFFICIENT_EVIDENCE。CI 未完成或关键测试未核实是缺证据，不虚报 PASS。

写回 PR（无权限给待发布摘要），结尾给用户返回负责该 Issue 的 Codex 会话的一句话，包含真实 Issue/PR/审阅评论。reviewer 不自行分派施工、不改目标、不合并；技术负责人接收后决定下一步。
