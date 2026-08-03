# AGENTS.md

本文件适用于仓库根目录及其全部子目录；更深层的 `AGENTS.md` 只能补充更严格、范围更窄的规则。

<!-- BEGIN UNIFIED SIX-REPOSITORY PRACTICES -->
## 统一工程与交付规则

### 语言、事实来源与协作

- 与用户、Issue、PR、review 和交付说明使用简体中文；代码标识符、协议字段、CLI 参数和行业缩写保持原文。代码注释遵循所在模块既有语言，不为翻译而改名。
- 事实优先级依次为：可执行配置/锁文件与代码、`.ci/project.json`、项目脚本、测试、当前文档。文档与实现冲突时先核实实现并在同一 PR 修正文档，不凭记忆扩写。
- 大改先说明影响的模块、接口、风险与验证；优先把复杂实现藏在小而稳定的接口后。`scripts/automation.py` 是自动化稳定接口，项目差异通过声明式配置和项目适配器表达。

### 修改范围与安全

- 开始工作前读取 `git status -sb`、远端、当前分支、最近的仓库指令和实际 hooks。保留用户未完成工作；禁止擅自 stash、reset、checkout 覆盖、递归删除或绕过 hook。
- 在最新远端 `main` 的独立 `codex/<slug>` 分支/worktree 中工作。只暂存本任务文件，不提交密钥、凭据、本地路径、缓存、数据库、模型、构建包或编辑器状态。
- 生成文件、版本派生文件和 lock 必须由仓库脚本更新；不得手改生成物后跳过生成/一致性检查。会删除或重建目录的脚本只可作用于仓库声明的固定输出目录。
- 不通过降低覆盖率、放宽 hash/identity、跳过 E2E、吞掉错误、添加无依据重试或禁用安全检查来使 CI 变绿。修复必须针对根因，并补充能在旧实现上失败的回归契约。

### CI/CD 架构保护

- 六仓只保留 `.github/workflows/ci.yml` 与 `.github/workflows/cd.yml`。这两个 workflow 以及 `scripts/automation.py`、`scripts/automation_core.py` 是六仓镜像的公共深模块；禁止单仓私改、格式化或复制分叉。公共变更必须在六仓协调实施，并校验提交后的 Git blob/字节一致。
- 项目专属工具链、测试、E2E、构建、smoke 和环境准备只写在 `.ci/project.json` 及项目脚本中。需要新依赖或新平台步骤时优先扩展项目 bootstrap/adapter，不把项目判断塞回 YAML。
- CI 在 PR 和 `main` push 上按 `bootstrap → quality → e2e → release_build → release_smoke` 顺序 fail closed。PR 必须完整执行 release build/smoke；只有 `main` push 会整理并上传正式候选。只有同一 PR 的陈旧运行可取消，`main` 运行不可互相取消。
- `main` CI 额外上传固定名 `release-candidate`。CD 的 publish job 只下载触发它的那次 `main` CI、同一 source SHA 的候选；禁止在 CD 重建、替换或人工上传资产。
- 手动运行 CD 只允许选择 `patch`/`minor`/`major`，作用是创建或刷新唯一 `automation/release` changelog/version PR。该 PR 合并后依次运行 `main` CI、provenance/SBOM attestation、正式非草稿 Release 和镜像同步；不再设置人工发布确认。

### 版本、changelog 与 Release 不变量

- 版本更新只能走 `python scripts/automation.py release prepare --bump <part>` 及 `.ci/project.json` 声明的生成命令；不得直接编辑多个版本源、手打正式 tag 或手建 Release。
- 目标版本基线取当前版本、稳定 `v*` tag 与已发布正式 Release 的最大值；draft/prerelease 不参与。只有 tag、没有正式 Release 的稳定版本也会推进下一目标，不能复用或回退。
- `refs/tags/v*` 不可更新/删除且无 bypass；main 禁止 force-push/删除。发布候选必须绑定 source SHA、版本、项目 identity、精确资产集合、SHA-256 与 SPDX 2.3 SBOM。已有正式 Release 只允许在 tag/source/identity 一致时补齐或修复资产，否则 fail closed。
- Changelog 由 squash 后的 Conventional Commit 生成。`feat`、`fix`、`perf`、`deps`、`revert` 和 breaking change 默认可见；包括 `security`、`build` 在内的其他类型默认隐藏。不要为进入 changelog 伪造 type；确需覆盖时用 `Changelog: include` 或 `Changelog: skip`。

### 代码质量与验证

