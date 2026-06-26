# 打包与发版方案 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 file-toolbox 建立 Nuitka 打包 + 版本号管理 + 依赖更新 + GitHub Release 的完整发版工作流。

**Architecture:** 四个 scripts/ 脚本 + 一份 GitHub workflow,全部围绕 pyproject.toml 单一版本真相源串联。bump_version.py 自动改版本 + git commit + tag;build_exe.py 用 Nuitka --standalone 出 exe 目录 + 便携 zip;update_deps.py 封装 uv lock;release.py 一键编排。CI 复用本地 build_exe.py。

**Tech Stack:** Nuitka(--standalone, MinGW64, pyside6 plugin)、uv、typer(脚本 CLI)、packaging(PEP 440 版本计算)、pytest、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-06-26-packaging-and-release-design.md`

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `file_toolbox/__init__.py` | 改用 importlib.metadata 读版本,消除硬编码 | Modify |
| `file_toolbox/__main__.py` | 新增 `python -m file_toolbox` 入口(调 CLI app) | Create |
| `file_toolbox/gui_entry.py` | Nuitka 编译入口,直接启动 GUI(终端用户双击 exe 进 GUI) | Create |
| `scripts/__init__.py` | 空,让 scripts 可作为包导入(测试用) | Create |
| `scripts/bump_version.py` | 版本号管理:bump / current / validate | Create |
| `scripts/build_exe.py` | Nuitka 打包脚本 | Create |
| `scripts/update_deps.py` | uv lock 升级封装 | Create |
| `scripts/release.py` | 一键编排 | Create |
| `scripts/extract_changelog.py` | 从 CHANGELOG.md 提取指定版本 notes(CI 用) | Create |
| `tests/test_bump_version.py` | bump 逻辑单测 | Create |
| `tests/test_version_source.py` | __init__ 版本读取单测 | Create |
| `tests/test_update_deps.py` | uv.lock diff 解析单测 | Create |
| `.github/workflows/release.yml` | tag 触发的打包+发版 workflow | Create |
| `pyproject.toml` | 加 `[project.scripts]` 无需改;dev 依赖加 packaging | Modify |
| `README.md` | 加「打包与发版」章节 | Modify |
| `CHANGELOG.md` | 记录本次发版工具 | Modify |

---

## Task 1: 版本号真相源改造(__init__.py)

**Files:**
- Modify: `file_toolbox/__init__.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_version_source.py`:

```python
"""验证 __version__ 通过 importlib.metadata 读取,不硬编码。"""

import re

import file_toolbox


def test_version_is_string():
    """__version__ 必须是字符串(无论安装与否都不报错)。"""
    assert isinstance(file_toolbox.__version__, str)
    assert file_toolbox.__version__  # 非空


def test_version_no_hardcoded_literal():
    """__init__.py 不应再出现 __version__ = "0.1.0" 这类硬编码。"""
    src = (Path(__file__).resolve().parents[1] / "file_toolbox" / "__init__.py").read_text(
        encoding="utf-8"
    )
    # 允许 importlib.metadata 读取,禁止直接赋值字面量版本号
    forbidden = re.compile(r'__version__\s*=\s*"\d+\.\d+\.\d+"')
    assert not forbidden.search(src), " __init__.py 仍硬编码 __version__,应改用 importlib.metadata"
```

需要 import Path,补全:

```python
from pathlib import Path
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_version_source.py -v
```
Expected: `test_version_no_hardcoded_literal` FAIL(因现状 `__version__ = "0.1.0"` 命中正则)。

- [ ] **Step 3: 改造 __init__.py**

将 `file_toolbox/__init__.py` 完整替换为:

```python
"""File Toolbox - 批量文件工具箱:重命名、建文件夹、生成 PDF、内容替换。"""

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "File Toolbox"
APP_DESCRIPTION = "批量文件工具箱"

try:
    __version__ = version("file-toolbox")
except PackageNotFoundError:  # 源码树直接运行(未安装),回退避免崩溃
    __version__ = "0.0.0+unknown"
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_version_source.py -v
```
Expected: 2 passed。

额外手动验证(已 pip install -e . 的环境):
```bash
python -c "import file_toolbox; print(file_toolbox.__version__)"
```
Expected: 输出 `0.1.0`(从 pyproject 读到)。

- [ ] **Step 5: 提交**

```bash
git add file_toolbox/__init__.py tests/test_version_source.py
git commit -m "refactor(version): __version__ 改用 importlib.metadata 读取(单一真相源)"
```

---

## Task 2: 新增 __main__.py + gui_entry.py 入口

**Files:**
- Create: `file_toolbox/__main__.py`
- Create: `file_toolbox/gui_entry.py`

- [ ] **Step 1: 创建 __main__.py**

`python -m file_toolbox` 走 CLI(与 `file-toolbox` 命令等价):

```python
"""模块入口:python -m file_toolbox 等价于 file-toolbox 命令。"""

from file_toolbox.cli.main import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 2: 创建 gui_entry.py**

Nuitka 编译入口。终端用户双击 exe 应直接进 GUI:

```python
"""GUI 独立入口(供 Nuitka 编译为 exe)。

双击 exe 直接启动图形界面;CLI 仍可经 python -m file_toolbox 或 file-toolbox 命令使用。
"""

from file_toolbox.gui.main_window import run_gui

if __name__ == "__main__":
    run_gui()
```

- [ ] **Step 3: 验证两个入口可运行**

```bash
python -m file_toolbox --version
```
Expected: 输出 `0.1.0`(走 CLI app,打印版本后退出)。

验证 gui_entry 不报导入错误(不实际启动窗口,仅导入):
```bash
python -c "from file_toolbox.gui_entry import run_gui; print('ok')"
```
Expected: 输出 `ok`。

- [ ] **Step 4: 提交**

```bash
git add file_toolbox/__main__.py file_toolbox/gui_entry.py
git commit -m "feat(entry): __main__.py + gui_entry.py(打包与模块入口)"
```

---

## Task 3: bump_version.py —— 版本计算 + PEP 440(纯函数,先 TDD)

