# AGENTS.md

本文件适用于仓库根目录及其全部子目录；更深层的 `AGENTS.md` 只能补充更严格、范围更窄的规则。

<!-- BEGIN UNIFIED SIX-REPOSITORY PRACTICES -->
## 统一工程与交付规则

### 语言、事实来源与协作

- 与用户、Issue、PR、review 和交付说明使用简体中文；代码标识符、协议字段、CLI 参数和行业缩写保持原文。代码注释遵循所在模块既有语言，不为翻译而改名。
- 事实优先级依次为：可执行配置/锁文件与代码、`.ci/project.json`、项目脚本、测试、当前文档。文档与实现冲突时先核实实现并在同一 PR 修正文档，不凭记忆扩写。
- 大改先说明影响的模块、接口、风险与验证；优先把复杂实现藏在小而稳定的接口后。`scripts/automation.py` 是自动化稳定接口，项目差异通过声明式配置、项目适配器和必要的 workflow 编排表达。
- 评审 rubric、验收清单和风险分级只保留能区分结果、支撑决策的条目；不要机械枚举所有组合，也不要把普通工程工作包装成安全攻防论文。

### 修改范围与安全

- 开始工作前读取 `git status -sb`、远端、当前分支、最近的仓库指令和实际 hooks。保留用户未完成工作；禁止擅自 stash、reset、checkout 覆盖、递归删除或绕过 hook。
- 在最新远端 `main` 的独立 `codex/<slug>` 分支/worktree 中工作。只暂存本任务文件，不提交密钥、凭据、本地路径、缓存、数据库、模型、构建包或编辑器状态。
- 生成文件、版本派生文件和 lock 必须由仓库脚本更新；不得手改生成物后跳过生成/一致性检查。会删除或重建目录的脚本只可作用于仓库声明的固定输出目录。
- 不通过降低覆盖率、跳过与变更相关的 E2E、吞掉错误、添加无依据重试、删除有明确边界契约的校验或禁用安全检查来使 CI 变绿。修复针对根因；存在稳定且合适的测试 seam 时补充能在旧实现上失败的回归契约，不为勾选条目制造脆弱测试。
- Python 环境统一由 `uv` 管理：使用仓库锁定配置通过 `uv sync --frozen ...`（或项目明确声明的 `uv venv`）创建/更新仓库内 `.venv`，所有 Python 入口通过 `uv run python ...` 或仓库封装脚本调用。禁止直接用系统 `python`/`pip` 安装项目依赖，禁止把依赖散装到全局或用户 `site-packages`。
- 依赖解析和工具链版本服从项目声明的配置、lock 与生成脚本。可复用本机可信下载缓存及已配置镜像，但不得为适配本机网络擅自修改仓库级 registry/index、lock 中的来源、Git remote 或 CI 配置。
- 下载或远端访问失败时先做最小诊断，不盲目重试，也不自行使用未经授权的第三方代理。确需改变仓库依赖来源时，作为独立变更说明其对 CI、lock 与供应链一致性的影响。
- 普通依赖及 lock 始终以仓库声明为准，不因本机已有更高版本而升级。SDK 或工具链缺少仓库固定版本、但本机已有更高稳定版本时，先检查项目的 roll-forward、lock、CI 与兼容性契约：允许兼容前滚的可直接复用；要求精确版本的，不静默修改 pin，而是向用户说明安装固定版本与独立升级 SDK 两种方案。升级须使用项目声明方式走普通 PR，并运行完整质量入口。
- SHA-256、hash 或 identity 比对不是普通正确性或安全校验的默认手段，只在发布资产、外部下载、更新包、跨系统资产交接或故障取证等存在明确字节完整性契约的边界使用。新增前必须能指出权威摘要的生产者、校验消费者、失败处理及其防止的可复现故障；缺少任一项则不新增。
- 不存在上述契约时，不对本地源码、生成文件、配置、目录、临时文件、缓存、日志、数据库或同一流水线内已受 Git/构建步骤约束的数据，为“多一层保险”重复计算 SHA-256，也不把手工 hash 当作默认 review 或交付证据。优先使用语义校验、解析/契约测试、Git tree/diff、精确资产清单或既有单一 checksum；已有多层 hash/identity 若没有独立消费者或边界，应简化而非继续叠加。

### CI/CD 架构保护

