"""EngineManager 注册表探测单元测试。

不触发真实 COM Dispatch,仅用 monkeypatch 替换 winreg。
"""

import pytest

from file_toolbox.core.batch_pdf.engine_manager import EngineManager


def test_probe_registry_returns_true_when_key_exists(monkeypatch):
    """HKCR 下存在 ProgID → 返回 True。"""
    import winreg

    def fake_open_key(root, subkey, *args, **kwargs):
        if subkey.lower() == "word.application":
            return object()  # 假的 key handle
        raise FileNotFoundError(subkey)

    monkeypatch.setattr(winreg, "OpenKey", fake_open_key)
    monkeypatch.setattr(winreg, "CloseKey", lambda h: None)

    assert EngineManager._probe_registry("Word.Application") is True
    assert EngineManager._probe_registry("KWPS.Application") is False


def test_probe_registry_returns_false_on_file_not_found(monkeypatch):
    import winreg

    def raise_fnf(root, subkey, *args, **kwargs):
        raise FileNotFoundError(subkey)

    monkeypatch.setattr(winreg, "OpenKey", raise_fnf)
    monkeypatch.setattr(winreg, "CloseKey", lambda h: None)

    assert EngineManager._probe_registry("Word.Application") is False


def test_probe_registry_returns_false_on_os_error(monkeypatch):
    """权限错误等 OSError 也视为不可用。"""
    import winreg

    def raise_os(root, subkey, *args, **kwargs):
        raise OSError("denied")

    monkeypatch.setattr(winreg, "OpenKey", raise_os)
    monkeypatch.setattr(winreg, "CloseKey", lambda h: None)

    assert EngineManager._probe_registry("Word.Application") is False


def test_detect_uses_registry_by_default(monkeypatch):
    """force_refresh=False(默认)走注册表,不调 _try_detect。"""
    # 清缓存避免串测
    EngineManager._cached_engines = None
    em = EngineManager()

    calls = []
    monkeypatch.setattr(EngineManager, "_probe_registry",
                        lambda prog_id: calls.append(prog_id) or True)
    monkeypatch.setattr(EngineManager, "_try_detect",
                        lambda *a, **k: pytest.fail("不应调用真 Dispatch"))

    result = em._detect_available_engines(force_refresh=False)
    assert result == {"office": True, "wps": True}
    assert "Word.Application" in calls
    assert "KWPS.Application" in calls


def test_detect_force_refresh_uses_real_dispatch(monkeypatch):
    """force_refresh=True 走 _try_detect(真 Dispatch),不调注册表。"""
    EngineManager._cached_engines = None
    em = EngineManager()

    monkeypatch.setattr(EngineManager, "_probe_registry",
                        lambda *a, **k: pytest.fail("force_refresh 不应走注册表"))
    monkeypatch.setattr(EngineManager, "_try_detect", lambda *a, **k: True)

    result = em._detect_available_engines(force_refresh=True)
    assert result == {"office": True, "wps": True}
