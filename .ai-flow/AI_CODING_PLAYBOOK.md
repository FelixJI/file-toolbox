# AI Coding Vibe Flow v4.0 — 执行规范

版本：4.0.0。发布日期：2026-09-14。模式：manual-handoff。默认档位：balanced。

## 1. 分工与控制权

用户控制 **Codex ↔ GLM** 的跨工具启动、外部等待恢复和最终合并。Codex 负责技术分工、真实仓库校准、复杂实施、GLM 结果接收、整改路由和工程验收；GLM 只实施 Codex 已明确的当前范围，不自主改变 Issue 目标、领取下一任务或决定最终验收。

网页版规划前读真实仓库和已有 Issues/PR，写入可验收的任务合同。规划时就必须给每个 Task 标出 `Difficulty`、`Risk`、`Recommended implementer` 和 `Execution mode`；Goal 必须汇总成可扫读的路由表。规划路由是建议，本地 Codex 启动后基于真实代码再次校准。一次规划依赖队列，仅细化近期工作；不另建长期 plan.md。

禁止 Codex 与 GLM 自动互调、回调、轮询或后台续办。**正式独立审阅是唯一例外：Codex 在 REVIEW_READY 时自动启动新的只读 reviewer 子代理。** 该子代理只负责审阅，不改实现、不派工、不合并；审阅结果自动返回 Codex 主执行上下文，不需要用户开新 Codex 窗口。

**最高优先级连续执行原则：同主体连续执行，只有跨工具/外部控制边界才人工交接。** 每个 checkpoint 后先判断下一步：仍由当前 Codex 或当前 GLM 在已授权范围内完成，就继续，不建 self-handoff、不让用户重新贴提示词。只有 Codex ↔ GLM、真实外部等待、用户决策/授权、人工合并或超出当前授权时才停。reviewer 子代理是 Codex 内部自动步骤，不属于人工交接边界。

## 2. 人工跨工具闭环

1. 网页版复用/创建主 Issue；多语义 PR 才建 Goal + Task Issues。每个 Task 写清 L/R、建议实施者与执行模式；Goal 汇总这些字段。规划完成后给用户一条 Codex 入口并停止。
2. 用户启动 Codex。Codex 读取 Issue、依赖、实际分支、开放 PR 与当前代码，复核 L/R 和建议实施者：若规划建议仍合理就按其推进；若需要改路由，先把理由写回 Issue/PR。
3. 下一步仍由 Codex 承担时，Codex连续调查→设计→实现→测试→修复→补证据，不 self-handoff。
4. 只有明确施工应转 GLM 时，Codex 写 Handoff 评论并输出**施工 / 收尾汇报 / 阻碍汇报**三条短句，然后停止。用户手工启动 GLM。
5. GLM 在该 Handoff 范围内连续实现、自测和修复；范围完成、受阻、越界或必须回 Codex 判断时写结果评论，主动给返回 Codex 的一句话并停止。
6. 用户把短句交回 Codex。Codex核查结果并继续自己负责的工作；若仍需新的 GLM 施工，再创建新的 Handoff。
7. 当实现和当前可得验证达到 REVIEW_READY，Codex**自动启动新的 reviewer 子代理**。子代理独立读取 Issue/PR/最新 base/head/diff/代码/测试，给出 PASS、CHANGES_REQUIRED 或 INSUFFICIENT_EVIDENCE，并写回 PR（无权限则把完整审阅结果返回主 Codex，由主 Codex原样发布并注明来源）。
8. CHANGES_REQUIRED：Codex 主执行自动接回。复杂/未知整改由 Codex 连续处理；明确施工才再次人工交 GLM。任何新提交完成验证后，再自动启动新的 reviewer 子代理增量复核。
9. PASS 且适用验证/CI/平台门禁满足后，Codex停在 MERGE_READY。用户决定是否合并。合并后如需继续目标队列，由用户再次启动相应阶段。

人工控制的是跨工具和最终决策，不是每个内部步骤。不要为了“协作感”强迫 GLM 参与，也不要因为 Codex 已经打开就吞掉原本明显适合 GLM 的 L1/L2 施工。

