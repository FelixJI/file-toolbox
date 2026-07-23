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
    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda prog_id: calls.append(prog_id) or True
    )
    monkeypatch.setattr(
        EngineManager, "_try_detect", lambda *a, **k: pytest.fail("不应调用真 Dispatch")
    )

    result = em._detect_available_engines(force_refresh=False)
    assert result == {"office": True, "wps": True}
    assert "Word.Application" in calls
    assert "KWPS.Application" in calls


def test_detect_force_refresh_uses_real_dispatch(monkeypatch):
    """force_refresh=True 走 _try_detect(真 Dispatch),不调注册表。"""
    EngineManager._cached_engines = None
    em = EngineManager()

    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda *a, **k: pytest.fail("force_refresh 不应走注册表")
    )
    monkeypatch.setattr(EngineManager, "_try_detect", lambda *a, **k: True)

    result = em._detect_available_engines(force_refresh=True)
    assert result == {"office": True, "wps": True}


def test_async_detect_body_uses_registry_probe_not_dispatch(monkeypatch):
    """回归:启动异步检测必须走注册表(force_refresh=False),不应触发真 Dispatch。

    此前 detect_engines_async 的 worker 以 force_refresh=True 调用,每次打开对话框都
    Dispatch Word/WPS,违背注册表快速探测的设计目标。worker 体已抽到
    _async_detect_body,可直接同步断言。
    """
    EngineManager._cached_engines = None  # 清缓存避免直接命中
    em = EngineManager()

    detect_calls = []
    try_calls = []

    def _spy_detect(self, force_refresh=False):
        detect_calls.append(force_refresh)
        return {"office": True, "wps": False}

    monkeypatch.setattr(EngineManager, "_detect_available_engines", _spy_detect)
    monkeypatch.setattr(
        EngineManager,
        "_try_detect",
        lambda *a, **k: try_calls.append(a) or pytest.fail("启动检测不应走真 Dispatch"),
    )

    # 回调应被调用,参数为 get_engine_info(use_cache=True) 的返回字符串
    captured = {}
    em._async_detect_body(callback=lambda info: captured.setdefault("info", info))

    assert len(detect_calls) == 1
    assert detect_calls[0] is False  # 关键:force_refresh=False(注册表探测)
    assert try_calls == []  # 未触发真 Dispatch
    assert "info" in captured and isinstance(captured["info"], str)