**Files:**
- Modify: `pyproject.toml`(dev 依赖加 packaging)
- Create: `scripts/__init__.py`
- Create: `scripts/bump_version.py`
- Test: `tests/test_bump_version.py`

- [ ] **Step 1: dev 依赖加 packaging**

在 `pyproject.toml` 的 `dev` 数组里追加 `"packaging>=24.0"`:

```toml
dev = ["pytest>=8.0", "pytest-cov>=5.0", "ruff>=0.5", "mypy>=1.10", "reportlab>=4.0", "packaging>=24.0"]
```

同步 lockfile:
```bash
uv sync --extra dev
```

- [ ] **Step 2: 写失败测试 —— 版本计算纯函数**

创建 `tests/test_bump_version.py`:

```python
"""bump_version.py 纯函数逻辑测试。"""

import sys
from pathlib import Path

# 让 tests 能 import scripts 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bump_version import bump_version, validate_pep440


class TestBumpVersion:
    def test_patch(self):
        assert bump_version("1.2.3", "patch") == "1.2.4"

    def test_minor_resets_patch(self):
        assert bump_version("1.2.3", "minor") == "1.3.0"

    def test_major_resets_minor_patch(self):
        assert bump_version("1.2.3", "major") == "2.0.0"

    def test_prerelease_dev_to_release(self):
        # dev/prerelease → 去掉预发布后缀,成为正式版
        assert bump_version("1.2.3a1", "prerelease") == "1.2.3"

    def test_prerelease_release_to_alpha(self):
        # 正式版 → 加 a1 预发布
        assert bump_version("1.2.3", "prerelease") == "1.2.4a1"

    def test_invalid_part_raises(self):
        import pytest

        with pytest.raises(ValueError):
            bump_version("1.2.3", "bogus")


class TestValidatePEP440:
    def test_valid_release(self):
        assert validate_pep440("1.2.3") is True

    def test_valid_prerelease(self):
        assert validate_pep440("1.2.3a1") is True

    def test_invalid(self):
        assert validate_pep440("1.2") is False
        assert validate_pep440("not-a-version") is False
```

- [ ] **Step 3: 运行测试确认失败**

```bash
pytest tests/test_bump_version.py -v
```
Expected: ImportError / ModuleNotFoundError(scripts.bump_version 不存在)。

- [ ] **Step 4: 实现 bump_version.py 的纯函数部分**

创建 `scripts/__init__.py`(空文件)。

创建 `scripts/bump_version.py`,先只写纯函数(后面 Task 补 CLI 和文件操作):

```python
"""版本号管理:bump / current / validate。

单一真相源:pyproject.toml [project] version。
运行方式:uv run --extra dev python scripts/bump_version.py <command>
"""

from __future__ import annotations

from packaging.version import Version, InvalidVersion

PARTS = ("major", "minor", "patch", "prerelease")


def validate_pep440(version: str) -> bool:
    """校验字符串是否符合 PEP 440。"""
    try:
        Version(version)
        return True
    except InvalidVersion:
        return False


def bump_version(current: str, part: str) -> str:
    """根据 part 计算下一个版本号(PEP 440)。

    part:
      - patch:   1.2.3   → 1.2.4
      - minor:   1.2.3   → 1.3.0
      - major:   1.2.3   → 2.0.0
      - prerelease:
          预发布版(1.2.3a1) → 1.2.3(转正)
          正式版(1.2.3)    → 1.2.4a1(开新预发布)
    """
    if part not in PARTS:
        raise ValueError(f"无效的 part: {part!r},应为 {PARTS}")
    if not validate_pep440(current):
        raise ValueError(f"当前版本不符合 PEP 440: {current!r}")

    v = Version(current)
    if part == "patch":
        return f"{v.major}.{v.minor}.{v.micro + 1}"
    if part == "minor":
        return f"{v.major}.{v.minor + 1}.0"
    if part == "major":
        return f"{v.major + 1}.0.0"
    # prerelease
    if v.is_prerelease:
        # 转正:去掉预发布后缀
        return f"{v.major}.{v.minor}.{v.micro}"
    # 正式版 → 开新预发布(patch+1 加 a1)
    return f"{v.major}.{v.minor}.{v.micro + 1}a1"
```

- [ ] **Step 5: 运行测试确认通过**

```bash
pytest tests/test_bump_version.py -v
```
Expected: 8 passed。

- [ ] **Step 6: 提交**

```bash
git add scripts/__init__.py scripts/bump_version.py tests/test_bump_version.py pyproject.toml uv.lock
git commit -m "feat(bump): 版本计算 + PEP 440 校验(纯函数)"
```

---

## Task 4: bump_version.py —— CHANGELOG 迁移(纯函数,先 TDD)

**Files:**
- Modify: `scripts/bump_version.py`
- Modify: `tests/test_bump_version.py`

- [ ] **Step 1: 写失败测试 —— changelog 迁移**

在 `tests/test_bump_version.py` 末尾追加:

```python
class TestMigrateChangelog:
    def _sample(self) -> str:
        return """# Changelog

## [Unreleased]

### Added
- 新功能 A
- 新功能 B

### Fixed
- 修 bug X

## 0.1.0 - 2026-06-25

### Added
- 初始功能
"""

    def test_moves_unreleased_to_new_version(self):
        from scripts.bump_version import migrate_changelog

        result = migrate_changelog(self._sample(), "0.2.0", "2026-06-26")
        # 新版本段在 Unreleased 之后
        assert "## [Unreleased]" in result
        assert "## 0.2.0 - 2026-06-26" in result
        # 新功能 A/B 移到了 0.2.0 段
        idx_unreleased = result.index("## [Unreleased]")
        idx_new = result.index("## 0.2.0 - 2026-06-26")
        idx_old = result.index("## 0.1.0")
        assert idx_unreleased < idx_new < idx_old
        assert "新功能 A" in result[result.index("## 0.2.0"):result.index("## 0.1.0")]

    def test_empty_unreleased_still_emits_new_section(self):
        from scripts.bump_version import migrate_changelog

        empty = """# Changelog

## [Unreleased]

## 0.1.0 - 2026-06-25

### Added
- 初始
"""
        result = migrate_changelog(empty, "0.2.0", "2026-06-26")
        assert "## 0.2.0 - 2026-06-26" in result
        # Unreleased 段保留(可能为空)
        assert "## [Unreleased]" in result
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_bump_version.py::TestMigrateChangelog -v
```
Expected: ImportError(migrate_changelog 未定义)。

