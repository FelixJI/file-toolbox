"""GUI 任务的结果、线程结束与异步关闭边界；业务结果仍由页面消费。"""

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QWidget


class TaskLifecycle:
    """每个页面一个句柄，直到消费真实 finished 才允许下一轮任务。"""

    def __init__(self, owner: QWidget) -> None:
        self._owner = owner
        self.worker: QThread | None = None
        self.close_pending = False
        # start 前观察缝(--selftest 驱动专用):track 是页面启动 worker 的唯一
        # 统一注册点,在此回调订阅可严格先于 worker.start(),消除"启动后才连接"
        # 的发射竞态(工作线程可能立即失败/立即清理告警)。正常 GUI 不设置
        # (默认 None,零开销);不引入全局 QThread 拦截框架。
        self.on_worker_tracked: Callable[[QThread], None] | None = None

    @property
    def busy(self) -> bool:
        return self.worker is not None or self.close_pending

    def track(self, worker: QThread) -> None:
        if self.busy:
            raise RuntimeError("上一任务尚未结束")
        self.worker = worker
        observer = self.on_worker_tracked
        if observer is not None:
            observer(worker)

    def accepts(self, sender: QObject | None) -> bool:
        # 页面也允许同步调用结果槽；真实信号必须来自当前任务。
        return sender is None or sender is self.worker

    def finish(self, sender: QObject | None) -> bool:
        worker = self.worker
        if worker is None or sender is not worker:
            return False
        self.worker = None
        worker.deleteLater()
        if self.close_pending:
            QTimer.singleShot(0, self._resume_close)
        return True

    def cancel(self) -> None:
        cancel = getattr(self.worker, "cancel", None)
        if callable(cancel):
            cancel()

    def defer_close(self, event: QCloseEvent) -> bool:
        if self.worker is None:
            return False
        if not self.close_pending:
            self.close_pending = True
            self.cancel()
        event.ignore()
        return True

    def _resume_close(self) -> None:
        self.close_pending = False
        self._owner.window().close()
