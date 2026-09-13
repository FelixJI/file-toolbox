# AI Flow v3.1 接入验收记录

日期：2026-09-13。当前结论：**PARTIAL**。升级分支为 `codex/ai-flow-v31-bootstrap`，默认 `balanced` / `event-driven`，正式配置保持 `runner.enabled=false`，不自动合并。

## 范围与本地授权

按用户本次 BOOTSTRAP 请求，使用现有登录启动本地 pi/Codex、运行测试，并在专用演练分支使用有限 BRANCH/COMMIT。授权不包含新计费通道、新凭据、全局信任、安全策略变更、真实数据、合并或部署。

从远端 main `79094f4c8887059054eda38bcadaa16d12ed4324` 建立独立 worktree。原 main 工作区已有的未提交 AI Flow 修改保持原样。根 AGENTS 管理块之外的内容保留；业务代码、公共 CI/CD 模块、workflow 和依赖来源未改变。安装候选、运行日志及临时备份均被 Git 忽略。

安装包版本 3.1.0。本仓适配：BRANCH 使用 `codex/`；通过 Git diff、暂存区/工作区路径和直接内容快照检测变化，不重复计算本地 SHA-256；启动示例使用 `uv run --frozen python`。独立审阅发现并修复 COMMIT 夹带清单外暂存内容的问题，有真实 Git 回归测试。

## CLI 与现有通道

- Python 3.13.12，uv 0.12.5，pi 0.85.1。
- `codex.exe` 为现有桌面捆绑 CLI 0.154.0-alpha.6.2，沿用 ChatGPT 登录。npm CLI 0.104.0 不支持当前配置模型，首次真实预检失败；未安装新 CLI，未改变模型或认证。
- pi 实际事件为 `zai-coding-cn / glm-5.3`；内置 provider 端点为 `https://open.bigmodel.cn/api/coding/paas/v4`，未发现自定义 models.json。保留 `pi_args=[]`，不复制认证文件，不推断账户余额或额度。
- 修正 CLI 路径后 `doctor --live`：pi_ok=true、codex_ok=true、repo_unchanged=true。日志：`.ai-flow/runtime/probes/55864e26b7434fcb858bd2fba321c799/`。
- 默认受限工具环境不能读取现有 CLI 配置或写 Git；本次通过受审查的显式本地执行完成。没有放宽 Codex 子会话的只读/workspace-write 沙箱。

## 验证

下列命令 cwd 均为升级 worktree 根目录 `.`。业务基线为上述 main SHA；接入初版为 `0ef565bcfc567083883b02fdbda336e00e22b5fd`，COMMIT 修复为 `510fae7e995be98747a8ebb93cfd0b3064b72cc3`。

| 命令 | 实际结果 |
|---|---|
| `uv sync --frozen --all-extras` | exit 0，锁定环境建立 |
| `uv run ruff check .` / `uv run ruff format --check .` | exit 0；新增 runner 另有显式路径检查 |
| `uv run mypy` | exit 0，128 个源码文件 |
| `uv run --all-extras python scripts/check_release_contract.py` | exit 0 |
| `uv run --all-extras python scripts/regen_ui.py --check` | exit 0，无 UI 漂移 |
| `uv run pytest --cov=file_toolbox.core --cov-branch --cov-fail-under=90 -W error::ResourceWarning -W error::DeprecationWarning -q` | exit 0，1938 passed，98.24% |
| `uv run pytest --cov=file_toolbox --cov-branch --cov-fail-under=90 -W error::ResourceWarning -W error::DeprecationWarning -q` | exit 0，1941 passed，98.30% |
| `uv run --all-extras python scripts/check_test_count.py` | exit 0，1941 ≥ 1922 |
| `uv build --out-dir build/package-validation` | exit 0，sdist/wheel 构建成功 |
| `uv run --frozen pytest tests/test_ai_flow.py -q` | COMMIT 修复后 exit 0，4 passed |

两次业务测试有同一已有 runpy RuntimeWarning，未改动 warning 门禁。包外 runner 契约测试 33 项整组最终通过；首次后台 fake CLI 场景失败，单测重跑和整组复跑通过，首次原因未定位，不据此声称后台可靠性已证实。该组使用假 CLI，不代替真实模型演练。