- [ ] **Step 3: 实现 migrate_changelog**

在 `scripts/bump_version.py` 追加:

```python
import re

_UNRELEASED_HEADER = "## [Unreleased]"


def migrate_changelog(content: str, new_version: str, date: str) -> str:
    """把 [Unreleased] 段的条目迁移到新版本段下,并重开空 Unreleased。

    结构(迁移后):
      # Changelog

      ## [Unreleased]

      ## <new_version> - <date>
      ...(原 Unreleased 的条目)

      ## <older versions...>
    """
    if _UNRELEASED_HEADER not in content:
        raise ValueError("CHANGELOG.md 缺少 '## [Unreleased]' 段")

    unreleased_idx = content.index(_UNRELEASED_HEADER)
    # Unreleased 段之后的内容
    after_unreleased = content[unreleased_idx + len(_UNRELEASED_HEADER):]
    # 下一个版本标题(## x.y.z 或 ## [Unreleased])之前 = Unreleased 条目体
    next_header_match = re.search(r"\n## ", after_unreleased)
    if next_header_match:
        unreleased_body = after_unreleased[: next_header_match.start()]
        rest = after_unreleased[next_header_match.start():]
    else:
        unreleased_body = after_unreleased
        rest = ""

    new_section = f"## {new_version} - {date}\n{unreleased_body.rstrip()}\n"
    # 重开空 Unreleased,接新版本段,再接 rest
    rebuilt = (
        content[:unreleased_idx]
        + f"{_UNRELEASED_HEADER}\n\n"
        + new_section
        + ("\n" + rest.lstrip("\n") if rest.strip() else "")
    )
    return rebuilt
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_bump_version.py::TestMigrateChangelog -v
```
Expected: 2 passed。

- [ ] **Step 5: 提交**

```bash
git add scripts/bump_version.py tests/test_bump_version.py
git commit -m "feat(bump): CHANGELOG 自动迁移(Unreleased → 新版本段)"
```

---

## Task 5: bump_version.py —— pyproject 读写 + validate

**Files:**
- Modify: `scripts/bump_version.py`
- Modify: `tests/test_bump_version.py`

- [ ] **Step 1: 写失败测试 —— pyproject 读写 + validate 入口**

在 `tests/test_bump_version.py` 末尾追加:

```python
class TestPyprojectVersionIO:
    def test_read_current_version(self, tmp_path):
        from scripts.bump_version import read_pyproject_version, write_pyproject_version

        pj = tmp_path / "pyproject.toml"
        pj.write_text(
            '[project]\nname = "file-toolbox"\nversion = "0.3.7"\n', encoding="utf-8"
        )
        assert read_pyproject_version(pj) == "0.3.7"

    def test_write_version_preserves_rest(self, tmp_path):
        from scripts.bump_version import read_pyproject_version, write_pyproject_version

        original = (
            '[project]\n'
            'name = "file-toolbox"\n'
            'version = "0.3.7"\n'
            'requires-python = ">=3.11"\n'
        )
        pj = tmp_path / "pyproject.toml"
        pj.write_text(original, encoding="utf-8")
        write_pyproject_version(pj, "0.4.0")
        new = pj.read_text(encoding="utf-8")
        assert read_pyproject_version(pj) == "0.4.0"
        # 其他行保持不变
        assert 'name = "file-toolbox"' in new
        assert 'requires-python = ">=3.11"' in new
        # 只有一处 version 行
        assert new.count('version =') == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_bump_version.py::TestPyprojectVersionIO -v
```
Expected: ImportError。

- [ ] **Step 3: 实现 pyproject 读写函数**

在 `scripts/bump_version.py` 追加:

```python
from pathlib import Path

_VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def read_pyproject_version(path: Path) -> str:
    """从 pyproject.toml 读 [project] version。"""
    text = path.read_text(encoding="utf-8")
    m = _VERSION_LINE.search(text)
    if not m:
        raise ValueError(f"{path} 中未找到 version = \"...\" 行")
    return m.group(1)


def write_pyproject_version(path: Path, new_version: str) -> None:
    """把新版本写回 pyproject.toml,只替换 version 行,保留其余内容。"""
    if not validate_pep440(new_version):
        raise ValueError(f"新版本不符合 PEP 440: {new_version!r}")
    text = path.read_text(encoding="utf-8")
    new_text, n = _VERSION_LINE.subn(f'version = "{new_version}"', text, count=1)
    if n == 0:
        raise ValueError(f"{path} 中未找到 version = \"...\" 行")
    path.write_text(new_text, encoding="utf-8")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_bump_version.py::TestPyprojectVersionIO -v
```
Expected: 2 passed。

- [ ] **Step 5: 提交**

```bash
git add scripts/bump_version.py tests/test_bump_version.py
git commit -m "feat(bump): pyproject.toml 版本读写(保留其余内容)"
```

---

## Task 6: bump_version.py —— git 自动化 + validate 命令

**Files:**
- Modify: `scripts/bump_version.py`

> 注:git 操作用真实子进程调用 git,不写单元测试(集成性质,会动真实仓库)。下面用 typer 的命令把所有函数串起来。

- [ ] **Step 1: 实现工作区检查 + git 操作函数**

在 `scripts/bump_version.py` 追加:

```python
import subprocess


class GitError(RuntimeError):
    """git 操作失败。"""


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=check
    )


def working_tree_clean(root: Path) -> bool:
    """git status 是否干净(无未提交改动)。"""
    res = _git("status", "--porcelain", cwd=root)
    return res.stdout.strip() == ""


def tag_exists(root: Path, tag: str) -> bool:
    res = _git("tag", "-l", tag, cwd=root, check=False)
    return res.stdout.strip() == tag


def git_commit_and_tag(
    root: Path, files: list[str], version: str, *, commit: bool, tag: bool
) -> None:
    """add → commit → tag。tag 失败时回滚 commit。"""
    tag_name = f"v{version}"
    if tag and tag_exists(root, tag_name):
        raise GitError(f"tag {tag_name} 已存在")
    if not commit:
        return
    # 工作区必须干净(除本次将 add 的文件外)
    _git("add", *files, cwd=root)
    _git("commit", "-m", f"chore(release): {tag_name}", cwd=root)
    if tag:
        try:
            _git("tag", tag_name, cwd=root)
        except subprocess.CalledProcessError as e:
            # 回滚刚提交的 commit(保留改动在工作区)
            _git("reset", "--soft", "HEAD~1", cwd=root, check=False)
            raise GitError(f"创建 tag {tag_name} 失败: {e.stderr}") from e


def push_tags(root: Path) -> None:
    _git("push", cwd=root)
    _git("push", "--tags", cwd=root)
```

- [ ] **Step 2: 实现 typer CLI 主入口**

在 `scripts/bump_version.py` 末尾追加:

```python
import datetime as _dt

import typer

_ROOT = Path(__file__).resolve().parents[1]
_PYPROJECT = _ROOT / "pyproject.toml"
_CHANGELOG = _ROOT / "CHANGELOG.md"

cli = typer.Typer(add_completion=False, help="file-toolbox 版本号管理")


@cli.command()
def current():
    """打印当前版本号(来自 pyproject.toml)。"""
    typer.echo(read_pyproject_version(_PYPROJECT))


@cli.command()
def validate():
    """校验版本号 PEP 440 + __init__.py 无硬编码残留。"""
    ver = read_pyproject_version(_PYPROJECT)
    if not validate_pep440(ver):
        typer.secho(f"✗ {ver} 不符合 PEP 440", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    init_src = (_ROOT / "file_toolbox" / "__init__.py").read_text(encoding="utf-8")
    if re.search(r'__version__\s*=\s*"\d+\.\d+\.\d+"', init_src):
        typer.secho("✗ __init__.py 仍硬编码 __version__", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.secho(f"✓ {ver} 有效", fg=typer.colors.GREEN)


@cli.command()
def bump(
    part: str = typer.Argument(None, help="major/minor/patch/prerelease(与 --set 二选一)"),
    set_version: str = typer.Option(None, "--set", help="直接设到指定版本(PEP 440)"),
    no_commit: bool = typer.Option(False, "--no-commit", help="只改文件,不 git commit"),
    no_tag: bool = typer.Option(False, "--no-tag", help="不打 git tag"),
    push: bool = typer.Option(False, "--push", help="commit+tag 后自动 git push --tags"),
    dry_run: bool = typer.Option(False, "--dry-run", help="预览,不写盘不动 git"),
):
    """bump 版本号 + 改 pyproject + 迁移 CHANGELOG + git commit + tag。"""
    if not part and not set_version:
        typer.secho("错误:需要 <part> 或 --set", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if part and set_version:
        typer.secho("错误:<part> 与 --set 互斥", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    current_ver = read_pyproject_version(_PYPROJECT)
    new_ver = set_version if set_version else bump_version(current_ver, part)
    if not validate_pep440(new_ver):
        typer.secho(f"✗ 新版本 {new_ver} 不符合 PEP 440", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    date = _dt.date.today().isoformat()

    if dry_run:
        typer.echo(f"[dry-run] {current_ver} → {new_ver} ({date})")
        typer.echo("[dry-run] 将迁移 CHANGELOG,commit + tag v%s" % new_ver)
        return

    # 工作区清洁检查(commit 前提下)
    if not no_commit and not working_tree_clean(_ROOT):
        typer.secho(
            "✗ git 工作区不干净,请先 commit/stash 当前改动", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(1)

    # 写 pyproject
    write_pyproject_version(_PYPROJECT, new_ver)
    typer.secho(f"✓ pyproject.toml: {current_ver} → {new_ver}", fg=typer.colors.GREEN)

    # 迁移 CHANGELOG
    cl_text = _CHANGELOG.read_text(encoding="utf-8")
    new_cl = migrate_changelog(cl_text, new_ver, date)
    _CHANGELOG.write_text(new_cl, encoding="utf-8")
    typer.secho(f"✓ CHANGELOG.md: 新增 {new_ver} 段", fg=typer.colors.GREEN)

    # git commit + tag
    files = ["pyproject.toml", "CHANGELOG.md"]
    try:
        git_commit_and_tag(_ROOT, files, new_ver, commit=not no_commit, tag=not no_tag)
    except GitError as e:
        typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    if not no_commit:
        typer.secho(f"✓ git commit + tag v{new_ver}", fg=typer.colors.GREEN)

    if push:
        push_tags(_ROOT)
        typer.secho("✓ git push --tags(触发 CI 发版)", fg=typer.colors.GREEN)
    else:
        typer.echo(f"\n下一步: git push --tags  (触发 CI 发版 v{new_ver})")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 3: 手动冒烟测试 validate + current**

```bash
uv run --extra dev python scripts/bump_version.py current
```
Expected: `0.1.0`。

```bash
uv run --extra dev python scripts/bump_version.py validate
```
Expected: `✓ 0.1.0 有效`。

- [ ] **Step 4: 手动冒烟测试 dry-run(不动 git)**

```bash
uv run --extra dev python scripts/bump_version.py bump patch --dry-run
```
Expected: `[dry-run] 0.1.0 → 0.2.0` 之类(patch 应得 0.1.1)。

> ⚠️ 注意:实际 bump 会改 pyproject + changelog + 打 tag,属真实发版动作,不在本 Task 执行,留到首次真实发版时用。

- [ ] **Step 5: 提交**

```bash
git add scripts/bump_version.py
git commit -m "feat(bump): git 自动化(commit+tag+回滚)+ typer CLI(current/validate/bump)"
```

---

## Task 7: update_deps.py —— uv lock 封装 + diff 解析

**Files:**
- Create: `scripts/update_deps.py`
- Test: `tests/test_update_deps.py`

- [ ] **Step 1: 写失败测试 —— lockfile diff 解析**

创建 `tests/test_update_deps.py`:

```python
"""update_deps.py 的 lockfile diff 解析测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.update_deps import parse_lock_versions, diff_upgrades


def _lock_snippet(packages: dict[str, str]) -> str:
    """生成 uv.lock 片段(只含 package 段的 name/version)。"""
    blocks = []
    for name, ver in packages.items():
        blocks.append(
            f'name = "{name}"\nversion = "{ver}"\nsdist = {{ }}\n'
        )
    return "\n".join(blocks)


def test_parse_lock_versions():
    text = _lock_snippet({"pdfplumber": "0.11.0", "openpyxl": "3.1.2"})
    versions = parse_lock_versions(text)
    assert versions == {"pdfplumber": "0.11.0", "openpyxl": "3.1.2"}


def test_diff_upgrades():
    before = {"pdfplumber": "0.11.0", "openpyxl": "3.1.2", "PySide6": "6.5.0"}
    after = {"pdfplumber": "0.11.3", "openpyxl": "3.1.2", "PySide6": "6.7.2"}
    upgrades = diff_upgrades(before, after)
    # 只列变化的包
    assert upgrades == {"pdfplumber": ("0.11.0", "0.11.3"), "PySide6": ("6.5.0", "6.7.2")}


def test_diff_no_change():
    before = {"a": "1.0.0"}
    after = {"a": "1.0.0"}
    assert diff_upgrades(before, after) == {}


def test_diff_new_package_ignored():
    # 新增包不算"升级"
    before = {"a": "1.0.0"}
    after = {"a": "1.0.0", "b": "2.0.0"}
    assert diff_upgrades(before, after) == {}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_update_deps.py -v
```
Expected: ImportError。

- [ ] **Step 3: 实现 update_deps.py 的解析函数**

创建 `scripts/update_deps.py`:

```python
"""依赖更新:封装 uv lock --upgrade,输出升级摘要。

