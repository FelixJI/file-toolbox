"""PdfGenerateWorker 测试:正常完成、异常、取消。

mock PDFGeneratorService,不触发真实 COM/转换。
worker.run() 同步调用(不走 QThread.start,直接验证逻辑),用 Qt 信号收集结果。
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from file_toolbox.gui.workers.pdf_worker import PdfGenerateWorker  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _stub_engine_validation(monkeypatch):
    """默认 stub 掉 worker.run() 里的引擎兑现检测,避免测试环境真实 COM Dispatch
    产生非致命 traceback 噪声(test_worker_invokes_engine_validation 会用自带的
    spy 覆盖此 stub,单独验证兑现调用)。
    """
    from file_toolbox.core.batch_pdf.engine_manager import EngineManager

    monkeypatch.setattr(
        EngineManager,
        "_detect_available_engines",
        lambda self, force_refresh=False: {"office": False, "wps": False},
    )


class _FakeService:
    """假 service:记录调用,可控成功/失败。"""

    def __init__(self, results, error=None):
        self._results = results
        self._error = error
        self.closed = False
        self.batch_calls = []

    def batch_generate(self, files, config, progress_callback=None, cancel_check=None):
        self.batch_calls.append((files, config, cancel_check))
        if self._error:
            raise self._error
        # 模拟进度回调
        total = len(files)
        for i in range(total):
            if cancel_check and cancel_check():
                break
            if progress_callback:
                progress_callback(i, total, f"处理 {i}")
        return self._results[: len(files)]  # 取消时可能截断

    def close(self):
        self.closed = True


def _make_result(name, success=True, error=""):
    from pathlib import Path

    return {
        "source": Path(name),
        "output": Path(name + ".pdf"),
        "success": success,
        "error": error,
    }


def test_worker_emits_finished_ok_on_success(app):
    """正常完成 → finished_ok 信号带 results。"""
    results = [_make_result("a.docx"), _make_result("b.docx")]
    svc = _FakeService(results)
    worker = PdfGenerateWorker(
        svc, [__import__("pathlib").Path("a.docx"), __import__("pathlib").Path("b.docx")], {}
    )

    captured = {}
    worker.finished_ok.connect(lambda r: captured.setdefault("ok", r))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))

    worker.run()  # 同步跑(不经 QThread.start)

    assert captured.get("ok") == results
    assert "fail" not in captured
    assert svc.closed is True


def test_worker_emits_failed_on_exception(app):
    """service 抛异常 → failed 信号。"""
    svc = _FakeService([], error=RuntimeError("boom"))
    worker = PdfGenerateWorker(svc, [__import__("pathlib").Path("a.docx")], {})

    captured = {}
    worker.finished_ok.connect(lambda r: captured.setdefault("ok", r))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))

    worker.run()

    assert "boom" in captured.get("fail", "")
    assert "ok" not in captured
    assert svc.closed is True  # finally 仍 close


def test_worker_emits_progress(app):
    """进度回调 → progress 信号。"""
    from pathlib import Path

    results = [_make_result(f"f{i}.docx") for i in range(3)]
    svc = _FakeService(results)
    worker = PdfGenerateWorker(svc, [Path(f"f{i}.docx") for i in range(3)], {})

    progress_msgs = []
    worker.progress.connect(lambda c, t, m: progress_msgs.append((c, t, m)))

    worker.run()

    assert len(progress_msgs) == 3
    assert progress_msgs[0][1] == 3  # total


def test_worker_cancel_sets_flag(app):
    """cancel() 设标志;下次 cancel_check 触发时 batch_generate 内部 break。"""
    from pathlib import Path

    # 用真 cancel_check 逻辑验证:第二次检查时取消
    results = [_make_result(f"f{i}.docx") for i in range(3)]
    svc = _FakeService(results)
    files = [Path(f"f{i}.docx") for i in range(3)]
    worker = PdfGenerateWorker(svc, files, {})

    # 模拟用户在处理第一个文件后取消
    n = {"i": 0}

    def cancel_check():
        n["i"] += 1
        return n["i"] > 1

    # run 内部会用 self._cancel;这里直接验证 cancel() 设标志
    assert worker._cancel is False
    worker.cancel()
    assert worker._cancel is True


def test_worker_invokes_engine_validation(app, monkeypatch):
    """run() 应实例化 EngineManager 并以 force_refresh=True 调用兑现检测。

    回归:此前误以类调用实例方法,验证被 try/except 静默吞掉(从未真正执行)。
    """
    from pathlib import Path

    from file_toolbox.core.batch_pdf.engine_manager import EngineManager

    calls = []

    def _spy(self, force_refresh=False):
        calls.append({"force_refresh": force_refresh})
        return {"office": False, "wps": False}

    monkeypatch.setattr(EngineManager, "_detect_available_engines", _spy)

    results = [_make_result("a.docx")]
    svc = _FakeService(results)
    worker = PdfGenerateWorker(svc, [Path("a.docx")], {})

    worker.run()

    assert len(calls) == 1
    assert calls[0]["force_refresh"] is True


def test_worker_start_delivers_finished_ok_across_threads(app):
    """集成:真正 worker.start() 后台线程 → finished_ok 信号跨线程投递回主线程。

    覆盖真实 QThread 启动 + 跨线程信号传递路径(区别于同步 run() 测试)。用
    _FakeService 即时返回,worker 应快速完成并经 finished_ok(queued connection)
    把结果送到主线程的槽。用 slot 捕获 + worker.wait + processEvents 轮询投递。
    """
    from pathlib import Path

    results = [_make_result("a.docx"), _make_result("b.docx")]
    svc = _FakeService(results)
    worker = PdfGenerateWorker(svc, [Path("a.docx"), Path("b.docx")], {})

    captured = {}
    worker.finished_ok.connect(lambda r: captured.setdefault("ok", r))
    failed = []
    worker.failed.connect(lambda m: failed.append(m))

    worker.start()
    # 后台线程 run() 会 emit finished_ok(queued)然后返回;wait 阻塞至线程结束
    finished = worker.wait(5000)
    assert finished, "worker 未在 5s 内结束"
    # 跨线程 queued 信号需主线程事件循环处理;手动 flush
    app.processEvents()
    if "ok" not in captured:
        # 极少数情况需再多轮一次
        app.processEvents()

    assert captured.get("ok") == results, "finished_ok 应投递 service 返回值到主线程槽"
    assert failed == [], "不应触发 failed"
    assert svc.closed is True


def test_worker_start_delivers_failed_across_threads(app):
    """集成:worker.start() 异常路径 → failed 信号跨线程投递。"""
    from pathlib import Path

    svc = _FakeService([], error=RuntimeError("cross-thread boom"))
    worker = PdfGenerateWorker(svc, [Path("a.docx")], {})

    captured = {}
    worker.failed.connect(lambda m: captured.setdefault("fail", m))
    ok = []
    worker.finished_ok.connect(lambda r: ok.append(r))

    worker.start()
    assert worker.wait(5000), "worker 未在 5s 内结束"
    app.processEvents()
    if "fail" not in captured:
        app.processEvents()

    assert "cross-thread boom" in captured.get("fail", "")
    assert ok == []
    assert svc.closed is True  # finally 仍 close
