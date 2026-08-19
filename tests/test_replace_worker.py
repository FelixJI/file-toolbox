"""ReplaceWorker 测试:预览/执行 worker 的信号、取消与参数透传。

mock ContentReplaceService,不触发真实 COM。worker.run() 同步调用(不走
QThread.start,直接验证逻辑),跨线程投递用真实 start() 验证。
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication

from file_toolbox.gui.workers.replace_worker import (
    ReplaceExecuteWorker,
    ReplacePreviewWorker,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakePreviewService:
    """假 service:记录调用与 cancel_check,可控异常。"""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[tuple[list[Path], list[dict[str, Any]]]] = []
        self.cancel_checks: list[Any] = []

    def preview_replace(self, files, operations, cancel_check=None):
        self.calls.append((list(files), list(operations)))
        self.cancel_checks.append(cancel_check)
        if self.error:
            raise self.error
        return {f: {"match_count": 1, "status": "✓ 准备就绪"} for f in files}


class _FakeExecuteService:
    """假 service:记录 kwargs、驱动 progress_callback,可控异常。"""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.results = (2, 5, ["e1"])

    def execute_replace(self, files, operations, **kwargs):
        self.calls.append({"files": list(files), "operations": list(operations), **kwargs})
        if self.error:
            raise self.error
        progress = kwargs.get("progress_callback")
        if progress:
            progress(1, len(files))
            progress(2, len(files))
        return self.results


# ---------------------------------------------------------------------------
# ReplacePreviewWorker
# ---------------------------------------------------------------------------


def test_preview_worker_emits_ok(app):
    svc = _FakePreviewService()
    files = [Path("a.docx"), Path("b.txt")]
    ops = [{"type": "simple_replace", "params": {"find": "a", "replace": "b"}}]
    worker = ReplacePreviewWorker(svc, files, ops)
    captured: dict[str, Any] = {}
    worker.preview_ok.connect(lambda r: captured.setdefault("ok", r))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))

    worker.run()

    assert captured.get("ok") == {f: {"match_count": 1, "status": "✓ 准备就绪"} for f in files}
    assert "fail" not in captured
    assert svc.calls == [(files, ops)]


def test_preview_worker_emits_failed_on_exception(app):
    svc = _FakePreviewService(error=RuntimeError("COM 崩了"))
    worker = ReplacePreviewWorker(svc, [Path("a.docx")], [])
    captured: dict[str, Any] = {}
    worker.preview_ok.connect(lambda r: captured.setdefault("ok", r))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))

    worker.run()

    assert "COM 崩了" in captured.get("fail", "")
    assert "ok" not in captured


def test_preview_worker_cancel_flag_flows_to_service(app):
    """cancel() 置位后,传给 service 的 cancel_check 立即返回 True。"""
    svc = _FakePreviewService()
    worker = ReplacePreviewWorker(svc, [Path("a.txt")], [])

    assert worker._cancel is False
    worker.run()
    cancel_check = svc.cancel_checks[0]
    assert callable(cancel_check)
    assert cancel_check() is False
    worker.cancel()
    assert worker._cancel is True
    assert cancel_check() is True


def test_preview_worker_start_delivers_across_threads(app):
    """集成:真实 worker.start() → preview_ok 跨线程(queued)投递回主线程。"""
    svc = _FakePreviewService()
    files = [Path("a.docx")]
    worker = ReplacePreviewWorker(svc, files, [])
    captured: dict[str, Any] = {}
    worker.preview_ok.connect(lambda r: captured.setdefault("ok", r))
    failed: list[str] = []
    worker.failed.connect(lambda m: failed.append(m))

    worker.start()
    assert worker.wait(5000), "worker 未在 5s 内结束"
    app.processEvents()
    if "ok" not in captured:
        app.processEvents()

    assert captured.get("ok") == {f: {"match_count": 1, "status": "✓ 准备就绪"} for f in files}
    assert failed == []


# ---------------------------------------------------------------------------
# ReplaceExecuteWorker
# ---------------------------------------------------------------------------


def test_execute_worker_emits_ok_and_passes_options(app):
    svc = _FakeExecuteService()
    files = [Path("a.docx"), Path("b.docx")]
    ops = [{"type": "simple_replace", "params": {"find": "a", "replace": "b"}}]
    worker = ReplaceExecuteWorker(svc, files, ops, keep_new_format=True)
    captured: dict[str, Any] = {}
    worker.execute_ok.connect(lambda s, t, e: captured.setdefault("ok", (s, t, e)))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))
    progress: list[tuple[int, int]] = []
    worker.progress.connect(lambda c, t: progress.append((c, t)))

    worker.run()

    assert captured.get("ok") == (2, 5, ["e1"])
    assert "fail" not in captured
    assert progress == [(1, 2), (2, 2)]
    call = svc.calls[0]
    assert call["files"] == files
    assert call["operations"] == ops
    assert call["keep_new_format"] is True
    assert callable(call["cancel_check"])


def test_execute_worker_emits_failed_on_exception(app):
    svc = _FakeExecuteService(error=RuntimeError("Word 无响应"))
    worker = ReplaceExecuteWorker(svc, [Path("a.docx")], [])
    captured: dict[str, Any] = {}
    worker.execute_ok.connect(lambda s, t, e: captured.setdefault("ok", (s, t, e)))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))

    worker.run()

    assert "Word 无响应" in captured.get("fail", "")
    assert "ok" not in captured


def test_execute_worker_start_delivers_across_threads(app):
    """集成:真实 start() → execute_ok/progress 跨线程投递回主线程。"""
    svc = _FakeExecuteService()
    worker = ReplaceExecuteWorker(svc, [Path("a.docx"), Path("b.docx")], [])
    captured: dict[str, Any] = {}
    worker.execute_ok.connect(lambda s, t, e: captured.setdefault("ok", (s, t, e)))
    failed: list[str] = []
    worker.failed.connect(lambda m: failed.append(m))

    worker.start()
    assert worker.wait(5000), "worker 未在 5s 内结束"
    app.processEvents()
    if "ok" not in captured:
        app.processEvents()

    assert captured.get("ok") == (2, 5, ["e1"])
    assert failed == []
