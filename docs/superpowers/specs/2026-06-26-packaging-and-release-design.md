# 打包与发版方案设计

- **日期**: 2026-06-26
- **状态**: 已批准,待实现
- **作者**: brainstorming 会话

## 1. 目标

为 file-toolbox 建立完整的打包与发版工作流,覆盖四个需求:

1. **打包方案评估** —— 选定打包技术,支持本地打包 + GitHub 打包。
2. **bump version 脚本** —— 统一管理版本号,自动跳转打包流程。
3. **跳转打包** —— 一条命令从版本号变更走到可执行产物。
4. **更新项目依赖** —— 封装依赖升级流程。

### 产物形态(终端用户)

- **Windows 可执行程序**: 双击运行的 `.exe`(Nuitka `--standalone` 目录模式)。
- **便携 zip**: 同一目录压缩成 `FileToolbox-{version}-win64.zip`,解压即用。
- **不产出 wheel/sdist** —— 本项目面向终端用户,不发 PyPI。

### 非目标(YAGNI)

- macOS/Linux 可执行程序(后续可加,本期不实现)。
- 代码签名 / 自动更新器(终端用户量级未到,暂不需要)。
- Dependabot 自动 PR(依赖更新走手动 uv lock 封装)。

## 2. 打包技术选型

### 评估结论:Nuitka `--standalone`

| 方案 | 评估 |
|---|---|
| **Nuitka `--standalone`** ✅ 选定 | 编译为 C,启动快、体积略小于 PyInstaller、反编译难;`--standalone` 产目录天然满足"exe + 便携 zip"双形态 |
| PyInstaller | 最成熟、配置直观,但产物体积大;`--onefile` 无法出目录故拿不到便携 zip |
| wheel/sdist | 需目标机有 Python,**不适合终端用户分发**,已排除 |
| Briefcase / PyOxidizer | PySide6 兼容差、活跃度低,不推荐 |

### 选定模式的取舍

- **编译慢**: 首次数分钟至 10+ 分钟。接受,CI 缓存 `build/` 中间目录提速。
- **MinGW64 依赖**: 用 `--mingw64 --assume-yes-for-downloads` 让 Nuitka 自动拉取 C 编译器,本地与 CI 一致。
- **`--onefile` 排除理由**: 只出单 exe,无法满足便携 zip 需求。

## 3. 版本号真相源

**单一真相源: `pyproject.toml` 的 `[project] version`。**

### 现状改造

当前版本号在两处硬编码,存在不同步风险:

| 文件 | 现状 | 改造后 |
|---|---|---|
| `pyproject.toml` | `version = "0.1.0"` | **唯一真相源**,bump 脚本只改这里 |
| `file_toolbox/__init__.py` | `__version__ = "0.1.0"` | 改为运行时从 `importlib.metadata` 读取 |

改造后的 `__init__.py`:

```python
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("file-toolbox")
except PackageNotFoundError:  # 源码树直接运行,未安装
    __version__ = "0.0.0+unknown"
```

- 安装环境(含 Nuitka 打包后的 exe):`importlib.metadata` 读到 `pyproject.toml` 写入的版本号。
- 源码树直接 `python -m file_toolbox`:回退到 `0.0.0+unknown`,避免报错。
- `bump_version validate` 会校验 `__init__.py` 不再残留硬编码,防回归。

## 4. 组件设计

```
scripts/
├── bump_version.py      # 版本号管理:bump / current / validate
├── build_exe.py         # Nuitka 打包:exe + 便携 zip
├── update_deps.py       # uv lock 升级封装
└── release.py           # 一键编排:bump → changelog → build → commit → tag
.github/workflows/
└── release.yml          # tag 推送触发 → 复用 build_exe.py → GitHub Release
```

### 4.1 `bump_version.py`

版本号管理工具。CLI 接口(基于 typer,与项目现有 CLI 风格一致):

| 子命令 | 作用 |
|---|---|
| `bump <part>` | part ∈ `major` / `minor` / `patch` / `prerelease`。计算新版本,写入 pyproject + 迁移 changelog,自动 git commit + tag |
| `bump --set X.Y.Z` | 直接设到指定版本(精确发版) |
| `current` | 读出当前版本号,供其他脚本/CI 消费 |
| `validate` | 校验版本号符合 PEP 440 + 检查 `__init__.py` 无硬编码残留 |

