"""Nuitka 打包:standalone 产出 exe 目录 + 便携 zip。

本地运行:
    uv run --extra gui --extra invoice --extra dev python scripts/build_exe.py [--ci]

打包策略(Nuitka standalone,onedir 等价形态;Velopack 需要目录布局):
  - PySide6:官方插件(--enable-plugin=pyside6)处理 Qt 插件/资源。
  - pywin32:win32com 动态 Dispatch 运行期按 ProgID 解析,静态分析追不全 →
    整包收;pythoncom/pywintypes 是带 DLL 的顶层模块,显式 --include-module 收,
    standalone DLL 扫描据此把 pywin32_system32 的 pythoncom3XX.dll、
    pywintypes3XX.dll 收进产物。这是旧 Nuitka 方案"批量转 PDF 缺依赖"bug 的
    根治点(当时缺手工收这两个 DLL),回归契约见 tests/test_build_exe_nuitka.py。
  - pypdfium2:PDFium 原生 DLL 在包数据里,--include-package-data 收运行时,
    --include-distribution-metadata 同步许可证(发布物必须随二进制分发)。
  - velopack:自更新原生绑定 DLL 在包数据里。
  - CHANGELOG.md 随包:--include-data-files 放 exe 同级,供关于页
    metadata.get_changelog() 回退链第 2 级命中。

CI 复用同一脚本(带 --ci);--assume-yes-for-downloads 允许 Nuitka 在无交互
环境自动下载 ccache/依赖分析工具。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
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
_ENTRY = _ROOT / "file_toolbox" / "gui_entry.py"
_PRODUCT = "FileToolbox"
_REPOSITORY = "FelixJI/file-toolbox"
_VPK_VERSION = "1.2.0"

cli = typer.Typer(add_completion=False, help="file-toolbox Nuitka 打包")


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
    identity = {
        "schema_version": 2,
        "project": {
            "component": "file-toolbox",
            "repository": _REPOSITORY,
            "version": version,
            "source_sha": source_sha,
        },
        "build": {
            "source_sha": source_sha,
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


def _latest_release_tag() -> str | None:
    """返回最新正式 Release 的 tag;仓库尚无 Release 时返回 None。"""

    result = subprocess.run(
        ["gh", "api", f"repos/{_REPOSITORY}/releases/latest"],
        cwd=str(_ROOT),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode == 0:
        return str(json.loads(result.stdout)["tag_name"])
    if "Not Found" in result.stderr:
        return None
    raise RuntimeError(
        f"查询 {_REPOSITORY} 最新 Release 失败(exit {result.returncode}): {result.stderr.strip()}"
    )


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.lstrip("v").split("."))


def _previous_full_nupkg(output_dir: Path, version: str) -> Path | None:
    """把上一正式版本的 full.nupkg 下载到 vpk 输出目录,作为差量基线。

    无任何正式 Release(首版引导)或最新版本不低于当前版本(本地重建已发布
    版本)时返回 None,安全降级为仅 full;Release 存在但下载失败时 fail closed。
    """

    tag = _latest_release_tag()
    if tag is None:
        return None
    previous = tag.lstrip("v")
    try:
        previous_tuple = _version_tuple(previous)
    except ValueError:
        previous_tuple = ()
    if len(previous_tuple) != 3:
        raise RuntimeError(f"最新 Release tag 不是稳定语义版本: {tag!r}")
    if previous_tuple >= _version_tuple(version):
        return None
    target = output_dir / f"{_PRODUCT}-{previous}-full.nupkg"
    result = subprocess.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "-R",
            _REPOSITORY,
            "-p",
            f"{_PRODUCT}-{previous}-full.nupkg",
            "-O",
            str(target),
        ],
        cwd=str(_ROOT),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(f"下载 {previous} full.nupkg 作为差量基线失败: {result.stderr.strip()}")
    return target


def _velopack_command(dotnet: str, product_dir: Path, version: str, output_dir: Path) -> list[str]:
    """构造 vpk 打包命令(独立纯函数,供契约测试锁定 --delta 差量旗标)。"""
    return [
        dotnet,
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
        "1",
        "--noInst",
        "--packTitle",
        _PRODUCT,
        "--yes",
        "--skip-updates",
        "true",
    ]


def _run_velopack(product_dir: Path, version: str, output_dir: Path) -> list[Path]:
    """用固定 vpk 打包,并只物化声明的正式资产(有差量基线时含 delta)。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = _previous_full_nupkg(output_dir, version)
    subprocess.run(
        _velopack_command(_dotnet_executable(), product_dir, version, output_dir),
        cwd=str(_ROOT),
        check=True,
    )
    sources: dict[str, tuple[str, ...]] = {
        f"{_PRODUCT}-{version}-full.nupkg": (f"{_PRODUCT}-{version}-full.nupkg",),
        f"{_PRODUCT}-v{version}-win-x64.zip": (
            f"{_PRODUCT}-Portable.zip",
            f"{_PRODUCT}-win-Portable.zip",
        ),
        "releases.win.json": ("releases.win.json",),
    }
    if baseline is not None:
        sources[f"{_PRODUCT}-{version}-delta.nupkg"] = (f"{_PRODUCT}-{version}-delta.nupkg",)
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