## 3. 难度、风险与建议实施者

规划者和 Codex都必须把 L 与 R 分开判断，各给一句证据理由。

| 难度 | 判断 | balanced 默认建议实施者 | 默认执行模式 |
|---|---|---|---|
| L1 | 局部机械修改、无复杂判断 | GLM | GLM |
| L2 | 方案清楚、单模块、可直接验证 | GLM | GLM |
| L3 | 跨模块、状态/数据流或根因待定 | Codex 或 Codex-first → GLM | Codex 先判断；边界清楚的施工再交 GLM |
| L4 | 架构、复杂状态机、并发/同步 | Codex | Codex |
| L5 | 系统级、多重约束、验证困难 | Codex | Codex 分阶段解决 |

风险会修正建议实施者：即使 L1/L2，若 R3 或施工需要关键架构/安全判断，可推荐 Codex；必须写明为什么偏离默认。

| 风险 | 内容 | 门禁 |
|---|---|---|
| R0 | 无运行时行为变化的普通文档 | 自检、适用验证、reviewer 子代理、人工合并 |
| R1 | 可逆普通行为变化 | 回归/本地验证、适用 CI、reviewer 子代理、人工合并 |
| R2 | 数据模型、兼容接口、核心路径、一致性 | 增加集成、兼容/恢复证据；reviewer 子代理；人工合并 |
| R3 | 权限、安全、破坏兼容、真实数据/不可逆迁移、CI/发布信任策略 | 专项安全/迁移演练与授权，必要时目标验收；reviewer 子代理；人工合并 |

Issue 中允许的 `Recommended implementer` 只有：`Codex`、`GLM`、`Codex-first → GLM`。不要写模糊的 `worker`、`任一 Agent` 或历史工具名称。`Execution mode` 要进一步说明何时转 GLM、什么条件由 Codex保留。

保留可选 `throughput` / `save`，只有用户选择才切换：前者把更多明确工作留给 Codex，后者更积极把明确施工交 GLM；两者都不削弱审阅与验证。配额未知保持 balanced，不猜账户额度。

## 4. Issue、Goal、范围与依赖

每个 Task Issue 必须有靠前且醒目的 **AI Flow Routing** 区块：

```text
Difficulty: L? — 理由
Risk: R? — 理由
Recommended implementer: Codex / GLM / Codex-first → GLM
Execution mode: ...
Routing rationale: ...
Technical owner: Codex
Review: Codex reviewer subagent (automatic)
Merge: human-only
```

Goal Issue 必须有汇总表，至少含：`Task | L/R | Recommended implementer | Execution mode | Depends on | State`。不能只在子 Issue 尾部埋 L/R，也不能在 Goal 里只列顺序和依赖。

Issue 还记录 Goal、Scope、Out of Scope、编号 AC、依赖、当前基线、验证策略及必要回滚/授权。验收标准必须可观察，包含重要失败路径；“CI 全绿”不是功能标准。

一个 PR = 一个可独立验收的行为。中型任务可在同一 PR 内分 2–5 个 checkpoint，不强制凑数，也不按文件/行数机械拆 PR。checkpoint 不是另一个 Issue、报告提交或人工转交点。

优先复用相关 Issues 和未合并 PR，记录冲突和当前拥有者。默认依赖 PR 合并后才能施工；不因为“代码已写完”就假设依赖满足。用户明确授权 stacked PR 时记录真实 base、后续 retarget 和集成复测；否则 WAITING_DEPENDENCY。

改变产品语义、公共契约或验收目标必须回到 Codex并更新合同；需要用户意图决策时 HUMAN_REQUIRED。技术实现细节不必逐文件询问用户。

## 5. 状态与控制指针

Issue 使用以下业务阶段：

```text
PLANNED → READY → CODEX_WORKING
                → HANDOFF_READY → GLM_WORKING → GLM_DONE
                → CODEX_CHECKING → REVIEW_READY → REVIEWING
                → CHANGES_REQUIRED → FIXING → REVIEW_READY
                → MERGE_READY → MERGED → ACCEPTED（目标层可选）
```