未运行 Nuitka release build/smoke：本次未修改业务构建/发布路径，完整发布矩阵仍需接入 PR 的 required check。没有上传候选、创建 tag/Release 或重复下载发布附件。

## 真实回调与独立审阅

独立接入审阅发现 P2 COMMIT blocker，修复后另一次独立增量复核为 PASS，绑定上述 `510fae7...` / main SHA。报告保存在 `.ai-flow/runtime/integration-review.md` 与 `integration-review-followup.md`。后续记录/文档提交需另行核对，不能把旧 SHA 当作新提交批准。

专用演练 worktree 与升级分支分离，只有演练配置临时 ready/enabled：

- 只读 run `20260913T073117Z-39fbcac6`：真实 Codex 核对分支、HEAD、工作区和禁止自动合并后 FINISHED。
- 业务 run `20260913T073349Z-7d78a243`：真实控制器完成 BRANCH → PI → COMMIT → REVIEW；独立 REVIEW 为 PASS，无 findings，最终于 2026-09-13 07:42:12 UTC 收到 FINISHED 回执。
- 业务分支 `codex/ai-flow-v31-business-smoke`，base `910ef50f47543c29090fc472a169e5472fea4b4e`，head `dbfac9cf295e79724cf291f184693c1cabf237e3`。只新增两个真实 FolderCreatorService TSV 解析测试，未调用创建目录功能。
- pi pytest 为 2 passed，Ruff check/format 和 mypy 均 exit 0；文件由外层显式 COMMIT 提交，独立审阅核对原始工具事件与精确提交内容。

演练证据位于演练 worktree 的 `.ai-flow/runtime/runs/<run-id>/`。演练分支未合并，按项目规则保留现场，不强制清理。

## 剩余边界与恢复

后台测试必须在启动 Codex 回合结束后核验，当前不能预先声称存活或完成。后续读取独立后台只读 run 的 state、SUMMARY、进程完成时间；确认完成时间晚于交接回合结束，再决定是否启用正式 runner。不得在未通过时把 partial 改 ready，不复用业务演练 run 进行业务派发。

GitHub 只读核查成功：viewerPermission=ADMIN，仓库仅允许 squash，main 要求严格同步的 required check。未执行远端写操作、未推送或创建接入 PR，所以 github_write 和本次远端 CI 仍未实测；无需重新配置现有门禁。可在获得推送/PR 授权后交付 PR，不能因本地 PASS 自动合并。

能力就绪后日常入口：**按 AI Flow v3 执行 #123，balanced，推进到可交付边界。**

## 2026-09-13 后续核验：本地 runner 就绪

以上 PARTIAL 为接入提交时的历史记录。本次 #83 的 v3 兼容执行补齐了剩余本地接入证据：

- 入口任务 `01a099a1-3276-75b3-8075-4b89958a1c2b` 的接入回合于 2026-09-13 07:45:50 UTC 完成（桌面任务 completedAt=1789285550）。
- 后台 run `20260913T074541Z-7f7d4b53` 的真实控制进程于 07:46:42 UTC 成功退出，runner 于 07:46:43 UTC FINISHED，晚于入口回合结束。该证据证明这次本机跨回合存活，不保证机器重启或宿主强制终止后的恢复。
- PR #85 已真实创建并合并，最新远端 main 为 `67dcb70612874fabe9e66faf0c75656d3704b431`；GitHub 写入能力已有实际记录。历史配置中的“未推送/未建 PR”不再是当前阻塞。
- 本次专用 worktree 执行 `uv sync --frozen --all-extras` 与 `uv run --frozen python .ai-flow/scripts/flow.py doctor` 均 exit 0，pi/Codex CLI 检查均 ok。沿用上述真实模型与业务闭环证据，没有重复修改认证或 provider。

据此将 configuration_status 更新为 ready、runner.enabled 更新为 true，并刷新本地能力记录；原有自动合并关闭、禁止部署、沙箱与有限 Git 写入限制不变。此变更作为独立接入 PR 审阅，不与 #77–#82 的业务修复混合。ready 仅指本地接入条件满足，不表示此 PR 的独立审阅、CI 或业务目标已通过。
