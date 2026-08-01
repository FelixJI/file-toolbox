"""只读版本信息工具。

版本、Changelog、提交和标签均由 Release Please 管理。本脚本只保留构建与
诊断所需的版本读取/校验能力，避免本地命令绕过正式发布门禁。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import typer
from packaging.version import InvalidVersion, Version

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
_PYPROJECT = _ROOT / "pyproject.toml"
_VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)

cli = typer.Typer(add_completion=False, help="file-toolbox 只读版本信息")


def validate_pep440(version: str) -> bool:
    """校验字符串是否符合 PEP 440。"""
    try:
        Version(version)
        return True
    except InvalidVersion:
        return False


def read_pyproject_version(path: Path) -> str:
    """从 pyproject.toml 读取项目版本。"""
    match = _VERSION_LINE.search(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f'{path} 中未找到 version = "..." 行')
    return match.group(1)


@cli.command()
def current() -> None:
    """打印 pyproject.toml 中的当前版本。"""
    typer.echo(read_pyproject_version(_PYPROJECT))


@cli.command()
def validate() -> None:
    """校验版本符合 PEP 440，且 __init__.py 没有硬编码版本。"""
    version = read_pyproject_version(_PYPROJECT)
    if not validate_pep440(version):
        typer.secho(f"✗ {version} 不符合 PEP 440", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    init_source = (_ROOT / "file_toolbox" / "__init__.py").read_text(encoding="utf-8")
    if re.search(r'__version__\s*=\s*"\d+\.\d+\.\d+"', init_source):
        typer.secho("✗ __init__.py 仍硬编码 __version__", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.secho(f"✓ {version} 有效", fg=typer.colors.GREEN)


if __name__ == "__main__":
    cli()
