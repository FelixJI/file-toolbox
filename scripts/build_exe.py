"""Nuitka 打包:--standalone 产出 exe 目录 + 便携 zip。

本地运行:
    uv run --with nuitka --extra gui --extra invoice python scripts/build_exe.py build [--ci]

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
    # 复用 bump_version 的 pyproject 读取,保持单一真相源
    sys.path.insert(0, str(_ROOT / "scripts"))
    from bump_version import read_pyproject_version  # type: ignore[import-not-found]

    return read_pyproject_version(_ROOT / "pyproject.toml")


def _build_command(output_dir: Path, version: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--mingw64",
        "--assume-yes-for-downloads",
        # Nuitka 官方 PySide6 插件:处理 Qt 插件/资源
        "--enable-plugin=pyside6",
        # 原生/懒加载依赖(静态分析易漏)
        "--include-package=fitz",  # PyMuPDF
        "--include-package=pdfplumber",  # invoice PDF 解析
        "--include-package=pdfminer",  # pdfplumber 依赖
        "--include-package=pdfminer.six",  # pdfminer 子模块
        "--include-package=openpyxl",  # Excel 导出
        "--include-package=chardet",  # 编码检测
        "--include-package-data=pdfplumber",  # pdfplumber 数据文件
        # GUI 应用无黑框(等价 PyInstaller --windowed)
        "--windows-disable-console",
        "--remove-output",  # 编译后清理中间文件
        f"--output-dir={output_dir}",
        f"--output-filename={_PRODUCT}.exe",
        # Windows 版本信息元数据(嵌入 exe 属性)
        "--company-name=FileToolbox",
        f"--product-name={_PRODUCT}",
        f"--file-version={version}",
        f"--product-version={version}",
        "--file-description=File Toolbox",
        str(_ENTRY),
    ]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@cli.command()
def build(
    ci: bool = typer.Option(False, "--ci", help="CI 模式:非交互,结构化输出"),
) -> None:
    """Nuitka 编译 → 压缩便携 zip → 生成 checksums。"""
    version = _current_version()
    typer.echo(f"打包版本: {version}")

    # 清理旧产物
    if _DIST.exists():
        shutil.rmtree(_DIST)
    _DIST.mkdir(parents=True)

    # Nuitka --output-dir 同时存放中间件(.build)和发行版(.dist)
    cmd = _build_command(_DIST, version)
    typer.echo("运行 Nuitka ...(首次编译会下载 MinGW64,需联网)")
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
        # GitHub Actions 结构化输出(用 $GITHUB_OUTPUT,非已废弃的 ::set-output)
        gh_output = Path(_DIST / "_gha_output.txt")
        with gh_output.open("a", encoding="utf-8") as fh:
            fh.write(f"zip={zip_name}\n")
            fh.write(f"version={version}\n")
        typer.echo(f"CI 输出写入 {gh_output}")

    typer.echo("\n打包完成。产物在 dist/。")


if __name__ == "__main__":
    cli()
