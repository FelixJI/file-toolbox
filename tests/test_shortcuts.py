"""shortcuts 模块测试。

所有外部交互通过 monkeypatch 重定向到 tmp_path,绝不碰用户真实桌面/开始菜单。
"""

import sys

import pytest

from file_toolbox.common import shortcuts


def test_shortcut_result_dataclass():
    r = shortcuts.ShortcutResult(True, "/path/x.lnk", "desktop", "成功")
    assert r.success is True
    assert r.path == "/path/x.lnk"
    assert r.location == "desktop"
    assert r.message == "成功"


def test_desktop_path_returns_path():
    p = shortcuts.desktop_dir()
    assert hasattr(p, "exists")  # 是 Path-like


def test_start_menu_path_returns_path():
    p = shortcuts.start_menu_dir()
    assert hasattr(p, "exists")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_desktop_uses_registry_or_home():
    # 不应抛异常;返回值是 Path
    p = shortcuts._windows_desktop()
    assert hasattr(p, "exists")
