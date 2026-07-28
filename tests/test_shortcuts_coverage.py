"""common/shortcuts 未覆盖分支补充测试。

覆盖行:
- 42-43: _windows_desktop winreg ImportError/OSError → 回退 ~/Desktop
- 54, 59-60, 67, 74: linux 分支(_linux_desktop/_linux_start_menu/desktop_dir/start_menu_dir)
- 99-101: _create_windows_lnk COM 失败
- 106-123: _create_linux_desktop_file(成功 + OSError)
- 127-128, 136: _create_macos_unsupported + darwin 分发
- 140: _create_shortcut linux 分发
- 157: _shortcut_filename linux
- 170-171: _remove_shortcut unlink OSError
"""

from pathlib import Path
from unittest.mock import MagicMock

from file_toolbox.common import shortcuts
from file_toolbox.common.shortcuts import (
    LOCATION_DESKTOP,
    LOCATION_START_MENU,
    ShortcutResult,
    _create_linux_desktop_file,
    _create_macos_unsupported,
    _create_shortcut,
    _create_windows_lnk,
    _gui_command,
    _linux_desktop,
    _linux_start_menu,
    _remove_shortcut,
    _shortcut_filename,
    _windows_desktop,
    _windows_start_menu,
    create_desktop_shortcut,
    create_start_menu_shortcut,
    desktop_dir,
    remove_desktop_shortcut,
    remove_start_menu_shortcut,
    start_menu_dir,
)

# ---------------------------------------------------------------------------
# _windows_desktop:winreg 失败回退(行 42-43)
# ---------------------------------------------------------------------------


def test_windows_desktop_winreg_oserror_falls_back(monkeypatch):
    """winreg.OpenKey 抛 OSError → 回退 ~/Desktop(行 42-43)。"""
    import sys

    fake_winreg = MagicMock()
    fake_winreg.HKEY_CURRENT_USER = 1
    fake_winreg.OpenKey = MagicMock(side_effect=OSError("no key"))
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    p = _windows_desktop()
    assert p == Path.home() / "Desktop"


def test_windows_desktop_winreg_importerror_falls_back(monkeypatch):
    """import winreg 抛 ImportError → 回退(行 42)。"""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "winreg":
            raise ImportError("no winreg")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    p = _windows_desktop()
    assert p == Path.home() / "Desktop"


def test_windows_desktop_registry_success(monkeypatch, tmp_path):
    """winreg 成功读 Desktop → 返回该路径。"""
    import sys

    fake_winreg = MagicMock()
    fake_winreg.HKEY_CURRENT_USER = 1
    fake_winreg.OpenKey.return_value.__enter__.return_value = MagicMock()
    fake_winreg.QueryValueEx.return_value = (str(tmp_path), 0)
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    assert _windows_desktop() == tmp_path


# ---------------------------------------------------------------------------
# _windows_start_menu(行 46-50)
# ---------------------------------------------------------------------------


def test_windows_start_menu_uses_appdata(monkeypatch):
    """%AppData% 存在 → 用它拼接。"""
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "C:/fake_appdata")
    p = _windows_start_menu()
    assert "fake_appdata" in str(p)
    assert "Start Menu/Programs" in str(p).replace("\\", "/")


def test_windows_start_menu_fallback_no_appdata(monkeypatch):
    """无 APPDATA → 用 home(行 48 默认值)。"""
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    p = _windows_start_menu()
    assert "Start Menu/Programs" in str(p).replace("\\", "/")


# ---------------------------------------------------------------------------
# linux 分支(行 54, 59-60, 67, 74)
# ---------------------------------------------------------------------------


def test_linux_desktop():
    assert _linux_desktop() == Path.home() / "Desktop"


def test_linux_start_menu_default():
    assert _linux_start_menu() == Path.home() / ".local/share/applications"


def test_linux_start_menu_xdg_env(monkeypatch):
    """XDG_DATA_HOME 存在 → 用它。"""
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/xdg")
    assert _linux_start_menu() == Path("/custom/xdg/applications")


