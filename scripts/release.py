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
) -> None:
    """bump 版本 → build → 提示推送。"""
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
