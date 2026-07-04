"""PyInstaller 打包:onedir 产出 exe 目录 + 便携 zip。

本地运行:
    uv run --extra gui --extra invoice --extra dev python scripts/build_exe.py [--ci]

打包策略(详见 scripts/FileToolbox.spec):
  - 用 .spec 文件配置,C 扩展/运行时 DLL 全由 PyInstaller hook + collect_all 自动收集。
  - 关键差异(对比旧 Nuitka 方案):pywin32 的 pywin32_system32/ DLL、PyMuPDF 的
    原生绑定、Pillow 的 _imaging.pyd 全部自动进产物,无需手工 copytree —— 这正是
    旧 Nuitka 方案"批量转 PDF 缺少依赖"bug 的根治点。

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

# CI(如 GitHub Actions windows-latest,英文区域)控制台默认 cp1252,
# 无法编码脚本里的中文/✓/✗ 字符 → typer.echo 抛 UnicodeEncodeError。
# 把标准流重配为 UTF-8,使脚本不依赖控制台代码页(reconfigure 原地生效,
# Click 缓存的 sys.stdout 引用同样受益)。Python 3.7+。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
_DIST = _ROOT / "dist"
_BUILD = _ROOT / "build"
_SPEC = _ROOT / "scripts" / "FileToolbox.spec"
_PRODUCT = "FileToolbox"

cli = typer.Typer(add_completion=False, help="file-toolbox PyInstaller 打包")


def _current_version() -> str:
    # 复用 bump_version 的 pyproject 读取,保持单一真相源
    sys.path.insert(0, str(_ROOT / "scripts"))
    from bump_version import read_pyproject_version  # type: ignore[import-not-found]

    return read_pyproject_version(_ROOT / "pyproject.toml")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@cli.command()
def build(
    ci: bool = typer.Option(False, "--ci", help="CI 模式:非交互,结构化输出"),
) -> None:
    """PyInstaller 打包 → 压缩便携 zip → 生成 checksums。"""
    version = _current_version()
    typer.echo(f"打包版本: {version}")

    if not _SPEC.exists():
        typer.secho(f"✗ 未找到 spec 文件: {_SPEC}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # 清理旧产物
    for d in (_DIST, _BUILD):
        if d.exists():
            shutil.rmtree(d)
    _DIST.mkdir(parents=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(_SPEC),
        f"--distpath={_DIST}",
        f"--workpath={_BUILD}",
        "--noconfirm",  # 覆盖已有产物,CI 非交互必需
    ]
    typer.echo("运行 PyInstaller ...")
    subprocess.run(cmd, cwd=str(_ROOT), check=True)

    # PyInstaller onedir 产物 = dist/FileToolbox/(由 spec 的 COLLECT.name 决定)
    product_dir = _DIST / _PRODUCT
    if not product_dir.exists():
        typer.secho(f"✗ 未找到产物目录: {product_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    exe = product_dir / f"{_PRODUCT}.exe"
    if not exe.exists():
        typer.secho(f"✗ 未找到产物 exe: {exe}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.secho(f"✓ exe: {exe}", fg=typer.colors.GREEN)

    # 便携 zip:以 FileToolbox/ 为顶层目录打包,解压即用
    zip_name = f"{_PRODUCT}-{version}-win64.zip"
    zip_path = _DIST / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in product_dir.rglob("*"):
            if f.is_file():
                # 相对 product_dir(而非 product_dir.parent),使 zip 顶层是 FileToolbox/
                zf.write(f, f.relative_to(product_dir.parent))
    typer.secho(f"✓ zip: {zip_path}", fg=typer.colors.GREEN)

    # checksums
    checksums = _DIST / "checksums.txt"
    lines = [f"{_sha256(zip_path)}  {zip_name}"]
    checksums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    typer.secho(f"✓ checksums: {checksums}", fg=typer.colors.GREEN)

    if ci:
        # GitHub Actions 结构化输出(用 $GITHUB_OUTPUT,非已废弃的 ::set-output)
        gh_output = Path(_DIST / "_gha_output.txt")
        with gh_output.open("a", encoding="utf-8") as fh:
            fh.write(f"zip={zip_name}\n")
            fh.write(f"version={version}\n")
        typer.echo(f"CI 输出写入 {gh_output}")

    typer.echo("\n打包完成。产物在 dist/。")


if __name__ == "__main__":
    cli()
