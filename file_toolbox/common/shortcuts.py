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
    非 Windows 上 winreg 不存在(ImportError),回退到 ~/Desktop。
    """
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            desktop, _ = winreg.QueryValueEx(key, "Desktop")
            return Path(desktop)
    except (ImportError, OSError):
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


def _gui_command() -> tuple[str, list[str]]:
    """启动 GUI 的命令:python 解释器 + -m file_toolbox gui。"""
    return (sys.executable, ["-m", "file_toolbox", "gui"])


def _create_windows_lnk(target_dir: Path, location: str) -> ShortcutResult:
    """Windows:用 WScript.Shell COM 创建 .lnk。目录不存在则创建。"""
    try:
        import win32com.client  # pywin32,Windows 已是依赖

        target_dir.mkdir(parents=True, exist_ok=True)
        exe, args = _gui_command()
        lnk_path = target_dir / f"{APP_NAME}.lnk"
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(lnk_path))
        shortcut.Targetpath = exe
        shortcut.Arguments = " ".join(args)
        shortcut.WorkingDirectory = str(Path.home())
        shortcut.Description = APP_NAME
        shortcut.Save()
        loc_name = "桌面" if location == LOCATION_DESKTOP else "开始菜单"
        return ShortcutResult(True, str(lnk_path), location, f"已创建{loc_name}快捷方式")
    except Exception as e:  # noqa: BLE001 — COM 失败不抛给 UI
        loc_name = "桌面" if location == LOCATION_DESKTOP else "开始菜单"
        return ShortcutResult(False, "", location, f"创建{loc_name}快捷方式失败: {e}")


def _create_linux_desktop_file(target_dir: Path, location: str) -> ShortcutResult:
    """Linux:创建 .desktop 文件。目录不存在则创建。"""
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        exe, args = _gui_command()
        desktop_path = target_dir / f"{APP_NAME}.desktop"
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_NAME}\n"
            f"Comment={APP_NAME}\n"
            f"Exec={exe} {' '.join(args)}\n"
            "Terminal=false\n"
        )
        desktop_path.write_text(content, encoding="utf-8")
        loc_name = "桌面" if location == LOCATION_DESKTOP else "开始菜单"
        return ShortcutResult(True, str(desktop_path), location, f"已创建{loc_name}快捷方式")
    except OSError as e:
        loc_name = "桌面" if location == LOCATION_DESKTOP else "开始菜单"
        return ShortcutResult(False, "", location, f"创建{loc_name}快捷方式失败: {e}")


def _create_macos_unsupported(location: str) -> ShortcutResult:
    loc_name = "桌面" if location == LOCATION_DESKTOP else "开始菜单"
    return ShortcutResult(
        False, "", location, f"macOS 暂不支持自动创建{loc_name}快捷方式,请手动添加"
    )


def _create_shortcut(location: str) -> ShortcutResult:
    """创建快捷方式的平台分发。"""
    if sys.platform == "darwin":
        return _create_macos_unsupported(location)
    target_dir = desktop_dir() if location == LOCATION_DESKTOP else start_menu_dir()
    if sys.platform == "win32":
        return _create_windows_lnk(target_dir, location)
    return _create_linux_desktop_file(target_dir, location)


def create_desktop_shortcut() -> ShortcutResult:
    """创建桌面快捷方式(已存在则覆盖,幂等)。"""
    return _create_shortcut(LOCATION_DESKTOP)


def create_start_menu_shortcut() -> ShortcutResult:
    """创建开始菜单快捷方式(已存在则覆盖,幂等)。"""
    return _create_shortcut(LOCATION_START_MENU)


def _shortcut_filename() -> str:
    """平台对应的快捷方式文件名(不含目录)。"""
    if sys.platform == "win32":
        return f"{APP_NAME}.lnk"
    return f"{APP_NAME}.desktop"  # macOS 也返回此名(但删除会因 macOS 创建失败而天然"未找到")


def _remove_shortcut(location: str) -> ShortcutResult:
    """删除快捷方式。不存在返回 success=False(不报错)。"""
    loc_name = "桌面" if location == LOCATION_DESKTOP else "开始菜单"
    target_dir = desktop_dir() if location == LOCATION_DESKTOP else start_menu_dir()
    path = target_dir / _shortcut_filename()
    if not path.exists():
        return ShortcutResult(False, "", location, f"未找到{loc_name}快捷方式(可能尚未创建)")
    try:
        path.unlink()
        return ShortcutResult(True, str(path), location, f"已删除{loc_name}快捷方式")
    except OSError as e:
        return ShortcutResult(False, "", location, f"删除{loc_name}快捷方式失败: {e}")


def remove_desktop_shortcut() -> ShortcutResult:
    """删除桌面快捷方式(不存在不报错,幂等)。"""
    return _remove_shortcut(LOCATION_DESKTOP)


def remove_start_menu_shortcut() -> ShortcutResult:
    """删除开始菜单快捷方式(不存在不报错,幂等)。"""
    return _remove_shortcut(LOCATION_START_MENU)
