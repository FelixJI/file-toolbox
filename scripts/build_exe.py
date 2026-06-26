"""Nuitka 打包:--standalone 产出 exe 目录 + 便携 zip。

本地运行:
    uv run --with nuitka --extra gui --extra invoice python scripts/build_exe.py [--ci]

打包策略:
  - 项目源码(file_toolbox):Nuitka 默认编译为 C(保护业务逻辑)。
  - 纯 Python 第三方库(pdfplumber/openpyxl/pdfminer/chardet):复制 + 编译为字节码。
  - PyMuPDF(pymupdf/fitz):原生绑定体量巨大,编译会 OOM(Nuitka issue #3291)。
    用 --nofollow-import-to 跳过编译,再由 build() 手工 copytree 拷贝运行时
    (.pyd / .dll / .py)——Nuitka 的数据选项不会拷这些扩展文件。
  - PySide6:由官方 pyside6 插件处理。

CI 复用同一脚本(带 --ci)。
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
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


def _package_dir(package: str) -> Path:
    """定位某已安装包的目录(用 importlib 解析,兼容 uv 临时环境)。"""
    import importlib.util

    spec = importlib.util.find_spec(package)
    if spec is None or spec.origin is None:
        raise typer.Exit(f"✗ 找不到包 {package}(确认 --extra invoice 已安装 pymupdf)")
    return Path(spec.origin).parent


# PyMuPDF(pymupdf/fitz)编译为 C 会 OOM(Nuitka issue #3291),
# 且 --include-package-data / --include-data-dir 都不会拷贝其 .pyd/.dll/.py 运行时文件。
# 故:nofollow 阻止编译,由 build() 在打包后用 copytree 手工拷贝整个包目录。
_PYMUPDF_PACKAGES = ("pymupdf", "fitz")


def _build_command(output_dir: Path, version: str) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--mingw64",
        "--assume-yes-for-downloads",
        # Nuitka 官方 PySide6 插件:处理 Qt 插件/资源
        "--enable-plugin=pyside6",
        # --- 第三方纯 Python 库:复制 + 编译为字节码(快,无 OOM 风险)---
        "--include-package=pdfplumber",  # invoice PDF 解析
        "--include-package=pdfminer",  # pdfplumber 依赖(包名 pdfminer,非 pdfminer.six)
        "--include-package=openpyxl",  # Excel 导出
        "--include-package=chardet",  # 编码检测
        "--include-package-data=pdfplumber",  # pdfplumber 数据文件
        # --- PyMuPDF:nofollow 阻止编译(避免 OOM),运行时文件由 build() 手工拷贝 ---
        "--nofollow-import-to=pymupdf",
        "--nofollow-import-to=fitz",
        # GUI 应用无黑框(等价 PyInstaller --windowed)
        "--windows-console-mode=disable",
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
    return cmd


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

    # PyMuPDF 运行时手工拷贝(nofollow 后 Nuitka 不拷其 .pyd/.dll/.py)。
    for pkg in _PYMUPDF_PACKAGES:
        src = _package_dir(pkg)
        dst = candidate / pkg
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        # 删 __pycache__ 等无关文件,减小体积
        for cache in dst.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)
    typer.secho("✓ 拷贝 PyMuPDF 运行时(pymupdf/fitz)", fg=typer.colors.GREEN)

    product_dir = _DIST / _PRODUCT
    if product_dir.exists():
        shutil.rmtree(product_dir)
    # Windows 下 rename 常因杀软/句柄占用失败,用 shutil.move + 重试兜底
    for attempt in range(5):
        try:
            shutil.move(str(candidate), str(product_dir))
            break
        except OSError:
            if attempt == 4:
                raise
            time.sleep(1)

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