- 六仓默认只保留 `.github/workflows/ci.yml` 与 `.github/workflows/cd.yml`；公共自动化深模块文件清单为 `scripts/automation.py`、`scripts/automation_core.py` 及 `scripts/automation_{common,ci,candidate,prepare,publish}.py`，相关变更必须六仓协调并保持每个对应文件提交后的 Git blob/字节一致。workflow 共享稳定 CLI、`required` 门禁、候选交接和发布状态机等不变量，但不要求字节一致；VibeTable 可按其多栈构建和 E2E 瓶颈调整 job、lane、缓存及产物交接。
- 项目专属命令、测试集合和构建语义优先写在 `.ci/project.json` 及项目脚本中。workflow 可表达项目所需的 runner、job 拓扑、缓存和产物交接，但不重复实现项目命令；需要新依赖或平台步骤时优先扩展 bootstrap/adapter。
- CI 在 PR 和 `main` push 上完成 `.ci/project.json` 声明的 `bootstrap`、`quality`、`e2e`、`release_build` 与 `release_smoke`，按项目真实依赖串并行编排并 fail closed。PR 必须执行适用的完整 release build/smoke；只有 `main` push 会整理并上传正式候选。只有同一 PR 的陈旧运行可取消，`main` 运行不可互相取消。
- PR CI 是合并门禁；squash merge 后的 `main` CI 验证合并结果，并额外上传固定名 `release-candidate`。CD 的 publish job 只下载触发它的那次 `main` CI、同一 source SHA 的候选，不重新运行完整 CI，也禁止在 CD 重建、替换或人工上传资产。
- 手动运行 CD 只允许选择 `patch`/`minor`/`major`，作用是创建或刷新唯一 `automation/release` changelog/version PR。该 PR 合并后依次运行 `main` CI、provenance/SBOM attestation、正式非草稿 Release 和镜像同步；不再设置人工发布确认。

### 版本、changelog 与 Release 不变量

- 版本更新只能走 `uv run python scripts/automation.py release prepare --bump <part>` 及 `.ci/project.json` 声明的生成命令；不得直接编辑多个版本源、手打正式 tag 或手建 Release。
- 目标版本基线取当前版本、稳定 `v*` tag 与已发布正式 Release 的最大值；draft/prerelease 不参与。只有 tag、没有正式 Release 的稳定版本也会推进下一目标，不能复用或回退。
- `refs/tags/v*` 不可更新/删除且无 bypass；main 禁止 force-push/删除。发布候选必须绑定 source SHA、版本、项目 identity、精确资产集合、SHA-256 与 SPDX 2.3 SBOM。已有正式 Release 只允许在 tag/source/identity 一致时补齐或修复资产，否则 fail closed。
- Changelog 由 squash 后的 Conventional Commit 生成。`feat`、`fix`、`perf`、`deps`、`revert` 和 breaking change 默认可见；包括 `security`、`build` 在内的其他类型默认隐藏。不要为进入 changelog 伪造 type；确需覆盖时用 `Changelog: include` 或 `Changelog: skip`。
- 正式 Release 完成后，以 CD 成功状态、source SHA、Release 资产清单、checksums 和 attestations 作为交付证据；流水线已完成逐资产校验时，不在本地重复下载全部资产。仅在用户明确要求或排查具体发布故障时，按项目脚本抽检相关资产。

### 代码质量与验证

- 先运行最小相关 formatter/lint/type/test，再运行项目专属质量入口；修改生成器、构建、版本、组件绑定或发布逻辑时必须执行相应 contract/smoke。完整矩阵以 GitHub PR 的 `required` check 为权威。
- Python 使用仓库配置的 Ruff 和类型检查；TypeScript/Vue 使用锁定 Node 与项目脚本；C# 使用锁定 .NET SDK、warnings-as-errors 与 locked restore；Go 必须 `gofmt`/`go vet`/`go test`。不得用宽泛 `Any`、ignore、禁用规则或更新 snapshot 掩盖缺陷。
- 测试与源码相邻或进入仓库既有测试目录，命名、marker 和覆盖率遵循项目章节。修复跨进程、GUI、打包或协议问题时，选择与可复现故障、接口契约或高概率风险直接相关的成功、失败、取消、超时或产物路径；不机械要求每次改动覆盖全部组合。
- 本地 hook 若已安装必须正常执行且不得 `--no-verify`；若 clone 未安装 hook，运行其配置对应命令并在 PR 说明。格式化若会改变公共镜像文件，必须按镜像豁免规则处理。

### Commit、PR 与合并

