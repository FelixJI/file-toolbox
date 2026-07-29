"""InvoiceParseWorker 测试:正常完成、异常、进度、取消。

mock InvoiceService,不触发真实 pdfplumber/解析。
worker.run() 同步调用(不走 QThread.start,直接验证逻辑),用 Qt 信号收集结果。
"""

import pytest

# 用 QtWidgets 子模块做 importorskip(而非顶层 PySide6):后者只校验包可 import,
# 不触发 libEGL/libGL 原生库加载;真实 import QtWidgets 才会,缺库时应跳过而非收集失败。
pytest.importorskip("PySide6.QtWidgets")

from pathlib import Path  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

from file_toolbox.gui.workers.invoice_worker import InvoiceParseWorker  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeService:
    """假 InvoiceService:记录调用,可控成功/失败。

    parse_files 返回固定的 ParseResult(self._result),按 files 数量驱动
    progress_callback;cancel_check 为真时提前停发进度。不提供 close()
    方法(回归 worker 不应调用 svc.close())。
    """

    def __init__(self, result, error=None):
        self._result = result
        self._error = error
        self.parse_calls = []

    def parse_files(
        self, files, dedupe_strategy="keep_all", progress_callback=None, cancel_check=None
    ):
        self.parse_calls.append((files, dedupe_strategy, cancel_check))
        if self._error:
            raise self._error
        total = len(files)
        for i in range(total):
            if cancel_check and cancel_check():
                break
            if progress_callback:
                progress_callback(i + 1, total)
        return self._result


def test_worker_emits_finished_ok_on_success(app):
    """正常完成 → finished_ok 信号带 results。"""
    from file_toolbox.core.invoice.types import ParseResult

    expected = ParseResult(invoices=[], duplicates=[], failed=[])
    svc = _FakeService(expected)
    worker = InvoiceParseWorker(svc, [Path("1.xml"), Path("2.xml")], "keep_all")

    captured = {}
    worker.finished_ok.connect(lambda r: captured.setdefault("ok", r))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))

    worker.run()  # 同步跑(不经 QThread.start)

    assert captured.get("ok") is expected
    assert "fail" not in captured
    assert len(svc.parse_calls) == 1


def test_worker_emits_failed_on_exception(app):
    """service 抛异常 → failed 信号。"""
    svc = _FakeService(None, error=RuntimeError("boom"))
    worker = InvoiceParseWorker(svc, [Path("1.xml")], "keep_all")

    captured = {}
    worker.finished_ok.connect(lambda r: captured.setdefault("ok", r))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))

    worker.run()

    assert "boom" in captured.get("fail", "")
    assert "ok" not in captured


def test_worker_emits_progress(app):
    """进度回调 → progress 信号,(current, total) 形状正确。"""
    from file_toolbox.core.invoice.types import ParseResult

    svc = _FakeService(ParseResult(invoices=[], duplicates=[], failed=[]))
    worker = InvoiceParseWorker(svc, [Path(f"f{i}.xml") for i in range(3)], "keep_all")

    progress_msgs = []
    worker.progress.connect(lambda c, t: progress_msgs.append((c, t)))

    worker.run()

    assert progress_msgs == [(1, 3), (2, 3), (3, 3)]


def test_worker_cancel_sets_flag(app):
    """cancel() 设标志;_cancel_check 反映该标志。"""
    from file_toolbox.core.invoice.types import ParseResult

    svc = _FakeService(ParseResult(invoices=[], duplicates=[], failed=[]))
    worker = InvoiceParseWorker(svc, [Path("1.xml")], "keep_all")

    assert worker._cancel is False
    assert worker._cancel_check() is False
    worker.cancel()
    assert worker._cancel is True
    assert worker._cancel_check() is True


def test_worker_does_not_call_close(app):
    """回归:InvoiceService 无 close() 方法 —— worker 绝不调用 svc.close()。

    若 worker 误加 self._svc.close()(照搬 pdf_worker 模式),此测试会因
    AttributeError 抛出而失败。
    """
    from file_toolbox.core.invoice.types import ParseResult

    svc = _FakeService(ParseResult(invoices=[], duplicates=[], failed=[]))
    assert not hasattr(svc, "close")  # 假 service 故意不提供 close

    worker = InvoiceParseWorker(svc, [Path("1.xml")], "keep_all")
    worker.run()  # 不应抛 AttributeError


def test_worker_start_delivers_finished_ok_across_threads(app):
    """集成:真正 worker.start() 后台线程 → finished_ok 信号跨线程投递回主线程。

    覆盖真实 QThread 启动 + 跨线程信号传递路径(区别于同步 run() 测试)。
    """
    from file_toolbox.core.invoice.types import ParseResult

    expected = ParseResult(invoices=[], duplicates=[], failed=[])
    svc = _FakeService(expected)
    worker = InvoiceParseWorker(svc, [Path("1.xml")], "keep_all")

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
        app.processEvents()

    assert captured.get("ok") is expected, "finished_ok 应投递 service 返回值到主线程槽"
    assert failed == [], "不应触发 failed"


def test_worker_start_delivers_failed_across_threads(app):
    """集成:worker.start() 异常路径 → failed 信号跨线程投递。"""
    svc = _FakeService(None, error=RuntimeError("cross-thread boom"))
    worker = InvoiceParseWorker(svc, [Path("1.xml")], "keep_all")

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