- 先运行最小相关 formatter/lint/type/test，再运行项目专属质量入口；修改生成器、构建、版本、组件绑定或发布逻辑时必须执行相应 contract/smoke。完整矩阵以 GitHub PR 的 `required` check 为权威。
- Python 使用仓库配置的 Ruff 和类型检查；TypeScript/Vue 使用锁定 Node 与项目脚本；C# 使用锁定 .NET SDK、warnings-as-errors 与 locked restore；Go 必须 `gofmt`/`go vet`/`go test`。不得用宽泛 `Any`、ignore、禁用规则或更新 snapshot 掩盖缺陷。
- 测试与源码相邻或进入仓库既有测试目录，命名、marker 和覆盖率遵循项目章节。修复跨进程、GUI、打包或协议问题时同时验证成功路径、失败路径、取消/超时和产物身份。
- 本地 hook 若已安装必须正常执行且不得 `--no-verify`；若 clone 未安装 hook，运行其配置对应命令并在 PR 说明。格式化若会改变公共镜像文件，必须按镜像豁免规则处理。

### Commit、PR 与合并

- Commit 使用 `<type>(<scope>): <简体中文动词短语>`，例如 `fix(ci): 修复候选产物绑定`、`docs(agents): 补充仓库治理规则`。一个 commit 只表达一个完整意图。
- PR 标题采用中文 Conventional Commit；正文至少包含背景与根因、变更内容、影响与风险、精确验证命令及结果。UI 可见改动附截图；未执行项说明原因，pending 不得写成 passed。
- 只允许 squash merge。合并前必须通过严格同步 `main` 的 `required` check，处理所有 review conversation，不使用 admin/bypass 绕过保护。普通 PR 合并后确认 `main` CI 与 CD 哨兵成功且未意外发布；`automation/release` PR 合并后则必须确认 CD 完成正式发布。
- worktree 只在工作树干净且 PR 已确认 `MERGED` 后移除。由于只允许 squash merge，必须验证 PR 的 `mergeCommit` 可从最新远端 `main` 到达，并用 `git diff --quiet <branch-head> <mergeCommit>` 确认 tree 等价；不能要求分支 HEAD 本身是 `main` 祖先。远端分支删除不等于本地提交可安全删除。

### Secret 与远端治理

- `RELEASE_TOKEN` 仅用于 release PR prepare；publish 使用 GitHub OIDC/最小权限。镜像凭据只从既有 Secret 注入。不得打印、复制、重命名或探测 Secret 值；Secret 名或权限变化必须六仓协调。
- `release` Environment 无 reviewer；仓库只允许 squash、自动删除已合并分支、线性历史、严格 `required`、管理员同样受保护。不得在代码变更中私自放宽 branch/ruleset/environment。

<!-- END UNIFIED SIX-REPOSITORY PRACTICES -->

## 项目架构与独特约束

- 本仓是 Python CLI + PySide6 GUI 文件工具。批量重命名、PDF 等核心功能可跨平台；Word/Excel/PPT 转换及替换依赖 Windows Office/WPS COM，禁止把这部分宣称为跨平台或在非 Windows CI 伪造通过。
- 权威自动化入口是 `scripts/automation.py`，由它读取 `.ci/project.json`：`uv sync --frozen --all-extras`，release contract、Ruff、mypy、UI 生成校验，两套 pytest 覆盖率门禁（不低于 90%）、测试数量基线、`uv build`，以及真实 PyInstaller release build/smoke。
- `file_toolbox/gui/generated/` 由 `.ui` 经 `scripts/regen_ui.py` 生成，禁止手改或用全仓格式化破坏。UI 变更同时修改源 `.ui`、重新生成并执行 `--check`。
- 唯一版本源是 `pyproject.toml [project].version`；`uv.lock` 的 editable package 版本和运行时 metadata 是派生值。不要新增 `version.txt` 或手打 tag。
- 发布契约固定为 `FileToolbox-{version}-win64.zip`、`checksums.txt`、`SBOM.spdx.json`、`build-identity.json`；ZIP 顶层 `FileToolbox/` 和 `FileToolbox/FileToolbox.exe` 是更新器接口，checksum/SBOM/identity 必须绑定同一归档。
- 文件修改命令默认 dry-run，只有明确 `--yes` 才执行；不得为了简化调用移除此保险。自动更新只替换程序目录，必须保留 `.file_toolbox/` 备份/历史并维持 hash 校验与失败回滚。
- Ruff 使用双引号/100 列/Python 3.11，mypy strict 且以 win32 为目标。仓库提供 pre-commit 配置（Ruff fix/format 与 mypy）；当前 clone 未必安装 hook，应运行等价命令。

## 六仓关系

- 本仓与 VibeOCR Protocol/Backend/Classic/Next、VibeTable 没有源码或运行时依赖，也不参与其组件版本链。
- 六仓关系仅是共享相同的 CI/CD 深模块、版本 PR 状态机、GitHub 治理和镜像策略；本仓项目命令继续留在自己的 adapter。
- 任何公共 workflow/core 修改必须与其余五仓同步；File Toolbox 的 GUI/COM/覆盖率/更新器规则不得反向塞入公共 YAML。
