"""自更新 GUI 组件：只依赖 ``UpdateCoordinator`` 的结果模型。

线程模型(QThread 事件循环):
  - 检查:主窗口 start() → run() → exec() 启动事件循环;
         主窗口用 invokeMethod(do_check, QueuedConnection) 投递。
  - 下载/应用:主窗口用 invokeMethod(do_download_and_apply, QueuedConnection) 投递。
  两者都在 worker 线程执行,不阻塞 UI。结果模型和 progress 跨线程经信号回主线程。

亲和性注意:queued 方法投递按"接收者对象的亲和性线程"派发,而 QThread 对象
默认亲和于创建线程(主线程)。worker 构造时必须 moveToThread(self),且不能设
parent(带 parent 的 QObject 禁止跨线程移动);否则投递的 do_check 会被主线程
事件循环取出、在主线程同步执行网络检查,冻结 GUI 直至网络超时。
"""

from __future__ import annotations

import logging
from threading import Event

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel, QWidget

from file_toolbox.updater.coordinator import UpdateCancelled, UpdateCoordinator
from file_toolbox.updater.models import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)

_logger = logging.getLogger(__name__)


class UpdateBanner(QLabel):
    """状态栏更新提示条。默认隐藏,有新版时 show_release() 显示。

    点击触发 clicked 信号(主窗口据此启动下载)。
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "color: #0969da; padding: 2px 8px; cursor: pointer; text-decoration: underline;"
        )
        self.hide()

    def show_result(self, result: UpdateCheckResult) -> None:
        self.setText(f"🆕 发现新版本 {result.version} · 点击更新")
        self.show()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt 命名)
        self.clicked.emit()


class UpdateWorker(QThread):
    """后台检查 + 下载 worker(运行自身事件循环,接收跨线程方法投递)。

    信号(均跨线程安全投递回主线程):
      ready(UpdateCheckResult)    — 检查到新版本
      checked(UpdateCheckResult)  — 每次检查的可观察结果
      progress(int)               — SDK 计算的下载百分比
      applied(UpdateApplyResult)  — apply 安排结果

    用法(主线程):
      worker.start()                                  # 启动线程 + 事件循环
      QMetaObject.invokeMethod(worker, "do_check",
                               Qt.ConnectionType.QueuedConnection)
      # 用户点击后:
      QMetaObject.invokeMethod(worker, "do_download_and_apply",
                               Qt.ConnectionType.QueuedConnection)

    生命周期:不得设 parent(亲和性约束,见模块 docstring);由 MainWindow 属性
    引用保活,closeEvent 中 quit/wait 收尾。
    """

    ready = Signal(object)  # UpdateCheckResult
    progress = Signal(int)
    applied = Signal(object)  # UpdateApplyResult
    checked = Signal(object)  # UpdateCheckResult

    def __init__(self, coordinator: UpdateCoordinator) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._cancel_requested = Event()
        # queued 投递按接收者亲和性派发;移入自身线程后 do_check 才在 worker 执行。
        self.moveToThread(self)

    def run(self) -> None:
        """启动事件循环,等待方法投递(do_check / do_download)。"""
        self.exec()

    @Slot()
    def do_check(self) -> None:
        """检查更新(在 worker 线程执行)。

        始终 emit checked 反馈结果(供手动检查 UI);有新版额外 emit ready。
        自动检查场景只消费 ready(忽略 checked),行为不变。

        必须加 @Slot():主窗口用 QMetaObject.invokeMethod(worker, "do_check",
        QueuedConnection) 按名跨线程投递,PySide6 meta-object 系统只能识别
        被装饰为槽的方法;不加装饰器时投递事件会被静默丢弃,表现为"检查无反应"。
        """
        try:
            result = self._coordinator.check()
        except Exception as error:
            _logger.warning("检查更新失败", exc_info=True)
            result = UpdateCheckResult(UpdateCheckStatus.FAILED, message=str(error))
        self.checked.emit(result)
        if result.status is UpdateCheckStatus.AVAILABLE:
            self.ready.emit(result)

    @Slot()
    def do_download_and_apply(self) -> None:
        """由 Coordinator 下载并安排 apply/restart。"""
        self._cancel_requested.clear()

        def report_progress(value: int) -> None:
            if self._cancel_requested.is_set():
                raise UpdateCancelled
            self.progress.emit(value)

        try:
            result = self._coordinator.download_and_apply(progress=report_progress)
        except Exception as error:
            _logger.exception("更新下载或应用出现未知异常")
            result = UpdateApplyResult(UpdateApplyStatus.FAILED, f"更新失败: {error}")
        self.applied.emit(result)

    def cancel_download(self) -> None:
        """线程安全地请求在下一个 SDK progress callback 中止下载。"""

        self._cancel_requested.set()