**版本计算**: 基于 PEP 440。优先用 `packaging` 库(已是 uv 生态标配);若不想引入运行时依赖,退化为纯字符串解析 + 正则(本项目运行时无 packaging,bump 工具用 `uv run --with packaging` 临时引入即可)。

**CHANGELOG 自动迁移**(Keep-a-Changelog 模式):
1. 将 `## [Unreleased]` 标题下、下一个版本标题之前的所有条目,移动到新版本段 `## X.Y.Z - YYYY-MM-DD` 下。
2. 在 `## [Unreleased]` 下重新开一个空的 Added/Changed/Fixed 占位(或保留空段)。
3. 若 `## [Unreleased]` 下无任何条目,提示用户但仍生成新版本段(空发版)。

**自动 git 操作**(本需求明确要求):
```
bump <part>
  1. 计算新版本
  2. 写入 pyproject.toml
  3. 迁移 CHANGELOG.md
  4. git add pyproject.toml CHANGELOG.md
  5. git commit -m "chore(release): vX.Y.Z"
  6. git tag vX.Y.Z
  7. 提示用户: git push --tags(默认不自动 push)
```

**开关**:
- `--no-commit`: 跳过 git commit(只改文件,本地实验用)。
- `--no-tag`: 改文件 + commit 但不打 tag。
- `--push`: commit + tag 后自动 `git push && git push --tags`(对外发布动作,须显式加)。
- `--dry-run`: 预览所有改动不写盘、不动 git。

**失败回滚**: tag 创建失败(如 tag 已存在)时,`git reset --soft HEAD~1` 回滚上一步 commit,不残留半成品。已存在的 tag 视为硬错误退出。

**工作区清洁校验**: 执行前检查 `git status` 是否干净(无未提交改动),不干净则报错退出,避免把无关改动混入 release commit。

### 4.2 `build_exe.py`

Nuitka 打包脚本,本地与 CI 复用同一份。

**运行环境**:
```bash
uv run --with nuitka --extra gui --extra invoice python scripts/build_exe.py
```
- `--with nuitka`: Nuitka 作为打包工具临时引入,不进运行时依赖。
- `--extra invoice`: 确保发票依赖(pdfplumber, openpyxl)存在于打包环境,打进 exe。

**Nuitka 命令行参数**(脚本内部组装):

| 参数 | 作用 |
|---|---|
| `--standalone` | 目录模式,产出 exe + 依赖目录 |
| `--mingw64 --assume-yes-for-downloads` | 自动拉 MinGW64 编译器,本地/CI 一致 |
| `--enable-plugin=pyside6` | Nuitka 官方 PySide6 插件,处理 Qt 插件/资源 |
| `--include-package=fitz` | PyMuPDF 原生绑定,静态分析易漏 |
| `--include-package=pdfplumber` | 发票 PDF 解析 |
| `--include-package=pdfminer` | pdfplumber 依赖,懒加载易漏 |
| `--include-package=openpyxl` | Excel 导出 |
| `--include-package-data=pdfplumber` | pdfplumber 数据文件 |
| `--windows-disable-console` | GUI 应用无黑框(等价 PyInstaller `--windowed`) |
| `--remove-output` | 编译后清理中间文件 |
| `--output-dir=dist` | 标准产物目录 |
| `--company-name --product-name --file-version ...` | Windows 版本信息元数据(嵌入 exe 属性) |
| `-m file_toolbox.__main__` 或 `file_toolbox/gui/main_window.py` | 入口点(见下方"入口点") |

**入口点决策**:
当前项目无 `__main__.py`,只有 `[project.scripts]` 的 `file-toolbox` 入口指向 `file_toolbox.cli.main:app`。Nuitka standalone 需要 Python 文件入口,故:
- 方案: 新增 `file_toolbox/__main__.py`,内容为 `from file_toolbox.cli.main import app; app()`(或对应 gui 入口),作为 Nuitka 编译入口。
- 该文件同时也让 `python -m file_toolbox` 可用,顺带补齐标准 Python 包惯例。