- Commit 使用 `<type>(<scope>): <简体中文动词短语>`，例如 `fix(ci): 修复候选产物绑定`、`docs(agents): 补充仓库治理规则`。一个 commit 只表达一个完整意图。
- PR 标题采用中文 Conventional Commit；正文至少包含背景与根因、变更内容、影响与风险、精确验证命令及结果。UI 可见改动附截图；未执行项说明原因，pending 不得写成 passed。
- 只允许 squash merge。合并前必须通过严格同步 `main` 的 `required` check，处理所有 review conversation，不使用 admin/bypass 绕过保护。普通 PR 合并后确认 `main` CI 与 CD 哨兵成功且未意外发布；`automation/release` PR 合并后则必须确认 CD 完成正式发布。
- 工具托管的 worktree 使用工具固定位置；手工创建的 worktree 统一放在各仓库共同父目录下的 `.worktrees/<repo>/<slug>`，按仓隔离，不放进仓库工作树、`build/` 或系统临时目录。worktree 只在工作树干净且 PR 已确认 `MERGED` 后移除。由于只允许 squash merge，必须验证 PR 的 `mergeCommit` 可从最新远端 `main` 到达，并用 `git diff --quiet <branch-head> <mergeCommit>` 确认 tree 等价；不能要求分支 HEAD 本身是 `main` 祖先。先使用 `git worktree remove` 移除 worktree，再执行 `git worktree prune` 和安全删除分支；验证失败时保留现场，不递归删除目录或 `.git`。

### Secret 与远端治理

- `RELEASE_TOKEN` 仅用于 release PR prepare；publish 使用 GitHub OIDC/最小权限。镜像凭据只从既有 Secret 注入。不得打印、复制、重命名或探测 Secret 值；Secret 名或权限变化必须六仓协调。
- `release` Environment 无 reviewer；仓库只允许 squash、自动删除已合并分支、线性历史、严格 `required`、管理员同样受保护。不得在代码变更中私自放宽 branch/ruleset/environment。

<!-- END UNIFIED SIX-REPOSITORY PRACTICES -->

## 项目架构与独特约束

- 本仓是 Python CLI + PySide6 GUI 文件工具。批量重命名、PDF 等核心功能可跨平台；Word/Excel/PPT 转换及替换依赖 Windows Office/WPS COM，禁止把这部分宣称为跨平台或在非 Windows CI 伪造通过。
- 权威自动化入口是 `scripts/automation.py`，由它读取 `.ci/project.json`：`uv sync --frozen --all-extras`，release contract、Ruff、mypy、UI 生成校验，两套 pytest 覆盖率门禁（不低于 90%）、测试数量基线、`uv build`，以及真实 Nuitka release build/smoke。
- `file_toolbox/gui/generated/` 由 `.ui` 经 `scripts/regen_ui.py` 生成，禁止手改或用全仓格式化破坏。UI 变更同时修改源 `.ui`、重新生成并执行 `--check`。
- 唯一版本源是 `pyproject.toml [project].version`；`uv.lock` 的 editable package 版本和运行时 metadata 是派生值。不要新增 `version.txt` 或手打 tag。
- Velopack 发布契约固定为 `FileToolbox-{version}-full.nupkg`、`FileToolbox-Portable.zip`、`releases.win.json`、`checksums.txt`、`SBOM.spdx.json`、`build-identity.json`；checksums/SBOM/identity 必须绑定同一精确资产集合。发行形态只有便携包（vpk `--noInst`，不生成 Setup 安装器）；应用内更新只使用 Velopack，便携运行态同样由 Velopack 自更新，不得重新引入安装器或自研下载链。
- 文件修改命令默认 dry-run，只有明确 `--yes` 才执行；不得为了简化调用移除此保险。应用更新由 Velopack 管理安装事务，项目不再维护 `.file_toolbox/` 更新备份、历史或自研 replacer 回滚链。
- Ruff 使用双引号/100 列/Python 3.11，mypy strict 且以 win32 为目标。仓库提供 pre-commit 配置（Ruff fix/format 与 mypy）；不在文档中假定某个 clone 是否安装 hook，按工作开始时的实际检查执行，未安装时运行等价命令。

## 六仓关系

- 本仓与 VibeOCR Protocol/Backend/Classic/Next、VibeTable 没有源码或运行时依赖，也不参与其组件版本链。
- 六仓关系仅是共享相同的 CI/CD 深模块、版本 PR 状态机、GitHub 治理和镜像策略；本仓项目命令继续留在自己的 adapter。
- 任何公共 core 修改必须与其余五仓同步；workflow 可按项目瓶颈差异化，File Toolbox 的 GUI/COM/覆盖率/更新器规则不得反向塞入其他仓库 YAML。
