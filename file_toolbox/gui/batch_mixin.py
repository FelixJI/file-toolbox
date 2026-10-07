"""批处理对话框混入类 - 提供文件选择、预览、进度显示等公共功能。"""

import contextlib
import logging
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, QThread, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QListView,
    QListWidget,
    QMessageBox,
    QTableView,
    QTableWidget,
    QWidget,
)

from file_toolbox.common.file_utils import format_file_size, get_file_info
from file_toolbox.gui.file_models import FileListModel, table_model
from file_toolbox.gui.task_lifecycle import TaskLifecycle
from file_toolbox.gui.workers.file_scan_worker import FileScanWorker, ScannedFile

# 预览防抖 / worker 停止超时(毫秒)
PREVIEW_DEBOUNCE_MS = 200
WORKER_STOP_TIMEOUT_MS = 3000


class SignalManager(QObject):
    """集中管理信号槽连接,便于清理。"""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._connections: list[tuple[Any, Any, str]] = []

    # NOTE: 故意不叫 connect() —— 那会与 QObject.connect 签名冲突(mypy [override]),
    # 且本管理器的三参形态(带 description)与 Qt 单参 connect 语义不同。
    def add_connection(self, signal: Any, slot: Callable[..., Any], description: str = "") -> None:
        try:
            signal.connect(slot)
            self._connections.append((signal, slot, description))
        except Exception:
            pass

    def disconnect_all(self) -> None:
        for signal, slot, _ in self._connections:
            with contextlib.suppress(RuntimeError):
                signal.disconnect(slot)
        self._connections.clear()


class FileImportMixin:
    """七个文件入口的扫描队列，沿用页面唯一 TaskLifecycle。"""

    _task: TaskLifecycle

    def _init_import(
        self,
        files: list[Path],
        view: QListView | None = None,
        full_path: bool = False,
        resolved: bool = False,
        check_files: bool = False,
        metadata: bool = False,
    ) -> None:
        self._import_files = files
        self._file_model = FileListModel(files, full_path, cast(QObject, self))
        if view is not None:
            view.setUniformItemSizes(True)
            view.setModel(self._file_model)
        # epoch仅由清空/取消废弃；追加请求排队，不使正在收尾的业务结果失效。
        self._import_generation = 0
        self._business_generation = 0
        self._import_pending: deque[FileScanWorker] = deque()
        self._import_changed = False
        self._import_resolved = resolved
        self._import_check_files = check_files
        self._import_metadata = metadata
        self._file_metadata: dict[Path, ScannedFile] = {}
        self._import_errors: list[str] = []

    def _queue_import(
        self,
        paths: list[Path],
        supported: Callable[[Path], bool],
        folder: Path | None = None,
        recursive: bool = False,
        *,
        unchecked: bool = False,
    ) -> None:
        if self._task.close_pending:
            return
        active = self._task.worker
        if not self._import_pending and (
            not isinstance(active, FileScanWorker) or active.cancel_requested
        ):
            self._import_errors.clear()
        worker = FileScanWorker(
            self._import_generation,
            paths,
            folder,
            recursive,
            supported,
            [],
            self._import_resolved and not unchecked,
            self._import_check_files and not unchecked,
            self._import_metadata and not unchecked,
            cast(QWidget, self),
        )
        worker.deduplicate = not unchecked
        self._import_pending.append(worker)
        self._resume_import()

    def _resume_import(self) -> bool:
        if self._task.busy or not self._import_pending:
            return False
        worker = self._import_pending.popleft()
        worker.existing = list(self._import_files)
        worker.batch.connect(self._on_import_batch)
        worker.failed.connect(self._on_import_error)
        worker.finished.connect(self._on_import_finished)
        self._task.track(worker)
        self._import_busy(True)
        worker.start()
        return True

    def _on_import_batch(self, generation: int, batch: list[ScannedFile]) -> None:
        sender = cast(QObject, self).sender()
        if (
            sender is not self._task.worker
            or generation != self._import_generation
            or self._task.close_pending
        ):
            return
        self._import_changed = True
        self._file_metadata.update({item.path: item for item in batch})
        self._file_model.append_paths([item.path for item in batch])
        self._import_updated(batch)

    def _on_import_error(self, generation: int, message: str) -> None:
        if (
            cast(QObject, self).sender() is not self._task.worker
            or generation != self._import_generation
            or self._task.close_pending
        ):
            return
        self._import_errors.append(message)
        logging.getLogger(type(self).__module__).warning("文件扫描失败: %s", message)
        self._import_status(f"扫描失败: {message}")

    def _on_import_finished(self) -> None:
        worker = self._task.worker
        if not isinstance(worker, FileScanWorker):
            return
        cancelled = worker.cancel_requested
        current = worker.generation == self._import_generation
        if not self._task.finish(cast(QObject, self).sender()):
            return
        self._import_busy(False)
        if cancelled:
            self._import_cancelled()
            if current:
                self._discard_import_queue()
        if not self._task.close_pending and not self._resume_import():
            if current and not cancelled:
                self._after_import()
            self._import_changed = False
            if self._import_errors:
                self._import_status(
                    f"已选择 {len(self._import_files)} 个文件，扫描错误 "
                    f"{len(self._import_errors)} 项: {self._import_errors[-1]}"
                )

    def _invalidate_import(self) -> None:
        self._import_generation += 1
        self._import_errors.clear()
        self._discard_import_queue()
        self._import_changed = False
        self._task.cancel()
        self._import_cancelled()
        self._file_metadata.clear()
        self._file_model.replace_paths([])

    def _discard_import_queue(self) -> None:
        while self._import_pending:
            self._import_pending.popleft().deleteLater()

    def _cancel_import(self) -> bool:
        # 只取消扫描：业务取消仍须接收实际完成成果，且不丢其排队导入。
        if not isinstance(self._task.worker, FileScanWorker):
            return False
        self._import_generation += 1
        self._discard_import_queue()
        self._import_changed = False
        self._task.cancel()
        self._import_cancelled()
        return True

    def _import_cancelled(self) -> None:
        pass

    def _accept_business_result(self) -> bool:
        return self._task.accepts(cast(QObject, self).sender()) and (
            cast(QObject, self).sender() is None
            or self._business_generation == self._import_generation
        )

    def _import_updated(self, batch: list[ScannedFile]) -> None:
        self._import_status(f"已选择 {len(self._import_files)} 个文件")

    def _import_status(self, text: str) -> None:
        pass

    def _import_busy(self, busy: bool) -> None:
        pass

    def _after_import(self) -> None:
        pass