**GUI 入口说明**: 终端用户双击 exe 应直接进 GUI(而非 CLI)。两个选项:
1. `__main__.py` 默认启动 GUI,带参数时走 CLI。
2. 单独的 `file_toolbox/gui_entry.py` 作为 Nuitka 入口,直接调 `run_gui()`。

实现时选(2)更清晰: exe = GUI 入口,CLI 仍可通过 `python -m file_toolbox` 或安装后的 `file-toolbox` 命令使用。具体由实现阶段定。

**产物后处理**:
1. 重命名 Nuitka 产物目录为 `FileToolbox/`。
2. 调 `bump_version current` 读版本号 → 嵌入产物文件名。
3. 压缩 `dist/FileToolbox/` → `dist/FileToolbox-{version}-win64.zip`。
4. 输出产物清单 + SHA256 校验和到 `dist/checksums.txt`。

### 4.3 `update_deps.py`

封装 `uv lock` 升级,提供友好输出。

| 子命令 | 作用 |
|---|---|
| `update-deps` | `uv lock --upgrade`(全量升级 lockfile) |
| `update-deps <pkg>` | `uv lock --upgrade-package <pkg>`(单包升级) |
| `update-deps --check` | dry-run,检测哪些包有新版,不改 lockfile |

**升级摘要**: 执行后对比 `uv.lock` 改动前后的包版本,输出形如:
```
升级摘要:
  pdfplumber   0.11.0 → 0.11.3
  openpyxl     3.1.2 → 3.1.5
  PySide6      6.5.0  → 6.7.2
共 3 个包升级。
提示: review uv.lock diff 后执行 git commit。
```

**开关**:
- `--dev`: 同时升级 dev 依赖组(默认 uv lock 已覆盖所有组,此开关保留以便将来区分)。
- 不自动 commit,提示用户 review `uv.lock` diff 后手动提交。

**实现**: 用 `git diff --no-index` 或直接对比前后两个 `uv.lock` 的解析结果(structured 解析 lockfile 的 package 段)。

### 4.4 `release.py`

一键编排,串联上述组件:

```bash
python scripts/release.py patch
# 等价于:
# 1. (可选) update_deps --check → 提示是否升级
# 2. bump_version patch → 改 pyproject + 迁移 changelog + commit + tag
# 3. build_exe → 出 exe + 便携 zip + checksums
# 4. 输出: 产物路径 + 下一步提示(git push --tags 触发 CI)
```

**CI 复用**: 带 `--ci` 标志时:
- 跳过交互式提示。
- 输出结构化日志(GitHub Actions `::set-output` / `$GITHUB_ENV`)。
- bump + build 全自动,不打断。

本地不带 `--ci` 时,关键步骤前暂停确认。

### 4.5 GitHub Actions `release.yml`

完整 workflow,**触发: 推送 `v*` tag**(与本地 bump → tag 流程对接):

```yaml
name: Release
on:
  push:
    tags: ['v*']

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --extra gui --extra invoice
      - run: uv run --with nuitka python scripts/build_exe.py --ci
      - uses: actions/upload-artifact@v4
        with:
          name: FileToolbox-win64
          path: |
            dist/FileToolbox-*-win64.zip
            dist/checksums.txt

  release:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4
        with: { name: FileToolbox-win64 }
      - name: 从 tag 名提取版本号
        run: echo "VERSION=${GITHUB_REF_NAME#v}" >> $GITHUB_ENV
      - name: 从 CHANGELOG.md 提取该版本 Release notes
        run: python scripts/extract_changelog.py $VERSION  # 简单提取脚本
      - uses: softprops/action-gh-release@v2
        with:
          body_path: release_notes.md
          files: |
            FileToolbox-*-win64.zip
            checksums.txt
```

