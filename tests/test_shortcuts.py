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


def _patch_dirs(monkeypatch, tmp_path):
    """把桌面/开始菜单目录重定向到 tmp_path 子目录,隔离真实环境。"""
    desk = tmp_path / "desktop"
    start = tmp_path / "startmenu"
    desk.mkdir()
    start.mkdir()
    monkeypatch.setattr(shortcuts, "desktop_dir", lambda: desk)
    monkeypatch.setattr(shortcuts, "start_menu_dir", lambda: start)
    return desk, start


def test_create_desktop_shortcut_success(monkeypatch, tmp_path):
    desk, _ = _patch_dirs(monkeypatch, tmp_path)
    r = shortcuts.create_desktop_shortcut()
    assert r.success is True
    assert r.location == shortcuts.LOCATION_DESKTOP
    assert r.path  # 非空
    # 文件确实生成(Windows=.lnk,Linux=.desktop)
    created = list(desk.iterdir())
    assert len(created) == 1


def test_create_start_menu_shortcut_success(monkeypatch, tmp_path):
    _, start = _patch_dirs(monkeypatch, tmp_path)
    r = shortcuts.create_start_menu_shortcut()
    assert r.success is True
    assert r.location == shortcuts.LOCATION_START_MENU
    created = list(start.iterdir())
    assert len(created) == 1


def test_create_overwrites_existing(monkeypatch, tmp_path):
    desk, _ = _patch_dirs(monkeypatch, tmp_path)
    r1 = shortcuts.create_desktop_shortcut()
    assert r1.success
    r2 = shortcuts.create_desktop_shortcut()  # 再次创建
    assert r2.success  # 幂等,覆盖
    created = list(desk.iterdir())
    assert len(created) == 1  # 仍是 1 个,非 2 个


def test_create_start_menu_creates_dir_if_missing(monkeypatch, tmp_path):
    """开始菜单目录不存在时应自动创建。"""
    desk = tmp_path / "desktop"
    start = tmp_path / "deep" / "startmenu"  # 不存在的深层目录
    desk.mkdir()
    monkeypatch.setattr(shortcuts, "desktop_dir", lambda: desk)
    monkeypatch.setattr(shortcuts, "start_menu_dir", lambda: start)
    r = shortcuts.create_start_menu_shortcut()
    assert r.success is True
    assert start.exists()


def test_remove_nonexistent_desktop_returns_false(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    r = shortcuts.remove_desktop_shortcut()
    assert r.success is False
    assert r.location == shortcuts.LOCATION_DESKTOP
    assert "未找到" in r.message


def test_remove_nonexistent_start_menu_returns_false(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    r = shortcuts.remove_start_menu_shortcut()
    assert r.success is False
    assert r.location == shortcuts.LOCATION_START_MENU
    assert "未找到" in r.message


def test_create_then_remove_desktop_idempotent(monkeypatch, tmp_path):
    desk, _ = _patch_dirs(monkeypatch, tmp_path)
    assert shortcuts.create_desktop_shortcut().success
    assert list(desk.iterdir())  # 存在
    r = shortcuts.remove_desktop_shortcut()
    assert r.success is True
    assert "已删除" in r.message
    assert list(desk.iterdir()) == []  # 已删
    # 再删一次(不存在),应 success=False 不报错
    r2 = shortcuts.remove_desktop_shortcut()
    assert r2.success is False
    assert "未找到" in r2.message


def test_create_then_remove_start_menu_idempotent(monkeypatch, tmp_path):
    _, start = _patch_dirs(monkeypatch, tmp_path)
    assert shortcuts.create_start_menu_shortcut().success
    r = shortcuts.remove_start_menu_shortcut()
    assert r.success is True
    assert list(start.iterdir()) == []
    r2 = shortcuts.remove_start_menu_shortcut()
    assert r2.success is False
