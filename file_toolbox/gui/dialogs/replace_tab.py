"""内容替换 Tab:批量替换 Word/Excel/txt 文档内容(简单+正则),自动备份。"""

import contextlib
from pathlib import Path
from typing import Any

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_replace import ContentReplaceService, ReplaceOperationType
from file_toolbox.gui.batch_mixin import BatchDialogMixin
from file_toolbox.gui.controllers.operation_params import OperationParamCollector
from file_toolbox.gui.controllers.qt_prompter import QInputDialogPrompter
from file_toolbox.gui.controllers.replace_controller import ReplaceController
from file_toolbox.gui.generated.ui_replace_dialog import Ui_ContentReplaceDialog


class ContentReplaceDialog(QDialog, BatchDialogMixin):
    """批量内容替换对话框(作为 Tab 嵌入)。"""

    SUPPORTED_FORMATS: set[str] = {".docx", ".doc", ".xlsx", ".xls", ".txt", ".md"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_batch_dialog()
        self.ui = Ui_ContentReplaceDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI code
        self._controller = ReplaceController()
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = ContentReplaceService(history_store=self._history)
        self.operations: list[dict[str, Any]] = []
        self.ui.btn_cancel.setVisible(False)
        self._connect_signals()
        self._update_status()

    def _connect_signals(self) -> None:
        self.ui.btn_select_files.clicked.connect(lambda: self._select_files(self.ui.list_files))
        self.ui.btn_select_folder.clicked.connect(lambda: self._select_folder(self.ui.list_files))
        self.ui.btn_clear_files.clicked.connect(lambda: self._clear_files(self.ui.list_files))
        self.ui.btn_simple_replace.clicked.connect(
            lambda: self._add_operation(ReplaceOperationType.SIMPLE_REPLACE.value)
        )
        self.ui.btn_regex_replace.clicked.connect(
            lambda: self._add_operation(ReplaceOperationType.REGEX_REPLACE.value)
        )
        self.ui.btn_edit_operation.clicked.connect(self._edit_operation)
        self.ui.btn_remove_operation.clicked.connect(self._remove_operation)
        self.ui.btn_refresh_preview.clicked.connect(self._do_refresh_preview)
        self.ui.btn_execute.clicked.connect(self._execute)
        self.ui.btn_show_history.clicked.connect(self._show_history)
        self.ui.btn_cancel.clicked.connect(self._on_cancel)

    # ---------- 操作管理 ----------
    def _add_operation(self, op_type: str) -> None:
        params = self._prompt_params(op_type)
        if params is None:
            return
        self.operations.append({"type": op_type, "params": params})
        self._refresh_op_list()
        self._do_refresh_preview()

    def _edit_operation(self) -> None:
        row = self.ui.list_operations.currentRow()
        if row < 0 or row >= len(self.operations):
            return
        op = self.operations[row]
        params = self._prompt_params(op["type"], op["params"])
        if params is None:
            return
        self.operations[row] = {"type": op["type"], "params": params}
        self._refresh_op_list()
        self._do_refresh_preview()

    def _remove_operation(self) -> None:
        row = self.ui.list_operations.currentRow()
        if row < 0 or row >= len(self.operations):
            return
        del self.operations[row]
        self._refresh_op_list()
        self._do_refresh_preview()

    def _refresh_op_list(self) -> None:
        from PySide6.QtWidgets import QListWidgetItem

        self.ui.list_operations.clear()
        for op in self.operations:
            label = self._controller.format_op_label(op)
            self.ui.list_operations.addItem(QListWidgetItem(label))

    def _prompt_params(
        self, op_type: str, existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """委托给 OperationParamCollector(纯逻辑),View 仅提供 QInputDialog 实现。"""
        collector = OperationParamCollector(QInputDialogPrompter(self))
        return collector.collect(op_type, existing)

    # ---------- 预览 / 执行 ----------
    # Word/Excel COM 的 Dispatch/Open 单文件可达数十秒:预览与执行均经 worker
    # 移入后台线程(ComSession 负责 COM 线程初始化),主线程只做校验与结果渲染,
    # 避免 freeze_watchdog 转储的 30-45s 冻结。结果经信号(queued)回主线程。
    def _worker_busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def _do_refresh_preview(self) -> None:
        if not self.selected_files or not self.operations:
            self.ui.table_preview.setRowCount(0)
            return
        if self._worker_busy():
            return  # 忙碌期间操作按钮已禁用,此处兜底防抖动定时器重入
        valid, msg = self._svc.validate_operations(self.operations)
        if not valid:
            QMessageBox.warning(self, "操作无效", msg)
            return
        from file_toolbox.gui.workers.replace_worker import ReplacePreviewWorker

        worker = ReplacePreviewWorker(
            self._svc, list(self.selected_files), self.operations, parent=self
        )
        worker.preview_ok.connect(self._on_preview_ok)
        worker.failed.connect(self._on_worker_failed)
        self._set_ui_enabled(False)
        self.ui.label_status.setText("正在预览匹配...")
        self.ui.progress_bar.setRange(0, 0)  # 不定态:预览无逐文件进度回调
        self.ui.progress_bar.setVisible(True)
        self.worker = worker
        worker.start()

    def _on_preview_ok(self, result: dict[Path, dict[str, Any]]) -> None:
        self.worker = None
        self._render_preview(result)
        self._restore_ui()

    def _render_preview(self, result: dict[Path, dict[str, Any]]) -> None:
        tbl = self.ui.table_preview
        tbl.setRowCount(len(result))
        for row, (f, info) in enumerate(result.items()):
            tbl.setItem(row, 0, QTableWidgetItem(f.name))
            tbl.setItem(row, 1, QTableWidgetItem(str(info["match_count"])))
            tbl.setItem(row, 2, QTableWidgetItem(info["status"]))

    def _execute(self) -> None:
        if not self.selected_files or not self.operations:
            QMessageBox.information(self, "提示", "请先选择文件并添加操作。")
            return
        if self._worker_busy():
            return
        reply = QMessageBox.question(
            self,
            "确认执行",
            f"将对 {len(self.selected_files)} 个文件执行替换,执行前自动备份。是否继续?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from file_toolbox.gui.workers.replace_worker import ReplaceExecuteWorker

        worker = ReplaceExecuteWorker(
            self._svc,
            list(self.selected_files),
            self.operations,
            keep_new_format=self.ui.chk_keep_new_format.isChecked(),
            parent=self,
        )
        worker.progress.connect(self._on_execute_progress)
        worker.execute_ok.connect(self._on_execute_ok)
        worker.failed.connect(self._on_worker_failed)
        self._set_ui_enabled(False)
        self.ui.label_status.setText("正在执行替换...")
        self.ui.progress_bar.setRange(0, len(self.selected_files))
        self.ui.progress_bar.setValue(0)
        self.ui.progress_bar.setVisible(True)
        self.worker = worker
        worker.start()

    def _on_execute_progress(self, processed: int, total: int) -> None:
        self.ui.progress_bar.setMaximum(total)
        self.ui.progress_bar.setValue(processed)

    def _on_execute_ok(self, success: int, total: int, errors: list[str]) -> None:
        self.worker = None
        self._restore_ui()
        # 历史记录已下沉 ContentReplaceService.execute_replace(注入了 history_store)
        QMessageBox.information(
            self,
            "完成",
            f"处理 {success} 个文件, 替换 {total} 处。"
            + ("\n" + "\n".join(errors) if errors else ""),
        )
        self._do_refresh_preview()

    def _on_worker_failed(self, msg: str) -> None:
        self.worker = None
        self._restore_ui()
        QMessageBox.critical(self, "替换失败", msg)

    def _on_cancel(self) -> None:
        if self.worker is not None and hasattr(self.worker, "cancel"):
            self.worker.cancel()
        self.ui.label_status.setText("正在取消(当前文件完成后停止)...")

    def _stop_worker(self, timeout_ms: int = 30000) -> None:
        """停止替换 worker —— 协作式取消 + 较长等待,绝不强制 terminate。

        覆盖 BatchDialogMixin._stop_worker:worker 持有 COM 对象,强制 terminate
        (QThread.terminate)会在线程仍处于 win32com/Word 调用中途时杀掉它,可能泄漏
        Office 进程、留下未初始化 COM、甚至死锁。cancel() 仅在文件间生效,大文档
        处理(>3s)会让基类 wait(3000) 超时进而触发 terminate —— 必须禁用。
        与 pdf_tab._stop_worker 同构(见其注释)。
        """
        if self.worker and self.worker.isRunning():
            if hasattr(self.worker, "cancel"):
                self.worker.cancel()
            self.worker.quit()
            if not self.worker.wait(timeout_ms):
                self.logger.warning(
                    f"{self.__class__.__name__}: 替换 worker 未能在 {timeout_ms}ms 内停止"
                    "(可能仍在处理大文档);不强制 terminate 以避免 COM 泄漏"
                )
        self.worker = None

    def _set_ui_enabled(self, enabled: bool) -> None:
        """预览/执行进行中禁用操作按钮并显示取消;完成则反之。"""
        for btn in (
            self.ui.btn_select_files,
            self.ui.btn_select_folder,
            self.ui.btn_clear_files,
            self.ui.btn_simple_replace,
            self.ui.btn_regex_replace,
            self.ui.btn_edit_operation,
            self.ui.btn_remove_operation,
            self.ui.btn_refresh_preview,
            self.ui.btn_execute,
            self.ui.btn_show_history,
        ):
            btn.setEnabled(enabled)
        self.ui.btn_cancel.setVisible(not enabled)

    def _restore_ui(self) -> None:
        """worker 结束(成功/失败/取消)后恢复控件状态。"""
        self._set_ui_enabled(True)
        self.ui.progress_bar.setRange(0, 100)
        self.ui.progress_bar.setValue(0)
        self.ui.progress_bar.setVisible(False)
        self._update_status()

    def _show_history(self) -> None:
        records = self._history.get_records("replace")
        if not records:
            QMessageBox.information(self, "历史", "暂无历史记录。")
            return
        lines = [self._controller.format_history_line(r) for r in records]
        QMessageBox.information(self, "历史", "\n".join(lines))

    def _update_status(self) -> None:
        self.ui.label_status.setText(f"已选择 {len(self.selected_files)} 个文件")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cleanup_batch_dialog()
        with contextlib.suppress(Exception):
            self._svc.close()
        super().closeEvent(event)
