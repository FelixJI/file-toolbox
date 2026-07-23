"""一键发版编排:bump → (可选 build) → 提示推送。

本地交互式(推荐,无参数运行):
    uv run --extra dev python scripts/release.py
    # 进入彩色向导:选版本类型 → 选是否打包 → 总览确认 → bump/build
    # 完成后提示手动 git push --tags 触发 CI

本地非交互:
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

# 复用 bump_version 的纯函数(版本计算/校验/工作区检查),保持单一真相源。
# 运行 `python scripts/release.py` 时 scripts/ 不在 sys.path,需显式注入。
sys.path.insert(0, str(_ROOT / "scripts"))
import bump_version as _bv  # noqa: E402

# 模块级别名:让编排函数通过这些名字引用,便于测试 monkeypatch 桩掉。
_compute_next = _bv.bump_version
validate_pep440 = _bv.validate_pep440
working_tree_clean = _bv.working_tree_clean
read_pyproject_version = _bv.read_pyproject_version

cli = typer.Typer(add_completion=False, help="file-toolbox 一键发版")


def _run(script: str, *args: str, check: bool = True) -> None:
    cmd = _PY + [str(_ROOT / "scripts" / script), *args]
    typer.echo(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(_ROOT), check=check)


def _git_output(*args: str, cwd: Path) -> str:
    """跑 git 命令,返回 stdout(strip)。失败(check=False)返回空串。"""
    res = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return res.stdout.strip()


def _git_branch(root: Path) -> str:
    """当前分支名。"""
    return _git_output("rev-parse", "--abbrev-ref", "HEAD", cwd=root)


def _unpushed_commits(root: Path) -> list[str]:
    """本地领先上游的提交(@{u}..HEAD)。无上游或查询失败 → 空列表(不报错)。"""
    out = _git_output("log", "@{u}..HEAD", "--oneline", cwd=root)
    return [line for line in out.splitlines() if line.strip()]


_CHOICES = {
    "1": "patch",
    "2": "minor",
    "3": "major",
    "4": "prerelease",
}


def _resolve_version_choice(choice: str, current: str) -> tuple[str, str] | None:
    """菜单数字 → (part, new_version)。选 5(自定义)→ ('__custom__', None)。非法 → None。"""
    if choice == "5":
        return ("__custom__", None)
    part = _CHOICES.get(choice)
    if part is None:
        return None
    return (part, _compute_next(current, part))


def _validate_custom_version(raw: str) -> str | None:
    """校验自定义版本号合规。合规返回原值,否则 None。"""
    raw = raw.strip()
    return raw if validate_pep440(raw) else None


@cli.command()
def release(
    part: str = typer.Argument(None, help="major/minor/patch/prerelease(与 --set 二选一)"),
    set_version: str = typer.Option(None, "--set", help="直接设到指定版本"),
    update_deps: bool = typer.Option(
        False, "--update-deps", help="发版前先跑 update_deps check"
    ),
    skip_build: bool = typer.Option(False, "--skip-build", help="只 bump,不打包"),
    ci: bool = typer.Option(False, "--ci", help="CI 模式:非交互"),
) -> None:
    """bump 版本 → build → 提示推送。"""
    if not part and not set_version and not ci:
        # 无参数运行 → 交互模式
        run_interactive()
        return
    if not part and not set_version:
        typer.secho("错误:需要 <part> 或 --set", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if update_deps and not ci:
        typer.echo("=== 检查依赖更新 ===")
        _run("update_deps.py", "check", check=False)

    # 1. bump(自动 commit + tag)
    typer.echo("=== bump 版本 ===")
    bump_args: list[str] = []
    if set_version:
        bump_args += ["--set", set_version]
    else:
        bump_args.append(part)  # type: ignore[arg-type]
    if ci:
        bump_args.append("--push")  # CI 里直接推送触发后续
    _run("bump_version.py", "bump", *bump_args)

    # 2. build(非 CI 且 skip-build 时跳过)
    if not skip_build:
        typer.echo("=== PyInstaller 打包 ===")
        build_args = ["--ci"] if ci else []
        _run("build_exe.py", *build_args)

    if not ci:
        typer.echo(
            "\n发版准备完成。下一步: git push --tags  (CI 会自动出 GitHub Release)"
        )
    typer.secho("✓ release 流程结束", fg=typer.colors.GREEN)


def _print_step0_abort(msg: str) -> None:
    typer.secho(f"✗ {msg}", fg=typer.colors.RED, err=True)


def run_interactive() -> None:
    """交互式发版向导(无参数运行 release.py 时进入)。

    Step 0 前置检查 → Step 1 选版本 → Step 2 选 build → Step 3 总览确认 → Step 4 执行。
    Ctrl+C 在交互阶段(Step 0-3,不写盘)友好退出;Step 4 已 commit 后不再拦截。
    """
    try:
        _run_interactive_inner()
    except KeyboardInterrupt:
        # 交互阶段取消:此时未启动任何子进程,无残留改动
        typer.secho("\n已取消(Ctrl+C),未做任何改动。", fg=typer.colors.YELLOW)
        raise typer.Exit(130) from None


def _run_interactive_inner() -> None:
    """run_interactive 的主体(被 try 包裹,便于统一拦 KeyboardInterrupt)。"""
    # ---- Step 0: 前置严格检查 ----
    if not working_tree_clean(_ROOT):
        _print_step0_abort("git 工作区不干净,请先 commit/stash 当前改动")
        raise typer.Exit(1)

    branch = _git_branch(_ROOT)
    if branch != "main":
        typer.secho(f"⚠ 当前分支非 main(在 {branch})", fg=typer.colors.YELLOW)
        if not typer.confirm("仍要在此分支发版?", default=False):
            typer.echo("已取消。")
            return

    unpushed = _unpushed_commits(_ROOT)
    if unpushed:
        typer.secho(f"⚠ 本地有 {len(unpushed)} 个未推送提交", fg=typer.colors.YELLOW)
        if not typer.confirm("仍要继续发版?", default=False):
            typer.echo("已取消。")
            return

    # ---- Step 1: 选版本类型 ----
    current_ver = read_pyproject_version(_ROOT / "pyproject.toml")
    while True:
        typer.secho(f"\nfile-toolbox 发版   当前 v{current_ver}", fg=typer.colors.CYAN)
        typer.echo("选择版本类型:")
        typer.echo(f"  [1] patch       → {_compute_next(current_ver, 'patch')}")
        typer.echo(f"  [2] minor       → {_compute_next(current_ver, 'minor')}")
        typer.echo(f"  [3] major       → {_compute_next(current_ver, 'major')}")
        typer.echo(f"  [4] prerelease  → {_compute_next(current_ver, 'prerelease')}")
        typer.echo("  [5] 自定义版本号 --set")
        choice = typer.prompt("> ", default="1")
        resolved = _resolve_version_choice(choice, current_ver)
        if resolved is None:
            typer.secho("无效选择,请输入 1-5", fg=typer.colors.RED)
            continue
        part, new_ver = resolved
        if part == "__custom__":
            while True:
                raw = typer.prompt("输入版本号(PEP 440)")
                ok = _validate_custom_version(raw)
                if ok:
                    new_ver = ok
                    part = None  # 自定义,走 --set
                    break
                typer.secho("版本号不合规(PEP 440),重试", fg=typer.colors.RED)
        break

    # ---- Step 2: 选附加动作(打包,不预选) ----
    do_build = typer.confirm("是否同步 PyInstaller 打包 build_exe?", default=False)

    # ---- Step 3: 总览确认 ----
    typer.echo("\n即将执行:")
    typer.echo(f"  • pyproject.toml: {current_ver} → {new_ver}")
    typer.echo("  • uv.lock: 同步 file-toolbox 版本号")
    typer.echo(f"  • CHANGELOG.md: 迁移 [Unreleased] 段到 {new_ver}")
    typer.echo(f"  • git commit + tag v{new_ver}")
    typer.echo(f"  • PyInstaller 打包   {'(将执行)' if do_build else '— 跳过 —'}")
    if not typer.confirm("\n确认执行?", default=False):
        typer.echo("已取消,未做任何改动。")
        return

    # ---- Step 4: 执行(bump + 可选 build,从不 push) ----
    _execute_release(part, new_ver, do_build)


def _execute_release(part: str | None, new_version: str, do_build: bool) -> None:
    """Step 4: 真正写盘 bump(+ 可选 build),从不自动 push。"""
    # 1. bump(commit + tag,经子进程,与非交互路径一致)
    typer.echo("=== bump 版本 ===")
    if part is None:
        _run("bump_version.py", "bump", "--set", new_version)
    else:
        _run("bump_version.py", "bump", part)

    # 2. 可选打包(本地,不带 --ci)
    if do_build:
        typer.echo("=== PyInstaller 打包 ===")
        _run("build_exe.py")

    # 3. 收尾:从不自动 push
    typer.secho(f"\n✓ 发版准备完成: v{new_version}", fg=typer.colors.GREEN)
    typer.echo(f"下一步: git push --tags  (触发 CI 出 GitHub Release v{new_version})")


if __name__ == "__main__":
    cli()
