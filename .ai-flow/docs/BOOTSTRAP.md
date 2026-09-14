# AI Flow v4.0 接入与 v3.2 迁移

执行者：本地 Codex；本次接入不调用 zcode、pi 或其他 Codex 会话。用户希望今后自行控制两侧进度，不需要安装任何互调替代服务。

## 1. 先停止旧链路，保留真实工作

读取现有 AGENTS/override、`.ai-flow/`、Git status、未完工 Issue/PR 和本次迁移范围。不要盲拷整个包，不 hard-code 仓库名、PR 编号或某条旧会话状态。

确认旧 runner 与其实际写入任务已结束/安全停止，核对真实进程与改动归属；需要用户在原窗口停止就明确这一操作后暂停。安装器不会杀进程，也不会删除旧锁“解锁”。旧版的 OS 协作锁只用来防止安装时碰上仍占锁的旧 runner，不能发现全部外部 Agent 或孤儿进程。

不停止无关 Codex/node/Python，不改全局登录/模型配置。若已有本机自启/计划任务/自定义桥接，仅检查并停用**确认属于当前旧 AI Flow 且获授权**的条目，不笼统删除其他业务自动化。用户仍开着的实现窗口要明确停止写入。

保留用户未提交内容。优先使用已有合适接入分支/独立干净 worktree，不默认 stash/reset/clean；旧任务保留分支、diff 和必要证据，之后按原 Issue 人工续办，绝不重放旧 run。

## 2. 预览与应用

包解压到目标仓库外，需 Python 3.10+ 与 Git；只用标准库，不发模型请求。

```text
uv run --frozen python install.py --repo "<仓库根目录>" --upgrade
uv run --frozen python install.py --repo "<仓库根目录>" --upgrade --apply --confirm-agents-stopped
```

在分发包目录执行时，为 `uv run` 添加 `--project "<仓库根目录>"`，使用目标仓库的锁定环境；不要在分发包内另建依赖环境。全新安装省略 `--upgrade`。脚本默认 dry-run；`--confirm-agents-stopped` 只确认你已完成上一节检查，不会自动替你检查/停止所有进程。

已知原版文件按哈希识别后备份并替换/删除（UTF-8 BOM / CRLF 的纯换行差异可归一化识别，原始字节仍备份）；支持识别输入包 v3.2 以及其携带的 v2/v3.1 哈希。未知定制文件不直接覆盖/删除，生成 ignored 升级候选并报告冲突。**退出码 2 / unresolved 不等于升级完成。** 脚本可能已经更新不冲突文件，必须继续完成语义合并，不能因 project.json 显示 4.0.0 就算完工。

备份在 `.ai-flow/migration-backups/`；候选在 `.ai-flow/upgrade-candidates/`。它们不是待提交内容。对定制规则保留业务要求并迁移到 v4.0；对定制旧调度代码先备份并评估有效业务内容，再精确退役旧自动入口。不得把完整旧互调说明复制回有效规则导致两套流程并存。

脚本不会自动提交、修改 index、推送、建立 PR、配置 hooks 或改远端；产物精确取消跟踪是下一节显式动作。

## 3. 需要删除的活动旧入口

具体路径清单在分发包 `migration/retired-paths.json`。重点：

- `.ai-flow/scripts/flow.py`、`native_rpc.py`。
- event-controller / completion-intake、旧 batch-run / resume 和旧 worker 入口；改用 v4.0 人工入口。
- 旧 decision/review 通信 schemas、STATUS/REVIEW JSON 示例和 local.example.json。
- RUNNER、AUTOMATION_BOUNDARY、过时 SOURCES 文档及旧版 GitHub Issue 模板。

规则、文档、project.json 和根 AGENTS 入口必须一致；根标记更新为 `AI-FLOW-V4`。自定义 AGENTS/override、MCP 配置、项目脚本或外部启动项中若还有**用于编排本流程**的互调，查清后精确停用。不能把业务中合法使用 RPC/API 的代码误删。

`local.json` 和 runtime 只作历史材料，v4.0 不读取、不迁回共享配置，不保留 ready/enabled、CLI 执行路径或后台恢复条件。必要旧诊断可原位保持 ignored；无需为迁移清空日志或认证。

共享配置仅保留仓库、默认分支、profile、有效验证命令、风险路径等长期政策；自动合并与互调强制关闭。未知自定义字段脚本保留并报告需要核查：有业务意义的保留，有旧执行意义的删除/改写；不能只根据字段名猜。

## 4. 处理本机报告与 Git 守卫

以下 `hygiene.py` 命令在**目标仓库根目录**执行；安装器和分发包测试仍在解压包目录执行。

```text
uv run --frozen python .ai-flow/scripts/hygiene.py --tracked
uv run --frozen python .ai-flow/scripts/hygiene.py --migrate
uv run --frozen python .ai-flow/scripts/hygiene.py --migrate --apply
```

只有查到已跟踪本机产物才执行精确迁移；会备份当前内容并取消跟踪，拒绝不安全的 symlink/无法安全移除场景，不处理其他业务文档。已提交历史中的报告不会被这一步抹除；不要自动改写公共历史或 force-push。

保留既有 hooks。可选 `--install-hooks`，遇现有 hook 管理器不覆盖；接入现有管理器需保留其检查和完整 pre-push stdin。v3.2 纯产物守卫可继续使用或单独核验升级，不是模型调用服务。

报告不进入 Git、PR 或 CI；必要简短接入结果发当前对话/已有接入 Issue，必要本地日志放 `.ai-flow/runtime/`。真正可复用的规则、脚本或测试配置变更正常验证，不能为了省 CI 跳过安全检查。

## 5. 验证与交付

分发包目录运行离线测试：

```text
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python install.py --repo "<仓库根目录>" --check
```

`--check` 检查文件/配置/入口等静态结构，不证明自定义规则语义正确或外部旧进程已停。接入 Codex 还须逐项确认候选已合并、退休路径已移出活动区、全局/项目旧桥接无残留、真实验证命令已核实且现有安全要求保留。

不跑原生协议探针、不安装 App Server/RPC 服务、不索取新凭据。基于当前真实 Issue 做一次**只读提示词演练**：Codex 能给实际填号的施工/收尾/阻碍短句，施工规则能给返回 Codex 的短句，独立审阅入口明确由用户新开会话。演练不能假称实际施工或审阅已发生；双工具实测由用户按本工作流手动启动，不由安装 Codex 代为调用。

核对完整 diff、适用项目测试、提交守卫；只将本次持久化迁移文件加入一个合理变更，不为安装报告另开 PR。独立正式审阅仍由用户手工开会话。本次自动安装验证不替代业务 PR 审阅或真实平台链路测试。

最终告诉用户：实际版本/模式、已验证与未验证、已保留/退役内容、尚需用户的一次操作（若有），以及后续一句话入口。任何未验证的旧进程停止、权限、CI、Windows 行为都不能写成已通过。
