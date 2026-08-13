"""PyInstaller 打包:onedir 产出 exe 目录 + 便携 zip。

本地运行:
    uv run --extra gui --extra invoice --extra dev python scripts/build_exe.py [--ci]

打包策略(详见 scripts/FileToolbox.spec):
  - 用 .spec 文件配置,C 扩展/运行时 DLL 全由 PyInstaller hook + collect_all 自动收集。
  - 关键差异(对比旧 Nuitka 方案):pywin32 的 pywin32_system32/ DLL、pypdfium2 的
    PDFium 运行时、Pillow 的 _imaging.pyd 全部自动进产物,无需手工 copytree —— 这正是
    旧 Nuitka 方案"批量转 PDF 缺少依赖"bug 的根治点。

CI 复用同一脚本(带 --ci)。
"""

from __future__ import annotations

import hashlib
import json
import os
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

_ROOT = Path(
    os.environ.get("AUTOMATION_PROJECT_ROOT", Path(__file__).resolve().parents[1])
).resolve()
# canonical CI 通过绝对 AUTOMATION_ARTIFACTS_DIR 隔离构建输出；本地默认仍为仓库 dist/。
_DIST = Path(os.environ.get("AUTOMATION_ARTIFACTS_DIR", _ROOT / "dist")).resolve()
_BUILD = _ROOT / "build"
_SPEC = _ROOT / "scripts" / "FileToolbox.spec"
_PRODUCT = "FileToolbox"
_VPK_VERSION = "1.2.0"

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


def _asset_records(paths: list[Path]) -> dict[str, dict[str, int | str]]:
    return {
        path.name: {"sha256": _sha256(path), "size": path.stat().st_size}
        for path in sorted(paths, key=lambda item: item.name)
    }