def test_desktop_dir_linux(monkeypatch):
    monkeypatch.setattr(shortcuts.sys, "platform", "linux")
    assert desktop_dir() == Path.home() / "Desktop"


def test_start_menu_dir_linux(monkeypatch):
    monkeypatch.setattr(shortcuts.sys, "platform", "linux")
    assert start_menu_dir() == Path.home() / ".local/share/applications"


# ---------------------------------------------------------------------------
# _gui_command(行 77-79)
# ---------------------------------------------------------------------------


def test_gui_command():
    exe, args = _gui_command()
    assert isinstance(exe, str)
    assert "-m" in args and "file_toolbox" in args and "gui" in args


# ---------------------------------------------------------------------------
# _create_windows_lnk:COM 失败(行 99-101)
# ---------------------------------------------------------------------------


def test_create_windows_lnk_com_failure(tmp_path, monkeypatch):
    """Dispatch 抛异常 → 返回失败结果(行 99-101)。"""
    import sys

    fake_win32com = MagicMock()
    fake_win32com.client.Dispatch.side_effect = RuntimeError("COM boom")
    monkeypatch.setitem(sys.modules, "win32com", fake_win32com)
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    result = _create_windows_lnk(tmp_path, LOCATION_DESKTOP)
    assert result.success is False
    assert "COM boom" in result.message
    assert result.location == LOCATION_DESKTOP


def test_create_windows_lnk_start_menu_failure(tmp_path, monkeypatch):
    """COM 失败 + start_menu location → '开始菜单' 提示。"""
    import sys

    fake_win32com = MagicMock()
    fake_win32com.client.Dispatch.side_effect = RuntimeError("boom")
    monkeypatch.setitem(sys.modules, "win32com", fake_win32com)
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    result = _create_windows_lnk(tmp_path, LOCATION_START_MENU)
    assert result.success is False
    assert "开始菜单" in result.message


# ---------------------------------------------------------------------------
# _create_linux_desktop_file(行 106-123)
# ---------------------------------------------------------------------------


def test_create_linux_desktop_file_success(tmp_path, monkeypatch):
    """成功创建 .desktop 文件(行 106-120)。"""
    monkeypatch.setattr(shortcuts.sys, "platform", "linux")
    result = _create_linux_desktop_file(tmp_path, LOCATION_DESKTOP)
    assert result.success is True
    assert "已创建桌面快捷方式" in result.message
    assert (tmp_path / "File Toolbox.desktop").exists()


def test_create_linux_desktop_file_start_menu(tmp_path, monkeypatch):
    """start_menu location → '开始菜单' 提示。"""
    monkeypatch.setattr(shortcuts.sys, "platform", "linux")
    result = _create_linux_desktop_file(tmp_path, LOCATION_START_MENU)
    assert result.success is True
    assert "开始菜单" in result.message


def test_create_linux_desktop_file_oserror(tmp_path, monkeypatch):
    """write_text 抛 OSError → 失败结果(行 121-123)。"""
    monkeypatch.setattr(shortcuts.sys, "platform", "linux")
    monkeypatch.setattr(
        Path, "write_text", lambda self, *a, **k: (_ for _ in ()).throw(OSError("write boom"))
    )
    result = _create_linux_desktop_file(tmp_path, LOCATION_DESKTOP)
    assert result.success is False
    assert "write boom" in result.message


# ---------------------------------------------------------------------------
# _create_macos_unsupported + darwin 分发(行 127-128, 136)
# ---------------------------------------------------------------------------


def test_create_macos_unsupported_desktop():
    result = _create_macos_unsupported(LOCATION_DESKTOP)
    assert result.success is False
    assert "桌面" in result.message


def test_create_macos_unsupported_start_menu():
    result = _create_macos_unsupported(LOCATION_START_MENU)
    assert result.success is False
    assert "开始菜单" in result.message


