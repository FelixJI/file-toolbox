"""回归:PDFGeneratorService.__del__ → close() → engine_manager.close() 的
_from_del 透传,避免 GC 链里触发 gc.collect() 导致 Windows 堆损坏 0xc0000374。

背景:EngineManager.close(_from_del=False) 末尾会 gc.collect();若该调用发生在
__del__ 触发的 GC 链中(例如 PDFGeneratorService.__del__ → service.close() →
engine_manager.close()),重入 GC 会与 pywin32/Windows 堆交互致堆损坏。故
service.close 必须把 _from_del 透传给 engine_manager.close。
"""

from file_toolbox.core.batch_pdf.service import PDFGeneratorService


def test_service_close_propagates_from_del_to_engine_manager(monkeypatch):
    """service.close(_from_del=True) 必须以 _from_del=True 调 engine_manager.close。"""
    svc = PDFGeneratorService()

    captured = {}
    monkeypatch.setattr(
        svc._engine_manager,
        "close",
        lambda _from_del=False: captured.setdefault("_from_del", _from_del),
    )

    svc.close(_from_del=True)

    assert captured.get("_from_del") is True


def test_service_close_default_does_not_force_from_del(monkeypatch):
    """显式 close()(非 __del__)默认 _from_del=False → engine_manager.close 仍跑 gc.collect。"""
    svc = PDFGeneratorService()

    captured = {}
    monkeypatch.setattr(
        svc._engine_manager,
        "close",
        lambda _from_del=False: captured.setdefault("_from_del", _from_del),
    )

    svc.close()  # 默认

    assert captured.get("_from_del") is False


def test_service_del_calls_close_with_from_del_true(monkeypatch):
    """PDFGeneratorService.__del__ 必须以 _from_del=True 调 close(不直接 gc.collect)。"""
    svc = PDFGeneratorService()

    captured = {}
    monkeypatch.setattr(
        svc,
        "close",
        lambda _from_del=False: captured.setdefault("_from_del", _from_del),
    )

    # 模拟析构链(__del__ 内部用 contextlib.suppress 包裹,不会抛)
    svc.__del__()

    assert captured.get("_from_del") is True