运行方式:uv run --extra dev python scripts/update_deps.py [pkg|--check]
"""

from __future__ import annotations

import re

# uv.lock 中每个 package 段:name = "x" 紧跟 version = "y"
_PACKAGE_RE = re.compile(r'name\s*=\s*"([^"]+)"\s*\nversion\s*=\s*"([^"]+)"')


def parse_lock_versions(lock_text: str) -> dict[str, str]:
    """从 uv.lock 文本解析 {包名: 版本}。"""
    return {name: ver for name, ver in _PACKAGE_RE.findall(lock_text)}


def diff_upgrades(
    before: dict[str, str], after: dict[str, str]
) -> dict[str, tuple[str, str]]:
    """对比前后版本,返回 {包名: (旧版, 新版)},只含版本变化的包。"""
    result: dict[str, tuple[str, str]] = {}
    for name, new_ver in after.items():
        old_ver = before.get(name)
        if old_ver is not None and old_ver != new_ver:
            result[name] = (old_ver, new_ver)
    return result
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_update_deps.py -v
```
Expected: 4 passed。

- [ ] **Step 5: 实现 typer CLI(update / check 命令)**

在 `scripts/update_deps.py` 追加:

```python
import subprocess
from pathlib import Path

import typer

_ROOT = Path(__file__).resolve().parents[1]
_LOCK = _ROOT / "uv.lock"

cli = typer.Typer(add_completion=False, help="file-toolbox 依赖更新(uv lock 封装)")


def _read_lock() -> dict[str, str]:
    return parse_lock_versions(_LOCK.read_text(encoding="utf-8"))


@cli.command()
def update(
    package: str = typer.Argument(None, help="只升级指定包(省略=全量升级)"),
):
    """执行 uv lock --upgrade(全量)或 --upgrade-package <pkg>(单包)。"""
    before = _read_lock()
    cmd = ["uv", "lock"]
    if package:
        cmd += ["--upgrade-package", package]
    else:
        cmd += ["--upgrade"]
    typer.echo(f"运行: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(_ROOT), check=True)
    after = _read_lock()
    upgrades = diff_upgrades(before, after)
    _print_summary(upgrades)


@cli.command(name="check")
def check():
    """dry-run 检测哪些包有新版(不改 lockfile)。"""
    before = _read_lock()
    # uv lock --upgrade 仍会改文件;用 --dry-run 避免落盘
    proc = subprocess.run(
        ["uv", "lock", "--upgrade", "--dry-run"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    # dry-run 输出在 stdout,但不含完整 lock;退而求其次:解析 stdout 里 uv 报告的变化
    # uv lock --dry-run 会打印 "Updated <pkg> <old> -> <new>" 之类行
    changes = _parse_uv_dryrun(proc.stdout)
    if not changes:
        typer.secho("所有依赖已是最新。", fg=typer.colors.GREEN)
        return
    typer.echo("可升级:")
    for name, (old, new) in changes.items():
        typer.echo(f"  {name:<20} {old} → {new}")
    typer.echo(f"\n共 {len(changes)} 个包可升级。运行 update-deps update 升级。")


_DRYRUN_RE = re.compile(r"Updated\s+(\S+)\s+(\S+)\s*->\s*(\S+)")


def _parse_uv_dryrun(stdout: str) -> dict[str, tuple[str, str]]:
    """解析 uv lock --dry-run 的输出。uv 格式可能变,这里尽力解析。"""
    result: dict[str, tuple[str, str]] = {}
    for m in _DRYRUN_RE.finditer(stdout):
        name, old, new = m.group(1), m.group(2), m.group(3)
        result[name] = (old, new)
    return result


def _print_summary(upgrades: dict[str, tuple[str, str]]) -> None:
    if not upgrades:
        typer.secho("无依赖升级。", fg=typer.colors.GREEN)
        return
    typer.echo("升级摘要:")
    for name, (old, new) in sorted(upgrades.items()):
        typer.echo(f"  {name:<20} {old} → {new}")
    typer.echo(f"共 {len(upgrades)} 个包升级。")
    typer.echo("提示: review uv.lock diff 后执行 git commit。")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 6: 手动冒烟**

```bash
uv run --extra dev python scripts/update_deps.py check
```
Expected: 输出"所有依赖已是最新"或可升级列表(取决于 uv.lock 现状)。

- [ ] **Step 7: 提交**

```bash
git add scripts/update_deps.py tests/test_update_deps.py
git commit -m "feat(deps): update_deps.py(uv lock 封装 + 升级摘要)"
```

---

## Task 8: build_exe.py —— Nuitka 打包脚本

**Files:**
- Create: `scripts/build_exe.py`

> 打包是集成性质,靠冒烟测试(产物能启动),不写单元测试。

- [ ] **Step 1: 创建 build_exe.py**

```python
"""Nuitka 打包:--standalone 产出 exe 目录 + 便携 zip。