任何阶段可以进入 BLOCKED、WAITING_CI、WAITING_DEPENDENCY、REVIEW_BLOCKED 或 HUMAN_REQUIRED。状态旁另记 `current_actor`、`next_actor`、`next_action`、`user_action_required`；**只有 Codex ↔ GLM 跨工具交接才需要 `handoff_id`**。

`HANDOFF_READY` 仅表示 Codex 已停止写入、材料可由 GLM 领取，不表示 GLM 已启动。GLM 完成只表示施工声明待 Codex 接收。`REVIEW_READY/REVIEWING` 不需要用户 Handoff：Codex自动创建 reviewer 子代理。review PASS 不等于平台批准或已合并。MERGED 依据真实远端结果。

若下一步仍是当前 Codex/GLM 且在授权范围，就状态更新后继续，不生成短句。若下一步是 reviewer 子代理，Codex直接内部调用，不停给用户。只有下一步需另一个外部工具、人或真实外部事件时才停。

## 6. 一句话与 GLM 交接包

Codex 每次**跨工具向 GLM 交接**必须输出三条短句：执行本次交接、收尾汇报、阻碍汇报。若下一步仍是 Codex，直接继续，禁止产生三句或 self-handoff。审阅没有用户短句，因为 reviewer 子代理由 Codex自动启动。

交接评论最少包含：Issue/Goal、handoff_id、Scope/Out of Scope/AC、分支与工作区、base/head SHA、dirty 文件与归属、已完成/剩余工作、真实测试/失败证据、失败轮次、下一动作、停止条件。只记录可获知事实；没有 PR/提交就明确“尚无”。

默认交接前保留一个可审查提交边界，精确暂存任务文件。允许有意交接未提交改动，但必须给完整差异清单、归属、恢复/验证方式，且用户确认旧写入者已停；不能为了干净工作树盲目提交别人的改动。

有 GitHub 权限则实际写回并拿到评论位置，失败要明确；重复发送前先读已有记录。无权限输出待发布摘要和短句，由用户搬运。网络未知时不能声称一句话已足够。

## 7. 单写入者与恢复

默认同一仓库一次只运行一位实施写入者，即便有多个 worktree；reviewer 子代理只读，不计入实施写入者。用户主动安排并行写入需要另外明确隔离方案，本包不自动并行。

Codex/GLM 接手前读 Git status、HEAD、分支和目标 diff，核对旧写入者已停。旧进程仍活动、归属不清、同一路径有用户修改时停止写入，保留现场；不得删除锁文件、杀不明进程、stash/reset/clean 或强推来“恢复”。

恢复以 Issue/PR + 实际 Git 为准，不读取旧 runner state 驱动动作。先识别已生效操作，再继续，避免重复 commit/push/建 PR。外部等待解除后由用户手工启动 Codex/GLM；不轮询 CI、另一工具或合并状态。

## 8. 验证与提交

读取项目真实脚本和测试，不编造命令；缺少已知命令时先调查，`validation.commands=[]` 表示尚未填写，不代表无需验证。把 command、cwd、结果/退出码、关联 SHA、日志或 CI 链接及 AC 映射写清楚。通过、失败、未跑、不适用、基础设施故障分开。

修 bug 尽可能补回归；UI 行为要有适用交互证据，数据/兼容行为不能仅用 mock 代替实际集成证明。基线已有失败单独记录，不能据此忽略新增失败。禁止删测试、削弱断言、静默 skip 或改门禁使自己通过。

阶段交付后再 push；精确暂存，不 `git add .` / `-A`。PR 可先为 Draft，GLM 不凭自己完成就宣布工程通过。验证不足先列缺口，Codex 接手安排补证据；当前工作真正被 CI 阻塞才 WAITING_CI，不循环忙等；还有安全工作可做就先做完。

合并前必须核对最新 head 和适用基线，不能用旧 SHA 结果。base 更新、merge queue 或集成提交改变结果时，需要相应集成证据。没有权限读结果就是缺证据。

## 9. reviewer 子代理与整改