class BatchDialogMixin(FileImportMixin):
    """批处理对话框混入类，提供文件选择、预览刷新和工作线程管理功能"""

    SUPPORTED_FORMATS: set[str] = set()
    PREVIEW_DEBOUNCE_MS: int = 200  # 预览防抖(毫秒)

    # _stop_worker/_cleanup_batch_dialog 需要 logger。子类可显式提供(如
    # PDFGeneratorDialog 的模块级类属性);未提供时由 _init_batch_dialog 兜底,
    # 否则 closeEvent 清理会抛 AttributeError(旧版 FileRenamerDialog 即如此)。
    logger: logging.Logger
    # worker 可能是任意 QThread 子类(如 PdfGenerateWorker),运行期可为 None。
    # 声明类级类型,避免 mypy 从 self.worker = None 推断出过于窄的 None 类型。
    worker: QThread | None

    @property
    def selected_files(self) -> list[Path]:
        return self._selected_files

    @selected_files.setter
    def selected_files(self, files: list[Path]) -> None:
        if hasattr(self, "_file_model"):
            self._file_model.replace_paths(files)
        else:
            self._selected_files = files

    def _init_batch_dialog(self) -> None:
        """初始化批处理对话框功能（在__init__中调用）"""
        # logger 兜底:实例属性而非 @property——property 与 Qt 元类在解释器退出期
        # GC 交互有堆损坏风险(见 pdf_tab 中放弃 LoggableMixin 的同类注释)。
        if not hasattr(self, "logger"):
            self.logger = logging.getLogger(type(self).__module__)
        self.selected_files = []
        self._import_auto_preview = True
        if not hasattr(self, "_task"):
            self._task = TaskLifecycle(cast(QWidget, self))
        self._init_import(self.selected_files, metadata=True)
        self.worker = None
        # 本 mixin 总是被混入 QDialog(本身是 QObject)。用 cast 如实表达
        # "运行期 self 即为 QWidget"这一契约,以满足 Qt API 的类型要求。
        self._signal_manager = SignalManager(cast(QObject, self))
        self._preview_timer = QTimer(cast(QObject, self))
        self._preview_timer.setSingleShot(True)
        self._signal_manager.add_connection(
            self._preview_timer.timeout, self._do_refresh_preview, "预览防抖定时器"
        )

    def _get_file_filter(self) -> str:
        """获取文件选择过滤器"""
        if self.SUPPORTED_FORMATS:
            formats = " ".join(f"*{ext}" for ext in self.SUPPORTED_FORMATS)
            return f"支持的文件 ({formats});;所有文件 (*.*)"
        return "所有文件 (*.*)"

    def _is_temp_file(self, file_path: Path) -> bool:
        """检查是否为临时文件（Word/Excel临时文件、.tmp文件等）"""
        name = file_path.name
        if name.startswith("~$") or name.startswith("~"):
            return True
        return file_path.suffix.lower() == ".tmp"

    def _is_file_supported(self, file_path: Path) -> bool:
        """检查文件是否支持"""
        if self._is_temp_file(file_path):
            return False
        if not self.SUPPORTED_FORMATS:
            return True
        return file_path.suffix.lower() in self.SUPPORTED_FORMATS

    def _select_files(
        self, list_widget: QListView | QListWidget | None = None, auto_preview: bool = True
    ) -> None:
        """选择文件"""
        files, _ = QFileDialog.getOpenFileNames(
            cast(QWidget, self), "选择文件", "", self._get_file_filter()
        )
        if files:
            if isinstance(list_widget, QListView):
                list_widget.setModel(self._file_model)
                self._file_model.full_path = True
            self._prepare_import_preview(auto_preview)
            self._queue_import([Path(p) for p in files], self._is_file_supported)

    def _select_folder(
        self,
        list_widget: QListView | QListWidget | None = None,
        ask_recursive: bool = True,
        auto_preview: bool = True,
    ) -> None:
        """选择文件夹"""
        folder = QFileDialog.getExistingDirectory(cast(QWidget, self), "选择文件夹")
        if not folder:
            return

        folder_path = Path(folder)
        recursive = False

        if ask_recursive:
            reply = QMessageBox.question(
                cast(QWidget, self),
                "选择模式",
                "是否包含子文件夹中的文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            recursive = reply == QMessageBox.StandardButton.Yes

        if isinstance(list_widget, QListView):
            list_widget.setModel(self._file_model)
            self._file_model.full_path = True
        self._prepare_import_preview(auto_preview)
        self._queue_import([], self._is_file_supported, folder_path, recursive)

    def _import_updated(self, batch: list[ScannedFile]) -> None:
        self._update_status()

    def _prepare_import_preview(self, auto_preview: bool) -> None:
        active = self._task.worker
        if not self._import_pending and (
            not isinstance(active, FileScanWorker) or active.cancel_requested
        ):
            self._import_auto_preview = auto_preview
        elif auto_preview:
            self._import_auto_preview = True

    def _after_import(self) -> None:
        if self._import_auto_preview and self._import_changed:
            self._refresh_preview()

    def _import_cancelled(self) -> None:
        self._preview_timer.stop()

    def _import_status(self, text: str) -> None:
        ui = getattr(self, "ui", None)
        if ui is not None:
            ui.label_status.setText(text)

    def _import_busy(self, busy: bool) -> None:
        ui = getattr(self, "ui", None)
        if ui is not None:
            ui.btn_cancel.setVisible(busy)

    def _clear_files(
        self,
        list_widget: QListView | QListWidget | None = None,
        table_widget: QTableView | QTableWidget | None = None,
    ) -> None:
        """清空文件列表"""
        self._preview_timer.stop()
        self._invalidate_import()
        if isinstance(table_widget, QTableWidget):
            table_widget.setRowCount(0)
        elif table_widget is not None:
            table_model(table_widget).replace_rows([])
        self._update_status()

    def _refresh_preview(self) -> None:
        """刷新预览（带防抖机制）"""
        self._preview_timer.stop()
        self._preview_timer.start(self.PREVIEW_DEBOUNCE_MS)

    def _do_refresh_preview(self) -> None:
        """执行刷新预览（子类必须实现）"""
        pass

    def _stop_worker(self, timeout_ms: int = WORKER_STOP_TIMEOUT_MS) -> None:
        """请求工作线程协作停止(cancel),不阻塞 GUI 线程、不强制终止。

        线程引用的清空与 deleteLater 只由真实 finished(TaskLifecycle.finish)消费:
        这里既不清引用,也不断开 worker 信号——清理期间线程可能仍在收尾(尤其持
        COM 的 worker),断开信号会让 finished 无法投递回页面,terminate/同步 wait
        则可能泄漏 Office 进程或冻结关闭。业务 worker 无事件循环,quit() 是 no-op,
        不再调用。timeout_ms 仅保留兼容旧签名,不再等待。
        """
        worker = self.worker
        if worker is None or not worker.isRunning():
            return
        cancel = getattr(worker, "cancel", None)
        if callable(cancel):
            cancel()

    def _set_ui_enabled(self, enabled: bool) -> None:
        """设置UI启用状态（子类可覆盖）"""
        pass

    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        return format_file_size(size)

    def _get_file_info(self, file_path: Path) -> dict[str, object]:
        """获取文件信息"""
        return get_file_info(file_path)

    def _update_status(self) -> None:
        """文件列表变更后的钩子(选择/清空文件后由 mixin 自动调用)。

        默认空实现;子类按需覆盖(如更新"已选择 N 个文件"标签)。
        旧实现需在每个子类里重写 _select_files/_select_folder/_clear_files
        仅为了转发到本方法 —— 现在子类只需实现这一个钩子。
        """
        pass

    def _cleanup_batch_dialog(self) -> None:
        """清理批处理对话框资源（在closeEvent中调用）"""
        self._preview_timer.stop()
        self._stop_worker()
        self._signal_manager.disconnect_all()
        self.logger.debug(f"{self.__class__.__name__} 信号已清理")