本地运行:
    uv run --with nuitka --extra gui --extra invoice python scripts/build_exe.py [--ci]

CI 复用同一脚本(带 --ci)。
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import typer

_ROOT = Path(__file__).resolve().parents[1]
_DIST = _ROOT / "dist"
_ENTRY = _ROOT / "file_toolbox" / "gui_entry.py"
_PRODUCT = "FileToolbox"

cli = typer.Typer(add_completion=False, help="file-toolbox Nuitka 打包")


def _current_version() -> str:
    sys.path.insert(0, str(_ROOT / "scripts"))
    from bump_version import read_pyproject_version  # type: ignore[import-not-found]

    return read_pyproject_version(_ROOT / "pyproject.toml")


def _build_command(output_dir: Path, version: str) -> list[str]:
    return [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--mingw64",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",
        "--include-package=fitz",            # PyMuPDF
        "--include-package=pdfplumber",      # invoice
        "--include-package=pdfminer",        # pdfplumber 依赖,懒加载
        "--include-package=pdfminer.six",    # pdfminer 子模块
        "--include-package=openpyxl",        # Excel 导出
        "--include-package-data=pdfplumber", # pdfplumber 数据文件
        "--include-package=chardet",         # 编码检测
        "--windows-disable-console",         # GUI 无黑框
        "--remove-output",                   # 清理中间文件
        f"--output-dir={output_dir}",
        f"--output-filename={_PRODUCT}.exe",
        # Windows 版本信息元数据
        f"--company-name=FileToolbox",
        f"--product-name={_PRODUCT}",
        f"--file-version={version}",
        f"--product-version={version}",
        f"--file-description=File Toolbox",
        str(_ENTRY),
    ]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@cli.command()
