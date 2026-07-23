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
from file_toolbox.gui.generated.ui_replace_dialog import Ui_ContentReplaceDialog


class ContentReplaceDialog(QDialog, BatchDialogMixin):
    """批量内容替换对话框(作为 Tab 嵌入)。"""

    SUPPORTED_FORMATS: set[str] = {".docx", ".doc", ".xlsx", ".xls", ".txt", ".md"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_batch_dialog()
        self.ui = Ui_ContentReplaceDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI code
        self._svc = ContentReplaceService()
        self._history = JsonHistoryStore()
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
            p = op["params"]
            if op["type"] == ReplaceOperationType.SIMPLE_REPLACE.value:
                label = f"替换: {p.get('find', '')!r} -> {p.get('replace', '')!r}"
            else:
                label = f"正则: /{p.get('pattern', '')}/ -> {p.get('replace', '')!r}"
            self.ui.list_operations.addItem(QListWidgetItem(label))

    def _prompt_params(
        self, op_type: str, existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """委托给 OperationParamCollector(纯逻辑),View 仅提供 QInputDialog 实现。"""
        collector = OperationParamCollector(QInputDialogPrompter(self))
        return collector.collect(op_type, existing)

    # ---------- 预览 / 执行 ----------
    def _do_refresh_preview(self) -> None:
        if not self.selected_files or not self.operations:
            self.ui.table_preview.setRowCount(0)
            return
        valid, msg = self._svc.validate_operations(self.operations)
        if not valid:
            QMessageBox.warning(self, "操作无效", msg)
            return
        result = self._svc.preview_replace(list(self.selected_files), self.operations)
        self._render_preview(result)

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
        reply = QMessageBox.question(
            self,
            "确认执行",
            f"将对 {len(self.selected_files)} 个文件执行替换,执行前自动备份。是否继续?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        success, total, errors = self._svc.execute_replace(
            list(self.selected_files), self.operations
        )
        self._history.add_record(
            "replace",
            {"files": [str(f) for f in self.selected_files], "operations": self.operations},
        )
        QMessageBox.information(
            self,
            "完成",
            f"处理 {success} 个文件, 替换 {total} 处。"
            + ("\n" + "\n".join(errors) if errors else ""),
        )
        self._do_refresh_preview()

    def _show_history(self) -> None:
        records = self._history.get_records("replace")
        if not records:
            QMessageBox.information(self, "历史", "暂无历史记录。")
            return
        lines = [
            f"#{r['id']} {r['timestamp'][:19]}  {r['data'].get('files', [])[:1]}" for r in records
        ]
        QMessageBox.information(self, "历史", "\n".join(lines))

    def _update_status(self) -> None:
        self.ui.label_status.setText(f"已选择 {len(self.selected_files)} 个文件")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cleanup_batch_dialog()
        with contextlib.suppress(Exception):
            self._svc.close()
        super().closeEvent(event)
