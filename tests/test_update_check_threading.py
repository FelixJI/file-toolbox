"""启动自动检查更新的线程亲和性回归测试。

历史 bug:UpdateWorker 是 QThread 子类,但对象创建于主线程,其 QObject 亲和性
是主线程;QMetaObject.invokeMethod(..., QueuedConnection) 按"接收者亲和性线程"
派发,导致投递的 do_check 事件被主线程事件循环取出、在主线程同步执行网络
检查,GUI 冻结直至网络超时(freeze watchdog 日志:冻结约 31.6s)。本测试锁定:
frozen 自动检查路径上 coordinator.check() 必须不在主线程执行。
"""

import sys
import threading
import time
from collections.abc import Callable

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from file_toolbox.gui.main_window import MainWindow
from file_toolbox.updater import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)


class ThreadRecordingCoordinator:
    """记录 check() 实际执行线程的 fake(立即返回,不阻塞)。"""

    def __init__(self) -> None:
        self.called = threading.Event()
        self.thread_ident: int | None = None

    def check(self) -> UpdateCheckResult:
        self.thread_ident = threading.get_ident()
        self.called.set()
        return UpdateCheckResult(UpdateCheckStatus.LATEST)

    def download_and_apply(
        self, progress: Callable[[int], None] | None = None
    ) -> UpdateApplyResult:
        return UpdateApplyResult(UpdateApplyStatus.FAILED, "unused")


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_frozen_auto_check_runs_off_main_thread(app, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    coordinator = ThreadRecordingCoordinator()
    win = MainWindow(coordinator)
    try:
        deadline = time.monotonic() + 5.0
        while not coordinator.called.is_set() and time.monotonic() < deadline:
            app.processEvents()
            coordinator.called.wait(0.02)
        assert coordinator.called.wait(1.0), "启动自动检查未触发"
        assert coordinator.thread_ident != threading.get_ident(), (
            "coordinator.check() 在主线程执行:启动自动检查会阻塞 GUI 事件循环"
        )
    finally:
        win.close()