def _nuitka_command(entry: Path, version: str, output_dir: Path) -> list[str]:
    """构造 Nuitka standalone 编译命令(独立纯函数,供契约测试锁定关键旗标)。"""
    return [
        sys.executable,
        "-m",
        "nuitka",
        # standalone = onedir 等价形态:exe + 依赖目录(Velopack 打包需要目录布局)
        "--standalone",
        # CI 无交互环境:允许自动下载 ccache/依赖分析工具(本地同样适用)
        "--assume-yes-for-downloads",
        # GUI 无黑框(等价旧 spec 的 console=False)
        "--windows-console-mode=disable",
        "--enable-plugin=pyside6",
        # pywin32:win32com 动态 Dispatch 按 ProgID 运行期解析,静态追不全 → 整包收;
        # pythoncom/pywintypes 是带 DLL 的顶层模块,standalone DLL 扫描据此收
        # pywin32_system32 下的 pythoncom3XX.dll / pywintypes3XX.dll
        "--include-package=win32com",
        "--include-package=win32comext",
        "--include-package=win32",
        "--include-module=pythoncom",
        "--include-module=pywintypes",
        # pypdfium2:PDFium 原生 DLL(包数据)+ dist-info 许可证
        "--include-package-data=pypdfium2",
        "--include-distribution-metadata=pypdfium2",
        # velopack:自更新原生绑定 DLL(包数据)
        "--include-package=velopack",
        "--include-package-data=velopack",
        # CHANGELOG 随包:exe 同级,关于页 get_changelog() 回退链第 2 级
        f"--include-data-files={_ROOT / 'CHANGELOG.md'}=CHANGELOG.md",
        f"--output-dir={output_dir}",
        f"--output-filename={_PRODUCT}.exe",
        # Windows 版本资源(资源管理器/更新器"关于"显示)
        f"--product-name={_PRODUCT}",
        f"--product-version={version}",
        f"--file-version={version}",
        "--file-description=批量文件工具箱",
        str(entry),
    ]


@cli.command()
def build(
    ci: bool = typer.Option(False, "--ci", help="CI 模式:非交互,结构化输出"),
) -> None:
    """Nuitka 打包 → Velopack 发布物 → 生成 checksums。"""
    version = _current_version()
    typer.echo(f"打包版本: {version}")

    if not _ENTRY.exists():
        typer.secho(f"✗ 未找到入口脚本: {_ENTRY}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # 清理旧产物（仅仓库声明的 build/dist 输出目录）
    for d in (_DIST, _BUILD):
        if d.exists():
            shutil.rmtree(d)
    _DIST.mkdir(parents=True)

    nuitka_out = _BUILD / "nuitka"
    typer.echo("运行 Nuitka ...")
    subprocess.run(_nuitka_command(_ENTRY, version, nuitka_out), cwd=str(_ROOT), check=True)

    # Nuitka standalone 产物 = <output-dir>/gui_entry.dist/(以入口脚本 stem 命名);
    # 规整为 FileToolbox/ 以保持 vpk --mainExe 与便携 zip 布局不变
    product_dir = nuitka_out / "gui_entry.dist"
    if not product_dir.exists():
        typer.secho(f"✗ 未找到产物目录: {product_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    target_dir = nuitka_out / _PRODUCT
    product_dir.rename(target_dir)
    product_dir = target_dir

    exe = product_dir / f"{_PRODUCT}.exe"
    if not exe.exists():
        typer.secho(f"✗ 未找到产物 exe: {exe}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.secho(f"✓ exe: {exe}", fg=typer.colors.GREEN)

    typer.echo("运行 Velopack vpk ...")
    payloads = _run_velopack(product_dir, version, _BUILD / "velopack")

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
            fh.write(f"version={version}\n")
        typer.echo(f"CI 输出写入 {gh_output}")

    typer.echo("\n打包完成。产物在 dist/。")


if __name__ == "__main__":
    cli()
