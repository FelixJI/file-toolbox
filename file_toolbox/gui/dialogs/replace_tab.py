"""内容替换 Tab:批量替换 Word/Excel/txt 文档内容(简单+正则),自动备份。"""

from PySide6.QtWidgets import (
    QDialog,
    QInputDialog,
    QMessageBox,
    QTableWidgetItem,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_replace import ContentReplaceService, ReplaceOperationType
from file_toolbox.gui.batch_mixin import BatchDialogMixin
from file_toolbox.gui.generated.ui_replace_dialog import Ui_ContentReplaceDialog


class ContentReplaceDialog(QDialog, BatchDialogMixin):
    """批量内容替换对话框(作为 Tab 嵌入)。"""

    SUPPORTED_FORMATS: set[str] = {".docx", ".doc", ".xlsx", ".xls", ".txt", ".md"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_batch_dialog()
        self.ui = Ui_ContentReplaceDialog()
        self.ui.setupUi(self)
        self._svc = ContentReplaceService()
        self._history = JsonHistoryStore()
        self.operations: list[dict] = []
        self.ui.btn_cancel.setVisible(False)
        self._connect_signals()
        self._update_status()

    def _connect_signals(self):
        self.ui.btn_select_files.clicked.connect(lambda: self._select_files(self.ui.list_files))
        self.ui.btn_select_folder.clicked.connect(
            lambda: self._select_folder(self.ui.list_files)
        )
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
    def _add_operation(self, op_type: str):
        params = self._prompt_params(op_type)
        if params is None:
            return
        self.operations.append({"type": op_type, "params": params})
        self._refresh_op_list()
        self._do_refresh_preview()

    def _edit_operation(self):
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

    def _remove_operation(self):
        row = self.ui.list_operations.currentRow()
        if row < 0 or row >= len(self.operations):
            return
        del self.operations[row]
        self._refresh_op_list()
        self._do_refresh_preview()

    def _refresh_op_list(self):
        from PySide6.QtWidgets import QListWidgetItem

        self.ui.list_operations.clear()
        for op in self.operations:
            p = op["params"]
            if op["type"] == ReplaceOperationType.SIMPLE_REPLACE.value:
                label = f"替换: {p.get('find', '')!r} -> {p.get('replace', '')!r}"
            else:
                label = f"正则: /{p.get('pattern', '')}/ -> {p.get('replace', '')!r}"
            self.ui.list_operations.addItem(QListWidgetItem(label))

    def _prompt_params(self, op_type: str, existing: dict | None = None) -> dict | None:
        existing = existing or {}
        if op_type == ReplaceOperationType.SIMPLE_REPLACE.value:
            find, ok = QInputDialog.getText(
                self, "简单替换", "查找文本:", text=existing.get("find", "")
            )
            if not ok or not find:
                return None
            replace, ok = QInputDialog.getText(
                self, "简单替换", f"将 {find!r} 替换为:", text=existing.get("replace", "")
            )
            cs = existing.get("case_sensitive", False)
            return {"find": find, "replace": replace if ok else "", "case_sensitive": cs}
        if op_type == ReplaceOperationType.REGEX_REPLACE.value:
            pattern, ok = QInputDialog.getText(
                self, "正则替换", "正则表达式:", text=existing.get("pattern", "")
            )
            if not ok or not pattern:
                return None
            replace, ok = QInputDialog.getText(
                self, "正则替换", "替换为:", text=existing.get("replace", "")
            )
            ic = existing.get("ignore_case", False)
            return {"pattern": pattern, "replace": replace if ok else "", "ignore_case": ic}
        return None

    # ---------- 预览 / 执行 ----------
    def _do_refresh_preview(self):
        if not self.selected_files or not self.operations:
            self.ui.table_preview.setRowCount(0)
            return
        valid, msg = self._svc.validate_operations(self.operations)
        if not valid:
            QMessageBox.warning(self, "操作无效", msg)
            return
        result = self._svc.preview_replace(list(self.selected_files), self.operations)
        self._render_preview(result)

    def _render_preview(self, result: dict):
        tbl = self.ui.table_preview
        tbl.setRowCount(len(result))
        for row, (f, info) in enumerate(result.items()):
            tbl.setItem(row, 0, QTableWidgetItem(f.name))
            tbl.setItem(row, 1, QTableWidgetItem(str(info["match_count"])))
            tbl.setItem(row, 2, QTableWidgetItem(info["status"]))

    def _execute(self):
        if not self.selected_files or not self.operations:
            QMessageBox.information(self, "提示", "请先选择文件并添加操作。")
            return
        reply = QMessageBox.question(
            self, "确认执行",
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
            self, "完成", f"处理 {success} 个文件, 替换 {total} 处。"
            + ("\n" + "\n".join(errors) if errors else ""),
        )
        self._do_refresh_preview()

    def _show_history(self):
        records = self._history.get_records("replace")
        if not records:
            QMessageBox.information(self, "历史", "暂无历史记录。")
            return
        lines = [
            f"#{r['id']} {r['timestamp'][:19]}  {r['data'].get('files', [])[:1]}"
            for r in records
        ]
        QMessageBox.information(self, "历史", "\n".join(lines))

    def _update_status(self):
        self.ui.label_status.setText(f"已选择 {len(self.selected_files)} 个文件")

    def closeEvent(self, event):
        self._cleanup_batch_dialog()
        try:
            self._svc.close()
        except Exception:
            pass
        super().closeEvent(event)
