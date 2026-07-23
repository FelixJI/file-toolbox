"""版本号管理:bump / current / validate。

单一真相源:pyproject.toml [project] version。
运行方式:uv run --extra dev python scripts/bump_version.py <command>
"""

from __future__ import annotations

import re
from pathlib import Path

from packaging.version import InvalidVersion, Version

PARTS = ("major", "minor", "patch", "prerelease")

_VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


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


_UNRELEASED_HEADER = "## [Unreleased]"
_NEXT_HEADER_RE = re.compile(r"\n## ")


def migrate_changelog(content: str, new_version: str, date: str) -> str:
    """把 [Unreleased] 段的条目迁移到新版本段下,并重开空 Unreleased。

    迁移后结构:
        ...(标题行 # Changelog 等)

        ## [Unreleased]

        ## <new_version> - <date>
        ...(原 Unreleased 的条目)

        ## <older versions...>
    """
    if _UNRELEASED_HEADER not in content:
        raise ValueError("CHANGELOG.md 缺少 '## [Unreleased]' 段")

    unreleased_idx = content.index(_UNRELEASED_HEADER)
    # Unreleased 标题之后的内容
    after_unreleased = content[unreleased_idx + len(_UNRELEASED_HEADER):]
    # 下一个 "## " 标题之前 = Unreleased 条目体
    next_header_match = _NEXT_HEADER_RE.search(after_unreleased)
    if next_header_match:
        unreleased_body = after_unreleased[: next_header_match.start()]
        rest = after_unreleased[next_header_match.start():]  # 含前导 "\n## "
    else:
        unreleased_body = after_unreleased
        rest = ""

    # 新版本段:标题 + 空行 + 条目体(strip 去掉首尾多余空行)
    body = unreleased_body.strip()
    new_section = f"## {new_version} - {date}\n"
    if body:
        new_section += f"\n{body}\n"
    # 保留 content 中 Unreleased 标题之前的全部内容,然后接空 Unreleased + 新版本段 + 旧版本
    rebuilt = (
        content[:unreleased_idx]
        + f"{_UNRELEASED_HEADER}\n\n"
        + new_section
        + ("\n" + rest.lstrip("\n") if rest.strip() else "")
    )
    return rebuilt


def read_pyproject_version(path: Path) -> str:
    """从 pyproject.toml 读 [project] version。"""
    text = path.read_text(encoding="utf-8")
    m = _VERSION_LINE.search(text)
    if not m:
        raise ValueError(f'{path} 中未找到 version = "..." 行')
    return m.group(1)


def write_pyproject_version(path: Path, new_version: str) -> None:
    """把新版本写回 pyproject.toml,只替换 version 行,保留其余内容。"""
    if not validate_pep440(new_version):
        raise ValueError(f"新版本不符合 PEP 440: {new_version!r}")
    text = path.read_text(encoding="utf-8")
    new_text, n = _VERSION_LINE.subn(f'version = "{new_version}"', text, count=1)
    if n == 0:
        raise ValueError(f'{path} 中未找到 version = "..." 行')
    path.write_text(new_text, encoding="utf-8")


# ---------------------------------------------------------------------------
# git 自动化
# ---------------------------------------------------------------------------

import subprocess  # noqa: E402


class GitError(RuntimeError):
    """git 操作失败。"""


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
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


def update_uv_lock_version(root: Path, new_version: str) -> None:
    """把 uv.lock 里 file-toolbox 段的 version 行改成 new_version。

    本项目是 `source = { editable = "." }`,uv.lock 里 file-toolbox 只记版本号,
    没有 sdist/wheel 的 hash 绑定,依赖列表也不随自身版本变。所以改版本号时,
    精确替换 lockfile 中 file-toolbox 段的 version 行,与 `uv lock` 等价
    (v0.1.0→0.1.1 的真实 uv lock diff 已验证:仅 version 行变动)。

    好处:不依赖 uv 是否在 PATH(本地 .venv 直跑 python 发版时 uv 常不在子进程 PATH)。

    抛 ValueError:找不到 file-toolbox 段或其后的 version 行(lockfile 结构异常)。
    """
    lock = root / "uv.lock"
    text = lock.read_text(encoding="utf-8")
    # 锁定 file-toolbox 段:其 `version = "..."` 紧跟 name 行之后。
    # (?m) 多行;(?s) 让 .* 跨行;非贪婪 + 仅匹配紧跟的 version 行,不误伤其他包。
    pattern = re.compile(
        r'(\[\[package\]\]\s*\nname = "file-toolbox"\s*\nversion = )"([^"]*)"',
        re.DOTALL,
    )
    new_text, n = pattern.subn(rf'\g<1>"{new_version}"', text, count=1)
    if n == 0:
        raise ValueError("uv.lock 中未找到 file-toolbox 段的 version 行")
    lock.write_text(new_text, encoding="utf-8")


# ---------------------------------------------------------------------------
# typer CLI
# ---------------------------------------------------------------------------

import datetime as _dt  # noqa: E402

import typer  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_PYPROJECT = _ROOT / "pyproject.toml"
_CHANGELOG = _ROOT / "CHANGELOG.md"

cli = typer.Typer(add_completion=False, help="file-toolbox 版本号管理")


@cli.command()
def current() -> None:
    """打印当前版本号(来自 pyproject.toml)。"""
    typer.echo(read_pyproject_version(_PYPROJECT))


@cli.command()
def validate() -> None:
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
    no_update_lock: bool = typer.Option(
        False, "--no-update-lock", help="跳过 uv lock(离线/无 uv 时)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="预览,不写盘不动 git"),
) -> None:
    """bump 版本号 + 改 pyproject + 同步 uv.lock + 迁移 CHANGELOG + git commit + tag。"""
    if not part and not set_version:
        typer.secho("错误:需要 <part> 或 --set", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if part and set_version:
        typer.secho("错误:<part> 与 --set 互斥", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    current_ver = read_pyproject_version(_PYPROJECT)
    new_ver = set_version if set_version else bump_version(current_ver, part)  # type: ignore[arg-type]
    if not validate_pep440(new_ver):
        typer.secho(f"✗ 新版本 {new_ver} 不符合 PEP 440", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    date = _dt.date.today().isoformat()

    if dry_run:
        typer.echo(f"[dry-run] {current_ver} → {new_ver} ({date})")
        typer.echo("[dry-run] 将同步 uv.lock、迁移 CHANGELOG,commit + tag")
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

    # 同步 uv.lock(文本替换 file-toolbox 段 version 行,与 uv lock 等价且不依赖 PATH)
    if not no_update_lock:
        try:
            update_uv_lock_version(_ROOT, new_ver)
            typer.secho("✓ uv.lock: 已同步", fg=typer.colors.GREEN)
        except (ValueError, OSError) as e:
            # lockfile 结构异常或读写失败:作为硬错误中止,避免发版后 lock 滞后
            typer.secho(f"✗ 同步 uv.lock 失败: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from e

    # 迁移 CHANGELOG
    cl_text = _CHANGELOG.read_text(encoding="utf-8")
    new_cl = migrate_changelog(cl_text, new_ver, date)
    _CHANGELOG.write_text(new_cl, encoding="utf-8")
    typer.secho(f"✓ CHANGELOG.md: 新增 {new_ver} 段", fg=typer.colors.GREEN)

    # git commit + tag
    files = ["pyproject.toml", "CHANGELOG.md"]
    if not no_update_lock:
        files.append("uv.lock")
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