def test_create_shortcut_darwin(monkeypatch):
    """darwin 平台 → _create_macos_unsupported(行 135-136)。"""
    monkeypatch.setattr(shortcuts.sys, "platform", "darwin")
    result = _create_shortcut(LOCATION_DESKTOP)
    assert result.success is False
    assert "macOS" in result.message


# ---------------------------------------------------------------------------
# _create_shortcut:linux 分发(行 140)
# ---------------------------------------------------------------------------


def test_create_shortcut_linux(monkeypatch, tmp_path):
    """linux 平台 → _create_linux_desktop_file(行 138-140)。"""
    monkeypatch.setattr(shortcuts.sys, "platform", "linux")
    monkeypatch.setattr(shortcuts, "desktop_dir", lambda: tmp_path)
    result = _create_shortcut(LOCATION_DESKTOP)
    assert result.success is True


# ---------------------------------------------------------------------------
# _shortcut_filename(行 153-157)
# ---------------------------------------------------------------------------


def test_shortcut_filename_windows(monkeypatch):
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    assert _shortcut_filename() == "File Toolbox.lnk"


def test_shortcut_filename_linux(monkeypatch):
    monkeypatch.setattr(shortcuts.sys, "platform", "linux")
    assert _shortcut_filename() == "File Toolbox.desktop"


# ---------------------------------------------------------------------------
# _remove_shortcut:unlink OSError(行 170-171)
# ---------------------------------------------------------------------------


def test_remove_shortcut_unlink_oserror(tmp_path, monkeypatch):
    """文件存在但 unlink 抛 OSError → 失败结果(行 170-171)。"""
    f = tmp_path / "File Toolbox.lnk"
    f.write_text("x")
    monkeypatch.setattr(shortcuts, "desktop_dir", lambda: tmp_path)
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    monkeypatch.setattr(Path, "unlink", lambda self, *a, **k: (_ for _ in ()).throw(OSError("locked")))
    result = _remove_shortcut(LOCATION_DESKTOP)
    assert result.success is False
    assert "locked" in result.message


def test_remove_shortcut_start_menu_not_found(tmp_path, monkeypatch):
    """start_menu 不存在 → 未找到(行 165-166)。"""
    monkeypatch.setattr(shortcuts, "start_menu_dir", lambda: tmp_path)
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    result = _remove_shortcut(LOCATION_START_MENU)
    assert result.success is False
    assert "未找到" in result.message
    assert "开始菜单" in result.message


# ---------------------------------------------------------------------------
# 公开入口覆盖
# ---------------------------------------------------------------------------


def test_create_desktop_shortcut_returns_result(monkeypatch, tmp_path):
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    monkeypatch.setattr(shortcuts, "desktop_dir", lambda: tmp_path)
    fake_win32com = MagicMock()
    shell = MagicMock()
    fake_win32com.client.Dispatch.return_value = shell
    import sys

    monkeypatch.setitem(sys.modules, "win32com", fake_win32com)
    result = create_desktop_shortcut()
    assert isinstance(result, ShortcutResult)


def test_create_start_menu_shortcut_returns_result(monkeypatch, tmp_path):
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    monkeypatch.setattr(shortcuts, "start_menu_dir", lambda: tmp_path)
    fake_win32com = MagicMock()
    fake_win32com.client.Dispatch.side_effect = RuntimeError("no com")
    import sys

    monkeypatch.setitem(sys.modules, "win32com", fake_win32com)
    result = create_start_menu_shortcut()
    assert result.success is False


def test_remove_desktop_shortcut_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(shortcuts, "desktop_dir", lambda: tmp_path)
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    result = remove_desktop_shortcut()
    assert result.success is False


def test_remove_start_menu_shortcut_returns_result(monkeypatch, tmp_path):
    monkeypatch.setattr(shortcuts, "start_menu_dir", lambda: tmp_path)
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    result = remove_start_menu_shortcut()
    assert isinstance(result, ShortcutResult)
