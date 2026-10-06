"""PDF 的结果不能释放仍在关闭 service 的真实 QThread。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("closing", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_pdf_result_waits_for_service_cleanup(tmp_path, failure, closing):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), str(int(failure)), str(int(closing))],
        cwd=tmp_path,
        env=dict(
            os.environ, QT_QPA_PLATFORM="offscreen", FILE_TOOLBOX_NO_COM_DETECT="1", PYTHONUTF8="1"
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def exercise(failure, closing):
    from threading import Event
    from time import monotonic
    from unittest.mock import patch

    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from shiboken6 import isValid

    from file_toolbox.gui.dialogs.pdf_tab import PDFGeneratorDialog

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    entered, release = Event(), Event()
    messages = []

    class Service:
        def batch_generate(self, *args, **kwargs):
            if failure:
                raise ValueError("controlled failure")
            return []

        def close(self, *, strict=False):
            entered.set()
            assert release.wait(10)

        def get_engine_info(self, **kwargs):
            return "test"

    def pump_until(condition):
        loop = QEventLoop()
        timer = QTimer()
        timer.timeout.connect(lambda: loop.quit() if condition() else None)
        timer.start(1)
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        deadline.start(5000)
        if not condition():
            loop.exec()
        assert condition(), "Qt condition timeout"

    with (
        patch.object(QMessageBox, "critical", side_effect=lambda *a: messages.append(a)),
        patch.object(QMessageBox, "warning", side_effect=lambda *a: messages.append(a)),
    ):
        dialog = PDFGeneratorDialog()
        dialog._svc = Service()
        dialog.show()
        dialog.selected_files = [Path("fictional.png")]
        worker = None
        try:
            dialog._generate()
            worker = dialog.worker
            assert entered.wait(5)
            pump_until(
                lambda: bool(messages) if failure else "完成:" in dialog.ui.label_progress.text()
            )
            assert worker.isRunning()
            assert dialog.worker is worker, "结果信号提前释放 worker"
            assert not dialog.ui.btn_generate.isEnabled(), "收尾期间恢复了启动按钮"
            dialog._generate()
            assert dialog.worker is worker, "收尾期间启动了下一任务"
            if closing:
                before = monotonic()
                assert not dialog.close()
                assert monotonic() - before < 0.5, "关闭不得阻塞事件循环"
                assert not dialog.close()
                responsive = []
                QTimer.singleShot(0, lambda: responsive.append(True))
                pump_until(lambda: responsive)
                assert worker.isRunning() and dialog.isVisible()
            release.set()
            assert worker.wait(5000)
            pump_until(lambda: dialog.worker is None)
            if closing:
                pump_until(lambda: not dialog.isVisible())
        finally:
            release.set()
            if worker is not None and isValid(worker):
                assert worker.wait(5000)
            app.processEvents()
            dialog.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert dialog.worker is None
        assert not isValid(worker), "结束的 QThread 必须释放"


if __name__ == "__main__":
    exercise(bool(int(sys.argv[1])), bool(int(sys.argv[2])))


def test_lifecycle_reusable_task_and_late_signals():
    from threading import Event
    from types import SimpleNamespace

    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QThread, QTimer, Signal
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QApplication, QWidget
    from shiboken6 import isValid

    from file_toolbox.gui.main_window import MainWindow
    from file_toolbox.gui.task_lifecycle import TaskLifecycle

    app = QApplication.instance() or QApplication([])
    release = Event()
    entered = Event()

    class Worker(QThread):
        progress = Signal(int)

        def __init__(self, parent):
            super().__init__(parent)
            self.cancel_count = 0

        def run(self):
            self.progress.emit(1)
            entered.set()
            assert release.wait(10)

        def cancel(self):
            self.cancel_count += 1

    class Page(QWidget):
        def __init__(self):
            super().__init__()
            self.task = TaskLifecycle(self)
            self._task = self.task
            self.value = 0

        def progress(self, value):
            if self.task.accepts(self.sender()):
                self.value = value

        def finished(self):
            self.task.finish(self.sender())

        def closeEvent(self, event):
            if not self.task.defer_close(event):
                super().closeEvent(event)

    page = Page()
    page.show()
    worker = Worker(page)
    late = Worker(page)
    for item in (worker, late):
        item.progress.connect(page.progress)
        item.finished.connect(page.finished)
    page.task.track(worker)
    window = SimpleNamespace(_tab_attrs=["_test_page"], _test_page=page)
    assert MainWindow._running_business_workers(window) == [worker]
    worker.start()
    try:
        assert entered.wait(5)
        app.processEvents()
        assert page.value == 1
        with pytest.raises(RuntimeError, match="上一任务"):
            page.task.track(late)
        late.progress.emit(999)
        late.finished.emit()
        assert page.value == 1
        assert page.task.worker is worker
        assert not page.task.finish(None)
        event = QCloseEvent()
        page.closeEvent(event)
        page.closeEvent(QCloseEvent())
        assert not event.isAccepted()
        assert page.task.busy and page.task.close_pending
        assert worker.cancel_count == 1
        # 取消只请求协作停止，线程和窗口仍然存在。
        assert worker.isRunning() and page.isVisible()
    finally:
        release.set()
        assert worker.wait(5000)
        assert MainWindow._running_business_workers(window) == [worker]
        loop = QEventLoop()
        timer = QTimer()
        timer.timeout.connect(lambda: loop.quit() if not page.isVisible() else None)
        timer.start(1)
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        deadline.start(5000)
        loop.exec()
        page.close()
    assert not page.task.busy
    assert not page.isVisible()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(worker)
    assert not page.task.finish(late)
    page.task.cancel()  # 无当前任务无副作用。

    # 同一页面连续执行，已完成的 QObject 不随批次累积。
    for _ in range(3):
        following = Worker(page)
        following.finished.connect(page.finished)
        page.task.track(following)
        following.start()
        assert following.wait(5000)
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not page.task.busy
        assert not isValid(following)
        assert page.findChildren(QThread) == [late]