def _write_build_identity(version: str, payloads: list[Path]) -> None:
    """写入项目构建身份；候选 manifest 由公共 core 负责生成。"""
    source_sha = os.environ.get("AUTOMATION_SOURCE_SHA", "local")
    legacy_archive = next(path for path in payloads if path.name.endswith("-win64.zip"))
    identity = {
        "schema_version": 2,
        "project": {
            "component": "file-toolbox",
            "repository": "FelixJI/file-toolbox",
            "version": version,
            "source_sha": source_sha,
        },
        "build": {
            "source_sha": source_sha,
            # 兼容现有候选消费者；schema 2 的 assets 是新的 exact-set 权威字段。
            "archive": legacy_archive.name,
            "archive_sha256": _sha256(legacy_archive),
            "assets": _asset_records(payloads),
        },
    }
    (_DIST / "build-identity.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_spdx_sbom(version: str, payloads: list[Path]) -> None:
    """写入稳定文件名、精确绑定全部发布 payload 的 SPDX 2.3 清单。"""
    records = _asset_records(payloads)
    namespace_digest = hashlib.sha256(
        "\n".join(f"{name}:{record['sha256']}" for name, record in records.items()).encode()
    ).hexdigest()
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"file-toolbox-{version}-build",
        "documentNamespace": (
            f"https://github.com/FelixJI/file-toolbox/releases/v{version}/sbom-{namespace_digest}"
        ),
        "creationInfo": {
            "created": "1980-01-01T00:00:00Z",
            "creators": ["Tool: scripts/build_exe.py"],
        },
        "packages": [
            {
                "SPDXID": "SPDXRef-Package",
                "name": "file-toolbox",
                "versionInfo": version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": True,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
            }
        ],
        "files": [
            {
                "SPDXID": f"SPDXRef-File-{index}",
                "fileName": name,
                "checksums": [{"algorithm": "SHA256", "checksumValue": record["sha256"]}],
            }
            for index, (name, record) in enumerate(records.items())
        ],
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": "SPDXRef-Package",
            },
            *[
                {
                    "spdxElementId": "SPDXRef-Package",
                    "relationshipType": "CONTAINS",
                    "relatedSpdxElement": f"SPDXRef-File-{index}",
                }
                for index in range(len(records))
            ],
        ],
    }
    (_DIST / "SBOM.spdx.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _dotnet_executable() -> str:
    """优先选择 Windows x64 dotnet，避免 PATH 中 x86 host 没有 SDK。"""

    if sys.platform == "win32":
        program_files = os.environ.get("PROGRAMW6432", r"C:\Program Files")
        x64_dotnet = Path(program_files) / "dotnet" / "dotnet.exe"
        if x64_dotnet.is_file():
            return str(x64_dotnet)
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise RuntimeError("未找到 .NET 8+ SDK，无法运行固定版本 vpk")
    return dotnet


def _run_velopack(product_dir: Path, version: str, output_dir: Path) -> list[Path]:
    """用固定 vpk 打包，并只物化声明的正式资产。"""

    cmd = [
        _dotnet_executable(),
        "dnx",
        f"vpk@{_VPK_VERSION}",
        "--",
        "pack",
        "--packId",
        _PRODUCT,
        "--packVersion",
        version,
        "--packDir",
        str(product_dir),
        "--mainExe",
        f"{_PRODUCT}.exe",
        "--outputDir",
        str(output_dir),
        "--channel",
        "win",
        "--delta",
        "None",
        "--packTitle",
        _PRODUCT,
        "--yes",
        "--skip-updates",
        "true",
    ]
    subprocess.run(cmd, cwd=str(_ROOT), check=True)
    sources = {
        f"{_PRODUCT}-{version}-full.nupkg": (f"{_PRODUCT}-{version}-full.nupkg",),
        f"{_PRODUCT}-Setup.exe": (
            f"{_PRODUCT}-Setup.exe",
            f"{_PRODUCT}-win-Setup.exe",
        ),
        f"{_PRODUCT}-Portable.zip": (
            f"{_PRODUCT}-Portable.zip",
            f"{_PRODUCT}-win-Portable.zip",
        ),
        "releases.win.json": ("releases.win.json",),
    }
    copied: list[Path] = []
    for target_name, source_names in sources.items():
        source = next(
            (output_dir / name for name in source_names if (output_dir / name).is_file()),
            None,
        )
        if source is None:
            raise RuntimeError(f"vpk 未生成声明资产: {source_names!r}")
        target = _DIST / target_name
        shutil.copy2(source, target)
        copied.append(target)
    return copied


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

    # 清理旧产物（仅仓库声明的 build/dist 输出目录）
    for d in (_DIST, _BUILD):
        if d.exists():
            shutil.rmtree(d)
    _DIST.mkdir(parents=True)

    pyinstaller_dist = _BUILD / "pyinstaller-dist"
    pyinstaller_work = _BUILD / "pyinstaller-work"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(_SPEC),
        f"--distpath={pyinstaller_dist}",
        f"--workpath={pyinstaller_work}",
        "--noconfirm",  # 覆盖已有产物,CI 非交互必需
    ]
    typer.echo("运行 PyInstaller ...")
    subprocess.run(cmd, cwd=str(_ROOT), check=True)

    # PyInstaller onedir 产物 = dist/FileToolbox/(由 spec 的 COLLECT.name 决定)
    product_dir = pyinstaller_dist / _PRODUCT
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

    typer.echo("运行 Velopack vpk ...")
    velopack_payloads = _run_velopack(product_dir, version, _BUILD / "velopack")
    payloads = [zip_path, *velopack_payloads]

    _write_build_identity(version, payloads)
    _write_spdx_sbom(version, payloads)

    # checksums
    checksums = _DIST / "checksums.txt"
    lines = [f"{_sha256(path)}  {path.name}" for path in sorted(payloads, key=lambda p: p.name)]
    checksums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    typer.secho(f"✓ checksums: {checksums}", fg=typer.colors.GREEN)

    if ci:
        # GitHub Actions 结构化输出(用 $GITHUB_OUTPUT,非已废弃的 ::set-output)
        gh_output = _BUILD / "_gha_output.txt"
        with gh_output.open("a", encoding="utf-8") as fh:
            fh.write(f"zip={zip_name}\n")
            fh.write(f"version={version}\n")
        typer.echo(f"CI 输出写入 {gh_output}")

    typer.echo("\n打包完成。产物在 dist/。")


if __name__ == "__main__":
    cli()
