"""PdfSortWorker 测试:正常完成、异常、进度、取消、跨线程投递。

mock PdfSortService,不触发真实 pypdf 读写。
worker.run() 同步调用(不走 QThread.start,直接验证逻辑),用 Qt 信号收集结果。
"""

import pytest

# 用 QtWidgets 子模块做 importorskip(而非顶层 PySide6):后者只校验包可 import,
# 不触发 libEGL/libGL 原生库加载;真实 import QtWidgets 才会,缺库时应跳过而非收集失败。
pytest.importorskip("PySide6.QtWidgets")

from pathlib import Path  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

from file_toolbox.core.pdf_sort import FailedFile, SortedFile, SortOptions, SortResult  # noqa: E402
from file_toolbox.gui.workers.pdf_sort_worker import PdfSortWorker  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeService:
    """假 PdfSortService:记录调用,可控成功/失败/取消。"""

    def __init__(self, result=None, error=None, cancelled_result=False):
        self._result = result
        self._error = error
        self._cancelled_result = cancelled_result
        self.sort_calls = []

    def sort(self, files, options, output=None, progress_callback=None, cancel_check=None):
        self.sort_calls.append((list(files), options, output, cancel_check))
        if self._error:
            raise self._error
        total = len(files)
        for i in range(total):
            if cancel_check and cancel_check():
                return SortResult(cancelled=True)
            if progress_callback:
                progress_callback(i + 1, total, f"排序 {files[i].name}")
        if self._cancelled_result:
            return SortResult(cancelled=True)
        if self._result is not None:
            return self._result
        return SortResult(sorted_files=[SortedFile(files[0].name, Path("out.pdf"), [])])


def _result_with_failed() -> SortResult:
    return SortResult(
        sorted_files=[SortedFile("a.pdf", Path("a_排序.pdf"), [])],
        failed=[FailedFile("b.pdf", "无法读取: broken")],
    )


def test_worker_emits_finished_ok_on_success(app):
    """正常完成 → finished_ok 信号带 SortResult(含失败文件信息)。"""
    expected = _result_with_failed()
    svc = _FakeService(result=expected)
    options = SortOptions(pattern="Date")
    worker = PdfSortWorker(svc, [Path("a.pdf"), Path("b.pdf")], None, options)

    captured = {}
    worker.finished_ok.connect(lambda r: captured.setdefault("ok", r))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))

    worker.run()  # 同步跑(不经 QThread.start)

    assert captured.get("ok") is expected
    assert "fail" not in captured
    assert svc.sort_calls[0][0] == [Path("a.pdf"), Path("b.pdf")]
    assert svc.sort_calls[0][1] is options
    assert svc.sort_calls[0][2] is None


def test_worker_emits_failed_on_exception(app):
    """service 抛异常 → failed 信号。"""
    svc = _FakeService(error=RuntimeError("boom"))
    worker = PdfSortWorker(svc, [Path("1.pdf")], None, SortOptions(pattern="Date"))

    captured = {}
    worker.finished_ok.connect(lambda r: captured.setdefault("ok", r))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))

    worker.run()

    assert "boom" in captured.get("fail", "")
    assert "ok" not in captured


def test_worker_emits_progress(app):
    """进度回调 → progress 信号,(current, total, msg) 形状正确。"""
    svc = _FakeService()
    worker = PdfSortWorker(
        svc, [Path(f"f{i}.pdf") for i in range(3)], None, SortOptions(pattern="Date")
    )

    progress_msgs = []
    worker.progress.connect(lambda c, t, m: progress_msgs.append((c, t, m)))

    worker.run()

    assert progress_msgs == [
        (1, 3, "排序 f0.pdf"),
        (2, 3, "排序 f1.pdf"),
        (3, 3, "排序 f2.pdf"),
    ]


def test_worker_cancel_sets_flag(app):
    """cancel() 设标志;_cancel_check 反映该标志并传给 service。"""
    svc = _FakeService()
    worker = PdfSortWorker(svc, [Path("1.pdf")], None, SortOptions(pattern="Date"))

    assert worker._cancel is False
    assert worker._cancel_check() is False
    worker.cancel()
    assert worker._cancel is True
    assert worker._cancel_check() is True


def test_worker_cancelled_result_still_finished_ok(app):
    """service 返回 cancelled 结果 → 仍走 finished_ok(取消非异常)。"""
    svc = _FakeService(cancelled_result=True)
    worker = PdfSortWorker(svc, [Path("1.pdf")], None, SortOptions(pattern="Date"))

    captured = {}
    worker.finished_ok.connect(lambda r: captured.setdefault("ok", r))
    worker.failed.connect(lambda m: captured.setdefault("fail", m))

    worker.run()

    assert captured.get("ok").cancelled is True
    assert "fail" not in captured


def test_worker_start_delivers_finished_ok_across_threads(app):
    """集成:真正 worker.start() 后台线程 → finished_ok 信号跨线程投递回主线程。"""
    expected = _result_with_failed()
    svc = _FakeService(result=expected)
    worker = PdfSortWorker(svc, [Path("a.pdf")], Path("out.pdf"), SortOptions(pattern="Date"))

    captured = {}
    worker.finished_ok.connect(lambda r: captured.setdefault("ok", r))
    failed = []
    worker.failed.connect(lambda m: failed.append(m))

    worker.start()
    finished = worker.wait(5000)
    assert finished, "worker 未在 5s 内结束"
    app.processEvents()
    if "ok" not in captured:
        app.processEvents()

    assert captured.get("ok") is expected, "finished_ok 应投递 service 返回值到主线程槽"
    assert failed == [], "不应触发 failed"


def test_worker_start_delivers_failed_across_threads(app):
    """集成:worker.start() 异常路径 → failed 信号跨线程投递。"""
    svc = _FakeService(error=RuntimeError("cross-thread boom"))
    worker = PdfSortWorker(svc, [Path("1.pdf")], None, SortOptions(pattern="Date"))

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
