"""依赖更新:封装 uv lock --upgrade,输出升级摘要。

运行方式:
  uv run scripts/update_deps.py            # 交互式菜单
  uv run scripts/update_deps.py check      # dry-run 检测可升级包
  uv run scripts/update_deps.py update     # 全量升级
  uv run scripts/update_deps.py update <pkg>  # 单包升级
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import typer

_ROOT = Path(__file__).resolve().parents[1]
_LOCK = _ROOT / "uv.lock"

# uv.lock 中每个 package 段:name = "x" 紧跟 version = "y"
_PACKAGE_RE = re.compile(r'name\s*=\s*"([^"]+)"\s*\nversion\s*=\s*"([^"]+)"')


def parse_lock_versions(lock_text: str) -> dict[str, str]:
    """从 uv.lock 文本解析 {包名: 版本}。"""
    return dict(_PACKAGE_RE.findall(lock_text))


def diff_upgrades(before: dict[str, str], after: dict[str, str]) -> dict[str, tuple[str, str]]:
    """对比前后版本,返回 {包名: (旧版, 新版)},只含版本变化的包。"""
    result: dict[str, tuple[str, str]] = {}
    for name, new_ver in after.items():
        old_ver = before.get(name)
        if old_ver is not None and old_ver != new_ver:
            result[name] = (old_ver, new_ver)
    return result


# ---------------------------------------------------------------------------
# typer CLI
# ---------------------------------------------------------------------------

cli = typer.Typer(add_completion=False, help="file-toolbox 依赖更新(uv lock 封装)")


def _read_lock() -> dict[str, str]:
    return parse_lock_versions(_LOCK.read_text(encoding="utf-8"))


def _print_summary(upgrades: dict[str, tuple[str, str]]) -> None:
    if not upgrades:
        typer.secho("无依赖升级。", fg=typer.colors.GREEN)
        return
    typer.echo("升级摘要:")
    for name, (old, new) in sorted(upgrades.items()):
        typer.echo(f"  {name:<20} {old} → {new}")
    typer.echo(f"共 {len(upgrades)} 个包升级。")
    typer.echo("提示: review uv.lock diff 后执行 git commit。")


# uv lock --dry-run 输出形如 "Updated <pkg> <old> -> <new>"
_DRYRUN_RE = re.compile(r"Updated\s+(\S+)\s+(\S+)\s*->\s*(\S+)")


def _parse_uv_dryrun(stdout: str) -> dict[str, tuple[str, str]]:
    """解析 uv lock --dry-run 的输出。uv 格式可能变,这里尽力解析。"""
    result: dict[str, tuple[str, str]] = {}
    for m in _DRYRUN_RE.finditer(stdout):
        name, old, new = m.group(1), m.group(2), m.group(3)
        result[name] = (old, new)
    return result


@cli.command()
def update(
    package: str = typer.Argument(None, help="只升级指定包(省略=全量升级)"),
) -> None:
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
def check() -> None:
    """dry-run 检测哪些包有新版(不改 lockfile)。"""
    proc = subprocess.run(
        ["uv", "lock", "--upgrade", "--dry-run"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    # uv lock --dry-run:exit code 0 表示无变化,非 0 表示有变化(或错误)
    changes = _parse_uv_dryrun(proc.stdout)
    if not changes:
        typer.secho("所有依赖已是最新。", fg=typer.colors.GREEN)
        return
    typer.echo("可升级:")
    for name, (old, new) in sorted(changes.items()):
        typer.echo(f"  {name:<20} {old} → {new}")
    typer.echo(f"\n共 {len(changes)} 个包可升级。运行 update-deps update 升级。")


# ---------------------------------------------------------------------------
# 交互式菜单(无子命令时调用)
# ---------------------------------------------------------------------------


def _interactive_menu() -> None:
    """无子命令时弹出菜单让用户选择操作。"""
    typer.echo("file-toolbox 依赖更新工具")
    typer.echo("请选择操作:")
    typer.echo("  1) check    - 检测哪些包有新版(不改 uv.lock)")
    typer.echo("  2) update   - 全量升级(修改 uv.lock)")
    typer.echo("  3) update <包名> - 只升级指定包")
    typer.echo("  q) 退出")
    try:
        choice = input("选择 [1]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        sys.exit(0)

    if choice in ("q", "quit", "exit"):
        sys.exit(0)
    if choice == "1":
        check()
    elif choice == "2":
        update()
    elif choice == "3":
        package = input("输入要升级的包名: ").strip()
        if not package:
            print("错误: 包名不能为空。")
            sys.exit(2)
        update(package)
    else:
        print(f"错误: 无效选择 {choice}")
        sys.exit(2)


if __name__ == "__main__":
    # 无子命令时进入交互式菜单
    if len(sys.argv) == 1:
        _interactive_menu()
    else:
        cli()
