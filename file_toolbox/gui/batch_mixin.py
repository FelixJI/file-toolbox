"""批处理对话框混入类 - 提供文件选择、预览、进度显示等公共功能。"""

import contextlib
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, QThread, QTimer
from PySide6.QtWidgets import QFileDialog, QListWidget, QMessageBox, QTableWidget, QWidget

from file_toolbox.common.file_utils import format_file_size, get_file_info

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


class BatchDialogMixin:
    """批处理对话框混入类，提供文件选择、预览刷新和工作线程管理功能"""

    SUPPORTED_FORMATS: set[str] = set()
    PREVIEW_DEBOUNCE_MS: int = 200  # 预览防抖(毫秒)

    # 子类(QDialog 子类,如 PDFGeneratorDialog)必须提供 logger。
    # 声明类型而非赋值:mypy 据此认定 self.logger 合法,且不在此引入实例属性。
    logger: logging.Logger
    # worker 可能是任意 QThread 子类(如 PdfGenerateWorker),运行期可为 None。
    # 声明类级类型,避免 mypy 从 self.worker = None 推断出过于窄的 None 类型。
    worker: QThread | None

    def _init_batch_dialog(self) -> None:
        """初始化批处理对话框功能（在__init__中调用）"""
        self.selected_files: list[Path] = []
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
        self, list_widget: QListWidget | None = None, auto_preview: bool = True
    ) -> None:
        """选择文件"""
        files, _ = QFileDialog.getOpenFileNames(
            cast(QWidget, self), "选择文件", "", self._get_file_filter()
        )
        if files:
            added_count = 0
            for file_path in files:
                path = Path(file_path)
                if self._is_file_supported(path) and path not in self.selected_files:
                    self.selected_files.append(path)
                    if list_widget:
                        list_widget.addItem(str(path))
                    added_count += 1
            if added_count > 0:
                self._update_status()
                if auto_preview:
                    self._refresh_preview()

    def _select_folder(
        self,
        list_widget: QListWidget | None = None,
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

        if recursive:
            if self.SUPPORTED_FORMATS:
                files: list[Path] = []
                for ext in self.SUPPORTED_FORMATS:
                    files.extend(
                        f for f in folder_path.rglob(f"*{ext}") if not self._is_temp_file(f)
                    )
            else:
                files = [
                    f for f in folder_path.rglob("*") if f.is_file() and not self._is_temp_file(f)
                ]
        else:
            files = [f for f in folder_path.iterdir() if f.is_file() and self._is_file_supported(f)]

        added_count = 0
        for file_path in files:
            if file_path not in self.selected_files:
                self.selected_files.append(file_path)
                if list_widget:
                    list_widget.addItem(str(file_path))
                added_count += 1

        if added_count > 0:
            self._update_status()
            if auto_preview:
                self._refresh_preview()

    def _clear_files(
        self, list_widget: QListWidget | None = None, table_widget: QTableWidget | None = None
    ) -> None:
        """清空文件列表"""
        self.selected_files.clear()
        if list_widget:
            list_widget.clear()
        if table_widget:
            table_widget.setRowCount(0)
        self._update_status()

    def _refresh_preview(self) -> None:
        """刷新预览（带防抖机制）"""
        self._preview_timer.stop()
        self._preview_timer.start(self.PREVIEW_DEBOUNCE_MS)

    def _do_refresh_preview(self) -> None:
        """执行刷新预览（子类必须实现）"""
        pass

    def _stop_worker(self, timeout_ms: int = WORKER_STOP_TIMEOUT_MS) -> None:
        """停止工作线程"""
        if self.worker and self.worker.isRunning():
            if hasattr(self.worker, "cancel"):
                self.worker.cancel()
            self.worker.quit()
            if not self.worker.wait(timeout_ms):
                self.logger.warning(
                    f"{self.__class__.__name__}: Worker 未能在 {timeout_ms}ms 内停止，强制终止"
                )
                self.worker.terminate()
                self.worker.wait(1000)
        self.worker = None

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
