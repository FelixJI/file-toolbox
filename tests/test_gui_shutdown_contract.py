"""生命周期回归在独立进程运行，Qt abort/quit 不得影响 pytest 主进程。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "scenario",
    [
        "excel-result",
        "pdf-result",
        "excel-close",
        "pdf-close",
        "excel-busy",
        "pdf-busy",
        "main-close",
        "restart",
        "geometry",
        "registry",
        "orphan-thread",
        "finish-during-close",
    ],
)
def test_shutdown_contract_in_subprocess(tmp_path, scenario):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), scenario],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def exercise(scenario):
    from threading import Event
    from time import monotonic
    from unittest.mock import patch

    from openpyxl import Workbook
    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QThread, QTimer, Signal
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QApplication, QMessageBox
    from shiboken6 import isValid

    from file_toolbox.common import settings
    from file_toolbox.gui import main_window
    from file_toolbox.gui.dialogs import excel_merge_tab, pdf_sort_tab

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    def pump_until(condition, timeout=8000):
        loop = QEventLoop()
        poll = QTimer()
        poll.timeout.connect(lambda: loop.quit() if condition() else None)
        poll.start(2)
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        deadline.start(timeout)
        if not condition():
            loop.exec()
        assert condition(), "Qt 条件超时"

    release = Event()
    entered = Event()
    workers = []
    messages = []
    patches = [
        patch.object(settings, "_settings_path", return_value=Path("settings.json")),
        patch.object(QMessageBox, "information", side_effect=lambda *a: messages.append(a[1])),
        patch.object(QMessageBox, "warning", side_effect=lambda *a: messages.append(a[1])),
        patch.object(QMessageBox, "critical", side_effect=lambda *a: messages.append(a[1])),
        patch.object(main_window, "is_packaged_runtime", return_value=False),
    ]
    for p in patches:
        p.start()
    window = None
    try:
        if scenario in {"orphan-thread", "finish-during-close"}:
            window = main_window.MainWindow()
            window._ensure_tab(7)
            tab = window._pdf_sort_tab
            window.show()

            class OrphanThread(QThread):
                race = scenario == "finish-during-close"

                def isRunning(self):
                    if self.race:
                        self.race = False
                        release.set()
                        assert self.wait(8000)
                        return True  # 模拟查询状态之后、连接 finished 之前已退出。
                    return super().isRunning()

                def run(self):
                    entered.set()
                    assert release.wait(20)

            worker = OrphanThread(tab)
            workers.append(worker)
            worker.start()
            assert entered.wait(8)
            calls = []
            with patch.object(type(tab), "closeEvent", side_effect=lambda e: calls.append(e)):
                if scenario == "finish-during-close":
                    assert window.close(), "不能等待已错过的 finished"
                else:
                    assert not window.close()
                    assert calls == [], "运行中子线程必须先于 Tab/service 清理"
                    release.set()
                    pump_until(lambda: not window.isVisible())
                assert len(calls) == 1
            return

        if scenario in {"registry", "geometry"}:
            window = main_window.MainWindow()
            window.show()
            if scenario == "registry":
                window._ensure_tab(7)
                tab = window._pdf_sort_tab
                unopened = set(window._lazy_specs)
                calls = []
                with patch.object(type(tab), "closeEvent", side_effect=lambda e: calls.append(e)):
                    event = QCloseEvent()
                    window.closeEvent(event)
                assert len(calls) == 1, "遗漏已实例化 PDF 排序页"
                assert set(window._lazy_specs) == unopened, "关闭不应构造懒加载页"
                assert event.isAccepted()
            else:
                with patch.object(
                    window, "_persist_window_geometry", side_effect=OSError("geometry denied")
                ):
                    event = QCloseEvent()
                    window.closeEvent(event)
                assert event.isAccepted(), "几何写入失败不能阻断正常收尾"
            return

        is_pdf = scenario.startswith("pdf") or scenario in {"restart", "main-close"}
        module = pdf_sort_tab if is_pdf else excel_merge_tab
        worker_name = "PdfSortWorker" if is_pdf else "ExcelMergeWorker"
        original_worker = getattr(module, worker_name)

        class HeldWorker(original_worker):
            def run(self):
                if scenario.endswith("busy"):
                    entered.set()
                    assert release.wait(20)
                    super().run()
                else:
                    super().run()  # 真正输出/结果信号后，线程仍由 Event 保持运行。
                    entered.set()
                    assert release.wait(20), "测试没有释放线程"

        with patch.object(module, worker_name, HeldWorker):
            if scenario in {"restart", "main-close"}:
                from file_toolbox.updater import UpdateApplyResult, UpdateApplyStatus

                class FakeCoordinator:
                    def download_and_apply(self, progress=None, *, request=None, before_apply=None):
                        return UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)

                window = main_window.MainWindow(FakeCoordinator())
                window._ensure_tab(7)
                tab = window._pdf_sort_tab
            else:
                tab = module.PdfSortTab() if is_pdf else module.ExcelMergeTab()
                window = tab
            window.show()
            if is_pdf:
                from reportlab.pdfgen.canvas import Canvas

                canvas = Canvas("source.pdf")
                for text in ["NO.2", "NO.1"]:
                    canvas.drawString(20, 20, text)
                    canvas.showPage()
                canvas.save()
                tab._add_paths([Path("source.pdf")])
                tab.ui.edit_pattern.setText(r"NO\.(\d+)")
                start = tab._sort
                button = tab.ui.btn_sort
            else:
                wb = Workbook()
                wb.active.append(["payload"])
                wb.save("source.xlsx")
                wb.close()
                tab._add_paths([Path("source.xlsx")])
                start = tab._merge
                button = tab.ui.btn_merge
            tab.ui.edit_outdir.setText("output")
            start()
            worker = tab._worker
            workers.append(worker)
            assert entered.wait(8000 / 1000)
            if not scenario.endswith("busy"):
                pump_until(lambda: bool(messages))
            assert worker.isRunning()
            if scenario.endswith("result"):
                assert tab._worker is worker, "结果信号不等于 QThread.finished"
                assert not button.isEnabled(), "真实 finished 前不能恢复启动"
                start()
                assert tab._worker is worker, "重复启动替换了未退出 worker"

                class LateSignals(QThread):
                    finished_ok = Signal(object)
                    failed = Signal(str)
                    warning = Signal(str)
                    progress = Signal(int, int, str)

                late = LateSignals(tab)
                late.finished_ok.connect(tab._on_sort_ok if is_pdf else tab._on_merge_ok)
                late.failed.connect(tab._on_sort_failed if is_pdf else tab._on_merge_failed)
                late.warning.connect(tab._on_history_warning)
                late.progress.connect(tab._on_progress)
                late.finished.connect(tab._on_worker_finished)
                previous = tab.ui.lbl_status.text(), list(messages)
                late.finished_ok.emit(None)
                late.failed.emit("stale failure")
                late.warning.emit("stale warning")
                late.progress.emit(9, 9, "stale progress")
                late.finished.emit()
                assert tab._worker is worker
                assert (tab.ui.lbl_status.text(), messages) == previous
            elif scenario == "restart":
                quits = []
                with patch.object(QApplication, "quit", side_effect=lambda: quits.append(1)):
                    update = window._update_worker
                    workers.append(update)
                    update.start()
                    window._download_request = update.start_download()
                    pump_until(lambda: window._restart_pending)
                    assert quits == [], "重启绕过了运行中业务线程"
                    assert window.isVisible()
                    release.set()
                    pump_until(lambda: quits == [1])
            else:
                event = QCloseEvent()
                before = monotonic()
                window.closeEvent(event)
                assert not event.isAccepted(), "线程仍运行时错误接受关闭"
                assert monotonic() - before < 0.5, "关闭阻塞了 GUI 线程"
                window.closeEvent(QCloseEvent())
                if not is_pdf:
                    previous_messages = list(messages)
                    worker.warning.emit("输出工作簿关闭失败: injected cleanup failure")
                    app.processEvents()
                    assert messages == previous_messages, "关闭等待期间不应弹出收尾告警"
                elapsed = []
                QTimer.singleShot(3100, lambda: elapsed.append(True))
                pump_until(lambda: bool(elapsed))
                assert worker.isRunning() and window.isVisible()
                release.set()
                pump_until(lambda: not window.isVisible())
            release.set()
            if isValid(worker):
                assert worker.wait(8000)
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert tab._worker is None
            assert not isValid(worker), "已结束线程 QObject 未释放"
            if not scenario.endswith("busy"):
                assert list(Path("output").iterdir()), "真实输出应保留"
    finally:
        release.set()
        for worker in workers:
            if isValid(worker):
                assert worker.wait(8000)
        app.processEvents()
        if window is not None:
            window.close()
        for p in reversed(patches):
            p.stop()


if __name__ == "__main__":
    exercise(sys.argv[1])