def build(ci: bool = typer.Option(False, "--ci", help="CI 模式:非交互,结构化输出")):
    """Nuitka 编译 → 压缩便携 zip → 生成 checksums。"""
    version = _current_version()
    typer.echo(f"打包版本: {version}")

    # 清理旧产物
    if _DIST.exists():
        shutil.rmtree(_DIST)
    _DIST.mkdir(parents=True)

    build_dir = _ROOT / "build"
    cmd = _build_command(build_dir, version)
    typer.echo("运行 Nuitka...")
    if ci:
        subprocess.run(cmd, cwd=str(_ROOT), check=True)
    else:
        subprocess.run(cmd, cwd=str(_ROOT), check=True)

    # Nuitka standalone 产物目录名 = 入口名(gui_entry.dist)
    candidate = _DIST / "gui_entry.dist"
    if not candidate.exists():
        # 兜底:找 dist 下唯一 .dist 目录
        dists = list(_DIST.glob("*.dist"))
        if not dists:
            typer.secho("✗ 未找到 Nuitka standalone 产物目录", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        candidate = dists[0]

    product_dir = _DIST / _PRODUCT
    if product_dir.exists():
        shutil.rmtree(product_dir)
    candidate.rename(product_dir)

    exe = product_dir / f"{_PRODUCT}.exe"
    if not exe.exists():
        typer.secho(f"✗ 未找到产物 exe: {exe}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.secho(f"✓ exe: {exe}", fg=typer.colors.GREEN)

    # 便携 zip
    zip_name = f"{_PRODUCT}-{version}-win64.zip"
    zip_path = _DIST / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in product_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(product_dir.parent))
    typer.secho(f"✓ zip: {zip_path}", fg=typer.colors.GREEN)

    # checksums
    checksums = _DIST / "checksums.txt"
    lines = [f"{_sha256(zip_path)}  {zip_name}"]
    checksums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    typer.secho(f"✓ checksums: {checksums}", fg=typer.colors.GREEN)

    if ci:
        # GitHub Actions 输出
        gha = Path("checksums.txt")
        print(f"::set-output name=zip::{zip_name}")
        print(f"::set-output name=version::{version}")
    typer.echo("\n打包完成。产物在 dist/。")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 2: 冒烟测试打包**

```bash
uv run --with nuitka --extra gui --extra invoice python scripts/build_exe.py build
```
Expected: 编译数分钟后,输出 `✓ exe`、`✓ zip`、`✓ checksums`,dist/ 下有 `FileToolbox/FileToolbox.exe` 和 `FileToolbox-0.1.0-win64.zip`。

> ⚠️ 首次编译会下载 MinGW64(因 --assume-yes-for-downloads),需联网。如编译失败,见下 Step 3 排查。

- [ ] **Step 3: 验证产物 exe 能启动 GUI**

```bash
./dist/FileToolbox/FileToolbox.exe &
sleep 3
# 手动确认 GUI 窗口出现后关闭
```
Expected: File Toolbox 主窗口出现(5 个 Tab)。若崩溃:
- ImportError 某模块 → 在 `_build_command` 加 `--include-package=<缺失模块>` 重新打包
- Qt 插件缺失 → 确认 `--enable-plugin=pyside6` 生效

- [ ] **Step 4: 提交**

```bash
git add scripts/build_exe.py
git commit -m "feat(build): Nuitka --standalone 打包脚本(exe + 便携 zip + checksums)"
```

> 注:dist/ 和 build/ 已在 .gitignore(第 4 行 `dist/`、第 5 行 `build/`),不会误提交。

---

## Task 9: release.py —— 一键编排

**Files:**
- Create: `scripts/release.py`

- [ ] **Step 1: 创建 release.py**

```python
"""一键发版编排:bump → (可选依赖升级) → build → 提示推送。

本地:
    uv run --extra dev python scripts/release.py patch
    # 等价: bump → build,完成后提示 git push --tags

CI:
    python scripts/release.py patch --ci
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

_ROOT = Path(__file__).resolve().parents[1]
_PY = [sys.executable]

cli = typer.Typer(add_completion=False, help="file-toolbox 一键发版")


def _run(script: str, *args: str, check: bool = True) -> None:
    cmd = _PY + [str(_ROOT / "scripts" / script), *args]
    typer.echo(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(_ROOT), check=check)


@cli.command()
def release(
    part: str = typer.Argument(None, help="major/minor/patch/prerelease(与 --set 二选一)"),
    set_version: str = typer.Option(None, "--set", help="直接设到指定版本"),
    update_deps: bool = typer.Option(
        False, "--update-deps", help="发版前先跑 update_deps check"
    ),
    skip_build: bool = typer.Option(False, "--skip-build", help="只 bump,不打包"),
    ci: bool = typer.Option(False, "--ci", help="CI 模式:非交互"),
):
    """bump 版本 → build → 提示推送。"""
    if not part and not set_version:
        typer.secho("错误:需要 <part> 或 --set", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if update_deps and not ci:
        typer.echo("=== 检查依赖更新 ===")
        _run("update_deps.py", "check", check=False)

    # 1. bump(自动 commit + tag)
    typer.echo("=== bump 版本 ===")
    bump_args = []
    if set_version:
        bump_args += ["--set", set_version]
    else:
        bump_args.append(part)
    if ci:
        bump_args.append("--push")  # CI 里直接推送触发后续
    _run("bump_version.py", "bump", *bump_args)

    # 2. build(非 CI 且 skip-build 时跳过)
    if not skip_build:
        typer.echo("=== Nuitka 打包 ===")
        build_args = ["build"]
        if ci:
            build_args.append("--ci")
        _run("build_exe.py", *build_args)

    if not ci:
        typer.echo(
            "\n发版准备完成。下一步: git push --tags  (CI 会自动出 GitHub Release)"
        )
    typer.secho("✓ release 流程结束", fg=typer.colors.GREEN)


if __name__ == "__main__":
    cli()
```

- [ ] **Step 2: 冒烟测试 --skip-build(只走 bump 的 dry 链路,不真打 tag)**

由于真 bump 会打 tag,这里只验证脚本能组装命令(用 bump 的 dry-run):

```bash
# 先确认脚本可解析(不实际执行 bump/build)
uv run --extra dev python scripts/release.py --help
```
Expected: 打印 release 命令帮助。

> 真实 release 流程留到首次正式发版执行,不在本 Task 触发。

- [ ] **Step 3: 提交**

```bash
git add scripts/release.py
git commit -m "feat(release): 一键编排脚本(bump → build → 提示推送)"
```

---

## Task 10: extract_changelog.py —— CI 提取 Release notes

**Files:**
- Create: `scripts/extract_changelog.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_bump_version.py` 末尾追加(同属 changelog 处理逻辑):

```python
class TestExtractChangelog:
    def test_extract_existing_version(self):
        from scripts.extract_changelog import extract_version_notes

        content = """# Changelog

## [Unreleased]

## 0.2.0 - 2026-06-26

### Added
- 新功能 A

### Fixed
- bug X

## 0.1.0 - 2026-06-25

### Added
- 初始
"""
        notes = extract_version_notes(content, "0.2.0")
        assert "新功能 A" in notes
        assert "bug X" in notes
        assert "初始" not in notes  # 不含旧版本

    def test_version_not_found_raises(self):
        import pytest

        from scripts.extract_changelog import extract_version_notes

        with pytest.raises(ValueError):
            extract_version_notes("# Changelog\n## 0.1.0\n\n- x\n", "9.9.9")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_bump_version.py::TestExtractChangelog -v
```
Expected: ImportError。

- [ ] **Step 3: 实现 extract_changelog.py**

```python
"""从 CHANGELOG.md 提取指定版本的 Release notes(CI 发版用)。

用法: python scripts/extract_changelog.py <version> [--out release_notes.md]
"""

from __future__ import annotations

import re
from pathlib import Path

import typer

_CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def extract_version_notes(content: str, version: str) -> str:
    """提取 CHANGELOG.md 中某版本段的内容(到下一个版本标题前)。"""
    # 匹配 ## <version> 或 ## <version> - <date>
    pattern = re.compile(
        rf"^## {re.escape(version)}(?:\s+-\s+\S+)?\s*\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(content)
    if not m:
        raise ValueError(f"CHANGELOG.md 中未找到版本 {version}")
    return m.group(1).strip()


cli = typer.Typer(add_completion=False, help="提取 CHANGELOG 指定版本 Release notes")


@cli.command()
def main(
    version: str = typer.Argument(..., help="版本号,如 0.2.0"),
    out: Path = typer.Option(Path("release_notes.md"), "--out", help="输出文件"),
):
    """提取并写入 Release notes 文件。"""
    content = _CHANGELOG.read_text(encoding="utf-8")
    notes = extract_version_notes(content, version)
    out.write_text(notes + "\n", encoding="utf-8")
    typer.echo(f"✓ Release notes 写入 {out}")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_bump_version.py::TestExtractChangelog -v
```
Expected: 2 passed。

- [ ] **Step 5: 提交**

```bash
git add scripts/extract_changelog.py tests/test_bump_version.py
git commit -m "feat(ci): extract_changelog.py(提取版本 Release notes)"
```

---

## Task 11: GitHub Actions release.yml

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: 创建 workflow 文件**

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: 安装 uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: 同步依赖(含 gui + invoice + dev)
        run: uv sync --extra gui --extra invoice --extra dev

      - name: 缓存 Nuitka build 目录
        uses: actions/cache@v4
        with:
          path: build
          key: nuitka-${{ runner.os }}-${{ hashFiles('pyproject.toml') }}

      - name: Nuitka 打包
        run: uv run --with nuitka python scripts/build_exe.py build --ci

      - name: 上传产物
        uses: actions/upload-artifact@v4
        with:
          name: FileToolbox-win64
          path: |
            dist/FileToolbox-*-win64.zip
            dist/checksums.txt
          if-no-files-found: error

  release:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: 下载产物
        uses: actions/download-artifact@v4
        with:
          name: FileToolbox-win64
          path: artifacts

      - name: 从 tag 提取版本号
        id: ver
        run: echo "version=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"

      - name: 安装 uv
        uses: astral-sh/setup-uv@v3

      - name: 提取 Release notes
        run: uv run --extra dev python scripts/extract_changelog.py "${{ steps.ver.outputs.version }}" --out release_notes.md

      - name: 创建 GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          body_path: release_notes.md
          files: |
            artifacts/FileToolbox-*-win64.zip
            artifacts/checksums.txt
```

- [ ] **Step 2: 校验 YAML 语法**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml', encoding='utf-8')); print('YAML OK')"
```
Expected: `YAML OK`。

- [ ] **Step 3: 提交**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): tag 触发打包 + GitHub Release workflow"
```

---

## Task 12: 文档更新(README + CHANGELOG)

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: README 加「打包与发版」章节**

在 `README.md` 的「许可证」章节前插入:

```markdown
## 打包与发版

