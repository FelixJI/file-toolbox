"""build_exe Nuitka 命令契约:锁定打包关键旗标,防回归。

背景:本项目曾用 Nuitka 因便携包缺 pywin32_system32 的 pythoncom/pywintypes
DLL("批量转 PDF 缺依赖"bug)换到 PyInstaller;切回 Nuitka 时把这些收包
决策固化为契约,任何旗标回退都会在此变红。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_exe  # noqa: E402


def _cmd() -> list[str]:
    return build_exe._nuitka_command(
        Path("file_toolbox/gui_entry.py"), "0.3.0", Path("build/nuitka")
    )


def test_command_uses_nuitka_standalone_without_console() -> None:
    cmd = _cmd()
    assert cmd[:3] == [sys.executable, "-m", "nuitka"]
    # standalone(onedir 等价,Velopack 需要目录布局)+ GUI 无黑框 + CI 无交互下载
    for flag in (
        "--standalone",
        "--assume-yes-for-downloads",
        "--windows-console-mode=disable",
        "--enable-plugin=pyside6",
    ):
        assert flag in cmd, f"缺少打包旗标: {flag}"


def test_command_includes_pywin32_runtime() -> None:
    """pywin32 全家收包:win32com 动态 Dispatch 追不全,pythoncom/pywintypes 带 DLL。

    缺 pythoncom/pywintypes 任一项 → 产物缺 pywin32_system32 DLL → COM 功能
    在便携包内崩溃(历史 bug 根源)。
    """
    cmd = _cmd()
    for flag in (
        "--include-package=win32com",
        "--include-package=win32comext",
        "--include-package=win32",
        "--include-module=pythoncom",
        "--include-module=pywintypes",
    ):
        assert flag in cmd, f"缺少 pywin32 收包旗标: {flag}"


def test_command_includes_native_package_data_and_licenses() -> None:
    """pypdfium2(PDFium DLL+许可证)与 velopack(自更新原生绑定)随包。"""
    cmd = _cmd()
    assert "--include-package-data=pypdfium2" in cmd
    assert "--include-distribution-metadata=pypdfium2" in cmd
    assert "--include-package=velopack" in cmd
    assert "--include-package-data=velopack" in cmd


def test_command_bundles_changelog_next_to_exe() -> None:
    """CHANGELOG.md 拷到 exe 同级(关于页 get_changelog() 回退链第 2 级)。"""
    cmd = _cmd()
    changelog_flags = [flag for flag in cmd if flag.startswith("--include-data-files=")]
    assert len(changelog_flags) == 1
    assert changelog_flags[0].endswith(f"{Path('CHANGELOG.md')}={Path('CHANGELOG.md')}")


def test_command_names_product_exe_and_version_resource() -> None:
    """产物 exe 名固定 FileToolbox.exe(vpk --mainExe 契约),版本资源随构建版本。"""
    cmd = _cmd()
    assert "--output-filename=FileToolbox.exe" in cmd
    assert "--product-name=FileToolbox" in cmd
    assert "--product-version=0.3.0" in cmd
    assert "--file-version=0.3.0" in cmd
    # 入口脚本在最后
    assert cmd[-1].endswith("gui_entry.py")