所有变更都需要正式 reviewer 子代理审阅。达到 REVIEW_READY 后，Codex主执行自动启动**新的审阅子代理**，并给它当前 Issue/PR 定位信息；不能把自己的结论、预期答案或“应该 PASS”作为审阅前提。

reviewer 子代理必须自行重新读取：适用规则、Issue 合同、最新 PR base/head、完整相关 diff、关联未改代码、实际测试/CI。首审检查完整相关范围；整改后检查上一 reviewed SHA→新 SHA 的增量、原 findings 与关联路径；base 改变补查集成影响。

reviewer 只读：不修改实现、不提交修复、不替 Codex重写任务、不调用 GLM、不合并。允许执行安全的只读检查；会污染工作区的测试应使用安全隔离，否则标缺证据。

每条 finding 有 ID、定位/复现、影响、严重性与阻塞性。P0/P1、AC 违反、关键验证缺失、可复现正确性/安全/兼容 P2 阻塞；P3 通常建议。结论仅 PASS / CHANGES_REQUIRED / INSUFFICIENT_EVIDENCE。

有 GitHub 写权限时 reviewer 子代理直接写 PR 审阅评论；没有权限时返回完整结构化结果给 Codex主执行，由主执行**原样发布并标注“reviewer 子代理结果”**，不能擅自删阻塞 finding。若当前 Codex环境不能创建新的只读 reviewer 子代理，标 `REVIEW_BLOCKED` 并告诉用户能力缺失；不退化为主 Agent 自审，也不要求用户另开窗口作为默认流程。

CHANGES_REQUIRED 后 Codex 主执行继续：根因/架构/高不确定性整改自己处理；明确施工才人工转 GLM。每个新提交更新验证，并启动新的 reviewer 子代理增量复核。PASS 后 Codex仍需核对最新 SHA、CI/门禁，才能 MERGE_READY。

## 10. 有限试错与阻碍

一轮失败是提出假设、实施修复并通过验证确认同一根因仍未解决。正常初次红测试、新发现问题不机械计入失败；不能改名字重置轮数。

GLM 同根因最多两轮有依据失败后交 Codex；根因未知或高风险边界变化可立即交回。Codex先重建最小复现，再最多两轮无进展则 HUMAN_REQUIRED，给基于证据的可选路径。CI 基础设施故障最多一次合理重试；仍未好转 BLOCKED，不伪报 PASS。

缺权限、环境依赖、配额/服务故障与产品决策区分；没有任何故障授权更换付费方案、账号、工具或突破沙箱。

## 11. 合并、目标验收与权限

v4.0 默认始终人工合并；不提供自动合并开关。即使全绿和 reviewer PASS 也只 MERGE_READY。用户后续明确要求当前 Agent 合并某个 PR 时属于一次具体授权，仍须核对实时证据，不能解释为以后自动合并。

保留仓库既有分支保护、required checks 和审批身份要求，不能把 AI review 当平台批准。业务 PR 不可自改门禁以放行自己。代码合并不授权生产部署、发布或真实数据操作。

跨 PR 目标可在集成后回网页版核对 ACCEPTED / NOT_ACCEPTED / EVIDENCE_MISSING；高风险产品语义必要时合并前核对。发现目标缺口如实记录必要后续 Issue，不把已合并改写成未合并。

## 12. 本机产物与 v3.2 迁移

共享规则在 `.ai-flow/`；临时诊断在 ignored `.ai-flow/runtime/`。日常状态写 Issue/PR，不增加通信 JSON、安装报告或为进度新建 PR。`local.json` 只可能是被忽略的旧版遗留，v4.0 不读取它。

迁移删除旧自动入口、跨工具协议客户端、控制/完成提示词与通信 schemas。旧任务不能自动 resume；先确认旧 Agent 停止，保留代码现场，再人工接管。历史文件名可能保留在 migration manifest 中用于识别和删除旧版文件，但**当前 Flow 的施工角色只称 GLM**。

本包不自动扫描外部服务/计划任务，也不卸载用户工具。需要停止的是确认属于旧 AI Flow 的具体任务，不能按进程名笼统杀掉所有 Codex、node 或 Python。
