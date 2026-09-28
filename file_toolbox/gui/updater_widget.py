"""自更新 GUI 组件：只依赖 ``UpdateCoordinator`` 的结果模型。

线程模型(QThread 事件循环):
  - 检查:主窗口 start() → run() → exec() 启动事件循环;
         主窗口用 invokeMethod(do_check, QueuedConnection) 投递。
  - 下载/应用:主窗口调用 start_download(),先创建请求再经内部 queued signal 投递。
  两者都在 worker 线程执行,不阻塞 UI。结果模型和 progress 跨线程经信号回主线程。

亲和性注意:queued 方法投递按"接收者对象的亲和性线程"派发,而 QThread 对象
默认亲和于创建线程(主线程)。worker 构造时必须 moveToThread(self),且不能设
parent(带 parent 的 QObject 禁止跨线程移动);否则投递的 do_check 会被主线程
事件循环取出、在主线程同步执行网络检查,冻结 GUI 直至网络超时。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from threading import Lock

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QPushButton, QWidget

from file_toolbox.updater.coordinator import UpdateCancelled, UpdateCoordinator, UpdateRequest
from file_toolbox.updater.models import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)

_logger = logging.getLogger(__name__)


class UpdateBanner(QPushButton):
    """状态栏更新提示按钮。默认隐藏,有新版时 show_result() 显示。

    用 QPushButton 而非 QLabel + mousePressEvent:可 Tab 聚焦、Enter/Space 可
    触发,UIA 暴露 Invoke 模式 —— 键盘用户与 UI 自动化均能点击(内置 clicked
    信号,主窗口据此启动下载)。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFlat(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("打开更新页面")
        self.setStyleSheet(
            "QPushButton { color: #0969da; padding: 2px 8px; border: none; "
            "background: transparent; text-decoration: underline; }"
        )
        self.hide()

    def show_result(self, result: UpdateCheckResult) -> None:
        self.setText(f"🆕 发现新版本 {result.version} · 查看更新")
        self.show()


class UpdateWorker(QThread):
    """后台检查 + 下载 worker(运行自身事件循环,接收跨线程方法投递)。

    信号(均跨线程安全投递回主线程):
      ready(UpdateCheckResult)    — 检查到新版本
      checked(UpdateCheckResult)  — 每次检查的可观察结果
      progress(request, int)      — 该请求的下载百分比
      applying(request)           — 该请求已跨过不可取消边界
      applied(request, result)    — 该请求的最终结果

    用法(主线程):
      worker.start()                                  # 启动线程 + 事件循环
      QMetaObject.invokeMethod(worker, "do_check",
                               Qt.ConnectionType.QueuedConnection)
      # 用户点击后:
      request = worker.start_download()              # 排队前即保留取消状态

    生命周期:不得设 parent(亲和性约束,见模块 docstring);由 MainWindow 属性
    引用保活,closeEvent 中请求 quit,收到 finished 后退出窗口。
    """

    ready = Signal(object)  # UpdateCheckResult
    progress = Signal(object, int)  # request, percent
    applying = Signal(object)  # request 已跨过不可取消提交边界
    applied = Signal(object, object)  # request, UpdateApplyResult
    _download_requested = Signal(object)
    checked = Signal(object)  # UpdateCheckResult

    def __init__(
        self,
        coordinator: UpdateCoordinator,
        *,
        coordinator_factory: Callable[[], UpdateCoordinator] | None = None,
    ) -> None:
        super().__init__()
        self._coordinator_factory = coordinator_factory or (lambda: coordinator)
        # 最近一轮检查使用的 coordinator;下载绑定它,不受后续新检查影响
        # (工厂每轮生成新实例时,进行中的下载与新一轮检查天然隔离)。
        self._check_coordinator: UpdateCoordinator = coordinator
        self._request_lock = Lock()
        self._active_request: UpdateRequest | None = None
        self._active_expected_version: str | None = None
        self._download_requested.connect(
            self.do_download_and_apply, Qt.ConnectionType.QueuedConnection
        )
        # queued 投递按接收者亲和性派发;移入自身线程后 do_check 才在 worker 执行。
        self.moveToThread(self)

    @property
    def _coordinator(self) -> UpdateCoordinator:
        """最近一轮检查的 coordinator(测试探针与预置候选使用)。"""
        return self._check_coordinator

    def run(self) -> None:
        """启动事件循环,等待方法投递(do_check / do_download)。"""
        self.exec()

    @Slot()
    def do_check(self) -> None:
        """检查更新(在 worker 线程执行)。

        每轮经工厂重新装配 coordinator:代理/forward proxy 设置保存后,
        下一轮检查即使用新快照,无需重启窗口。始终 emit checked 反馈结果;
        有新版额外 emit ready。

        必须加 @Slot():主窗口用 QMetaObject.invokeMethod(worker, "do_check",
        QueuedConnection) 按名跨线程投递,PySide6 meta-object 系统只能识别
        被装饰为槽的方法;不加装饰器时投递事件会被静默丢弃,表现为"检查无反应"。
        """
        # 工厂与 check 同在 try 内:装配失败(如 settings IO 异常)也必须 emit
        # checked 映射为 FAILED,否则关于页停留在"检查中…"且按钮无法恢复。
        try:
            coordinator = self._coordinator_factory()
            self._check_coordinator = coordinator
            result = coordinator.check()
        except Exception as error:
            _logger.warning("检查更新失败", exc_info=True)
            result = UpdateCheckResult(UpdateCheckStatus.FAILED, message=str(error))
        self.checked.emit(result)
        if result.status is UpdateCheckStatus.AVAILABLE:
            self.ready.emit(result)

    def start_download(self, expected_version: str | None = None) -> UpdateRequest | None:
        """在调用线程保留请求后再投递;运行中与已安排 apply 时拒绝重复请求。

        ``expected_version``: 用户确认下载时展示的版本;worker 把它传给
        coordinator 做候选绑定校验,防止过期 UI 状态触发错误目标的更新。
        """
        with self._request_lock:
            if self._active_request is not None:
                return None
            request = UpdateRequest()
            self._active_request = request
            self._active_expected_version = expected_version
        self._download_requested.emit(request)
        return request

    @Slot(object)
    def do_download_and_apply(self, request: UpdateRequest) -> None:
        """处理对应请求,排队时收到的取消保留到执行。"""
        with self._request_lock:
            if request is not self._active_request or not request.claim():
                return
            coordinator = self._check_coordinator
            expected_version = self._active_expected_version

        def report_progress(value: int) -> None:
            request.check_cancelled()
            self.progress.emit(request, value)

        try:
            request.check_cancelled()
            # expected_version 仅在有确认版本时传递:老版 coordinator/fake 的
            # download_and_apply 没有该参数,None 时保持原调用形状。
            if expected_version is None:
                result = coordinator.download_and_apply(
                    progress=report_progress,
                    request=request,
                    before_apply=lambda: self.applying.emit(request),
                )
            else:
                result = coordinator.download_and_apply(
                    progress=report_progress,
                    request=request,
                    before_apply=lambda: self.applying.emit(request),
                    expected_version=expected_version,
                )
        except UpdateCancelled:
            result = UpdateApplyResult(UpdateApplyStatus.CANCELLED)
        except Exception as error:
            _logger.exception("更新下载或应用出现未知异常")
            result = UpdateApplyResult(UpdateApplyStatus.FAILED, f"更新失败: {error}")
        if request.finish():
            result = UpdateApplyResult(UpdateApplyStatus.CANCELLED)
        with self._request_lock:
            if not request.applying and result.status is not UpdateApplyStatus.APPLY_STARTED:
                self._active_request = None
                self._active_expected_version = None
        self.applied.emit(request, result)

    def cancel_download(self, request: UpdateRequest) -> bool:
        """直接线程安全调用;返回是否在 apply 提交前接受取消。"""
        with self._request_lock:
            return request is self._active_request and request.cancel()