本项目用 **Nuitka**(`--standalone`)打包为 Windows 可执行程序,产出免安装便携 zip。

### 本地打包

```bash
uv run --with nuitka --extra gui --extra invoice python scripts/build_exe.py build
# 产物:dist/FileToolbox-{version}-win64.zip
```

### 版本号管理

版本号唯一真相源:`pyproject.toml`。`__init__.py` 运行时经 `importlib.metadata` 读取。

```bash
# 查看当前版本
uv run --extra dev python scripts/bump_version.py current

# bump 版本(自动改 pyproject + 迁移 CHANGELOG + git commit + tag)
uv run --extra dev python scripts/bump_version.py bump patch
uv run --extra dev python scripts/bump_version.py bump minor
uv run --extra dev python scripts/bump_version.py bump --set 1.0.0

# 推送 tag 触发 GitHub Actions 发版
git push --tags
```

### 更新依赖

```bash
uv run --extra dev python scripts/update_deps.py check    # 检查可升级
uv run --extra dev python scripts/update_deps.py update   # 全量升级 uv.lock
uv run --extra dev python scripts/update_deps.py update PySide6  # 单包升级
```

### 一键发版

```bash
uv run --extra dev python scripts/release.py patch   # bump → build,提示推送
```

### GitHub Actions

推送 `v*` tag 后,`.github/workflows/release.yml` 自动在 Windows 上打包,创建 GitHub Release 并附带便携 zip + 校验和。
```

- [ ] **Step 2: CHANGELOG 记录本次工具**

在 `CHANGELOG.md` 的 `## [Unreleased]` 下追加(### Added 段):

```markdown
### Added
- 打包与发版工具链:
  - Nuitka `--standalone` 打包脚本(`scripts/build_exe.py`),产出 Windows 便携 exe + zip + 校验和。
  - 版本号管理 `scripts/bump_version.py`(bump/current/validate,自动 git commit + tag),pyproject.toml 单一真相源。
  - 依赖更新 `scripts/update_deps.py`(uv lock 封装 + 升级摘要)。
  - 一键发版 `scripts/release.py`。
  - GitHub Actions `release.yml`:tag 触发自动打包 + 发版。
```

- [ ] **Step 3: 提交**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: README + CHANGELOG 打包与发版工具链"
```

---

## Task 13: 全量验证 + 首次真实发版演练

**Files:** 无(验证性 Task)

- [ ] **Step 1: 跑全部单测**

```bash
uv run --extra dev pytest -v
```
Expected: 全绿(含新增的 test_bump_version / test_version_source / test_update_deps)。

- [ ] **Step 2: lint 检查**

```bash
uv run --extra dev ruff check scripts/ file_toolbox/ tests/
```
Expected: 无错误(有则修复)。

- [ ] **Step 3: validate 命令终检**

```bash
uv run --extra dev python scripts/bump_version.py validate
```
Expected: `✓ 0.1.0 有效`。

- [ ] **Step 4: 本地打包冒烟(确认 Nuitka 全流程通)**

```bash
uv run --with nuitka --extra gui --extra invoice python scripts/build_exe.py build
```
Expected: dist/ 下产物齐全,exe 能启动 GUI。

> 若暂不想真发版,到此为止。真实发版时执行下一步。

- [ ] **Step 5(可选): 首次真实发版**

```bash
# bump 到 0.2.0(自动 commit + tag)
uv run --extra dev python scripts/bump_version.py bump minor
# 推送 tag 触发 CI(GitHub 远程配好后)
git push --tags
```

- [ ] **Step 6: 提交(若有 lint 修复)**

```bash
git add -A
git commit -m "chore: 打包发版工具链收尾"
```

---

## 自查清单(Plan 作者)

**Spec 覆盖:**
- ✅ §2 Nuitka standalone → Task 8
- ✅ §3 版本真相源(importlib.metadata)→ Task 1
- ✅ §4.1 bump_version(bump/current/validate + git 自动化)→ Task 3,4,5,6
- ✅ §4.2 build_exe → Task 8
- ✅ §4.3 update_deps → Task 7
- ✅ §4.4 release.py → Task 9
- ✅ §4.5 release.yml → Task 11
- ✅ §7 测试策略(单测覆盖纯逻辑 + 冒烟)→ Task 3-5,7,10
- ✅ §8 文档 → Task 12

**类型一致性:** `bump_version.py` 的 `bump_version()` / `validate_pep440()` / `migrate_changelog()` / `read_pyproject_version()` / `write_pyproject_version()` / `git_commit_and_tag()` 在 Task 3-6 定义,Task 9 release.py 通过 `_run("bump_version.py", ...)` 调用,签名一致。`parse_lock_versions` / `diff_upgrades` 在 Task 7 定义并自用。✅

**占位符扫描:** 无 TBD/TODO,所有代码块完整。✅

**风险点(实现者注意):**
- Task 6 的 `bump` 命令是真实发版动作(改文件 + commit + tag),**只在 dry-run 模式或首次真实发版时执行**,日常开发不要误跑。
- Task 8 Nuitka 首次编译慢 + 需联网下 MinGW64;CI 同理。
- `test_version_source.py` 用正则检测 `__init__.py` 硬编码,执行 `import Path` 需在文件顶部 import(已在测试代码补 `from pathlib import Path`)。