**关键点**:
- **Windows runner**: 因 Office COM 功能仅 Windows,且终端用户在 Windows。
- **本地脚本与 CI 复用同一 `build_exe.py`**: 避免双份配置漂移。
- **缓存**: `setup-uv` 的 `enable-cache` 缓存 uv;Nuitka 的 `build/` 目录用 `actions/cache` 缓存提速。
- **Release notes 自动化**: 从 CHANGELOG.md 提取对应版本段(新增一个小辅助脚本 `extract_changelog.py`,或内联到 release.yml 的 run 步骤)。
- **权限**: `permissions: contents: write` 允许创建 Release。

> 注: 项目暂无 GitHub 远程。workflow 文件先写好进仓库,`git remote add` + 打 tag 后即生效。

## 5. 数据流

```
开发者                    bump_version.py          pyproject.toml         CHANGELOG.md
  │  bump patch                │                        │                     │
  │ ─────────────────────────► │ ── 写 version ────────► │                     │
  │                            │ ── 迁移条目 ─────────────────────────────────► │
  │                            │ ── git commit + tag ◄──┘                     │
  │                            │                                              │
  │                            │              build_exe.py                     │
  │                            │   读 current version ──────────────────────┐  │
  │                            │   Nuitka 编译 ────────────────────────────► │
  │                            │   产物 FileToolbox-{ver}-win64.zip          │
  │                            │                                              │
  │  git push --tags           │                                              │
  │ ───────────────────────────────────────────────────────────────────────► │
  │                            │            GitHub Actions release.yml        │
  │                            │   tag 触发 → build_exe.py --ci → Release     │
  │ ◄────────────────────────────────── GitHub Release(附 zip) ───────────── │
```

## 6. 错误处理

| 场景 | 处理 |
|---|---|
| bump 时 git 工作区不干净 | 报错退出,提示先 commit/stash 当前改动 |
| tag 已存在 | 视为硬错误;若已 commit 则 `git reset --soft HEAD~1` 回滚 |
| Nuitka 编译失败 | 非零退出,保留 build/ 日志供排查;CI 上 artifact 上传日志 |
| 缺少 invoice extra | build_exe.py 启动时校验 `uv run` 环境含 pdfplumber,缺则提示 `--extra invoice` |
| CHANGELOG 无 Unreleased 条目 | 警告但仍生成新版本段(空发版) |
| importlib.metadata 取不到版本 | 回退 `0.0.0+unknown`,不崩溃 |

## 7. 测试策略

| 组件 | 测试方式 |
|---|---|
| `bump_version.py` 版本计算 | 单元测试: patch/minor/major/prerelease 跳跃、PEP 440 校验、`--set` |
| CHANGELOG 迁移 | 单元测试: Unreleased 条目正确移动到新版本段、空 Unreleased 处理 |
| git 操作 | 集成测试(临时 git 仓库): commit + tag 创建、工作区不干净检测、tag 冲突回滚 |
| `__init__.py` 版本读取 | 单元测试: 安装后 `importlib.metadata` 返回正确版本 |
| `update_deps.py` diff 解析 | 单元测试: 给定前后两个 lockfile 片段,正确提取升级摘要 |
| `build_exe.py` / `release.yml` | **冒烟测试**: 实际跑一次打包,验证产物 exe 能启动 GUI;不写单元测试(集成性质) |

## 8. 实现顺序(供后续 plan 参考)

1. **版本真相源改造** —— 改 `__init__.py`,加 `__main__.py` 入口。
2. **bump_version.py** + 单元测试(逻辑核心,先稳)。
3. **build_exe.py** + 本地冒烟(产物能跑)。
4. **update_deps.py**(较薄)。
5. **release.py**(编排)。
6. **release.yml**(CI,复用 build_exe)。
7. **文档**: README 加"打包/发版"章节,CHANGELOG 记录本次。

## 9. 开放问题(实现阶段决策,不阻塞 spec)

- **Nuitka 入口**: `gui_entry.py` 单独文件 vs `__main__.py` 带参数分发 —— 实现阶段定。
- **CHANGELOG 空段占位风格**: 保留空 `### Added` vs 完全省略 —— 实现阶段按现有风格对齐。
- **CI 缓存 Nuitka build/ 目录的 key 策略**: 按 `pyproject.toml` hash 还是按 tag —— 实现阶段调优。
