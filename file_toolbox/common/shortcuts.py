"""跨平台快捷方式创建/删除:桌面 + 开始菜单。

纯逻辑、可单测。UI 只看 ShortcutResult 返回值,平台差异与外部交互全部内化。
所有外部调用(读注册表、COM、写文件)包在 try/except,永不向 UI 抛异常。
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "File Toolbox"  # 快捷方式显示名
LOCATION_DESKTOP = "desktop"
LOCATION_START_MENU = "start_menu"


@dataclass
class ShortcutResult:
    """快捷方式操作结果。UI 据此弹框。"""

    success: bool
    path: str  # 实际创建/删除的路径(失败时为空)
    location: str  # "desktop" / "start_menu"
    message: str  # 给用户看的中文提示


def _windows_desktop() -> Path:
    """Windows 真实桌面路径(规避 OneDrive 重定向)。

    直接用 ~/Desktop 会因 OneDrive 重定向失败,改读注册表 Shell Folders。
    """
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            desktop, _ = winreg.QueryValueEx(key, "Desktop")
            return Path(desktop)
    except OSError:
        return Path.home() / "Desktop"  # 回退


def _windows_start_menu() -> Path:
    """Windows 开始菜单用户目录(%AppData%/Microsoft/Windows/Start Menu/Programs)。"""
    return Path(os.environ.get("APPDATA", str(Path.home()))) / (
        "Microsoft/Windows/Start Menu/Programs"
    )


def _linux_desktop() -> Path:
    return Path.home() / "Desktop"


def _linux_start_menu() -> Path:
    # ~/.local/share/applications(XDG 用户应用目录)
    xdg_data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
    return Path(xdg_data) / "applications"


def desktop_dir() -> Path:
    """获取桌面目录(按平台)。"""
    if sys.platform == "win32":
        return _windows_desktop()
    return _linux_desktop()  # macOS 也走这里(桌面目录名同为 Desktop)


def start_menu_dir() -> Path:
    """获取开始菜单/应用启动目录(按平台)。"""
    if sys.platform == "win32":
        return _windows_start_menu()
    return _linux_start_menu()
