"""重命名 Tab:批量重命名界面(文件选择 + 操作列表 + 预览/执行)。"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_rename import FileRenameService, OperationType
from file_toolbox.gui.batch_mixin import BatchDialogMixin
from file_toolbox.gui.generated.ui_rename_dialog import Ui_FileRenamerDialog


class FileRenamerDialog(QDialog, BatchDialogMixin):
    """文件重命名对话框(作为 Tab 嵌入)。"""

    SUPPORTED_FORMATS: set[str] = set()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_batch_dialog()
        self.ui = Ui_FileRenamerDialog()
        self.ui.setupUi(self)

        self._svc = FileRenameService()
        self._history = JsonHistoryStore()
        self.operations: list[dict] = []

        # 隐藏 Tab 场景下不需要的按钮
        self.ui.btn_cancel.setVisible(False)

        self._connect_signals()
        self._update_status()

    # ---------- 信号连接 ----------
    def _connect_signals(self):
        self.ui.btn_select_files.clicked.connect(lambda: self._select_files(self.ui.list_files))
        self.ui.btn_select_folder.clicked.connect(
            lambda: self._select_folder(self.ui.list_files)
        )
        self.ui.btn_clear_files.clicked.connect(lambda: self._clear_files(self.ui.list_files))
        self.ui.btn_add_prefix.clicked.connect(
            lambda: self._add_operation(OperationType.ADD_PREFIX.value)
        )
        self.ui.btn_add_suffix.clicked.connect(
            lambda: self._add_operation(OperationType.ADD_SUFFIX.value)
        )
        self.ui.btn_replace_text.clicked.connect(
            lambda: self._add_operation(OperationType.REPLACE_TEXT.value)
        )
        self.ui.btn_regex_replace.clicked.connect(
            lambda: self._add_operation(OperationType.REGEX_REPLACE.value)
        )
        self.ui.btn_add_number.clicked.connect(
            lambda: self._add_operation(OperationType.ADD_NUMBER.value)
        )
        self.ui.btn_delete_chars.clicked.connect(
            lambda: self._add_operation(OperationType.DELETE_CHARS.value)
        )
        self.ui.btn_add_date.clicked.connect(
            lambda: self._add_operation(OperationType.ADD_DATE.value)
        )
        self.ui.btn_edit_operation.clicked.connect(self._edit_operation)
        self.ui.btn_remove_operation.clicked.connect(self._remove_operation)
        self.ui.btn_refresh_preview.clicked.connect(self._do_refresh_preview)
        self.ui.btn_execute.clicked.connect(self._execute)
        self.ui.btn_show_history.clicked.connect(self._show_history)

    # ---------- 操作管理 ----------
    def _add_operation(self, op_type: str):
        params = self._prompt_operation_params(op_type)
        if params is None:
            return
        self.operations.append({"type": op_type, "params": params})
        self._refresh_operation_list()
        self._refresh_preview()

    def _edit_operation(self):
        row = self.ui.list_operations.currentRow()
        if row < 0 or row >= len(self.operations):
            return
        op = self.operations[row]
        params = self._prompt_operation_params(op["type"], op["params"])
        if params is None:
            return
        self.operations[row] = {"type": op["type"], "params": params}
        self._refresh_operation_list()
        self._refresh_preview()

    def _remove_operation(self):
        row = self.ui.list_operations.currentRow()
        if row < 0 or row >= len(self.operations):
            return
        del self.operations[row]
        self._refresh_operation_list()
        self._refresh_preview()

    def _refresh_operation_list(self):
        self.ui.list_operations.clear()
        names = {
            OperationType.ADD_PREFIX.value: "添加前缀",
            OperationType.ADD_SUFFIX.value: "添加后缀",
            OperationType.REPLACE_TEXT.value: "替换字符",
            OperationType.REGEX_REPLACE.value: "正则替换",
            OperationType.ADD_NUMBER.value: "添加序号",
            OperationType.DELETE_CHARS.value: "删除字符",
            OperationType.ADD_DATE.value: "添加日期",
        }
        for op in self.operations:
            label = names.get(op["type"], op["type"])
            item = QListWidgetItem(f"{label}: {op['params']}")
            self.ui.list_operations.addItem(item)

    def _prompt_operation_params(self, op_type: str, existing: dict | None = None) -> dict | None:
        """通过输入对话框收集操作参数。existing 用于编辑预填。"""
        existing = existing or {}
        if op_type == OperationType.ADD_PREFIX.value:
            text, ok = QInputDialog.getText(
                self, "添加前缀", "前缀文本:", text=existing.get("text", "")
            )
            return {"text": text} if ok and text else None
        if op_type == OperationType.ADD_SUFFIX.value:
            text, ok = QInputDialog.getText(
                self, "添加后缀", "后缀文本:", text=existing.get("text", "")
            )
            return {"text": text} if ok and text else None
        if op_type == OperationType.REPLACE_TEXT.value:
            find, ok = QInputDialog.getText(
                self, "替换字符", "查找:", text=existing.get("find", "")
            )
            if not ok or not find:
                return None
            replace, ok = QInputDialog.getText(
                self, "替换字符", f"将 {find!r} 替换为:", text=existing.get("replace", "")
            )
            return {"find": find, "replace": replace if ok else ""}
        if op_type == OperationType.REGEX_REPLACE.value:
            pattern, ok = QInputDialog.getText(
                self, "正则替换", "正则表达式:", text=existing.get("pattern", "")
            )
            if not ok or not pattern:
                return None
            replace, ok = QInputDialog.getText(
                self, "正则替换", "替换为:", text=existing.get("replace", "")
            )
            return {"pattern": pattern, "replace": replace if ok else ""}
        if op_type == OperationType.ADD_NUMBER.value:
            start, ok = QInputDialog.getInt(
                self, "添加序号", "起始序号:", value=int(existing.get("start", 1)), min=0
            )
            if not ok:
                return None
            digits, ok = QInputDialog.getInt(
                self, "添加序号", "位数:", value=int(existing.get("digits", 3)), min=1, max=10
            )
            return {"start": start, "digits": digits}
        if op_type == OperationType.DELETE_CHARS.value:
            dtype, ok = QInputDialog.getItem(
                self,
                "删除字符",
                "删除类型:",
                ["prefix", "suffix", "text"],
                0,
                editable=False,
            )
            if not ok:
                return None
            value, ok = QInputDialog.getText(
                self, "删除字符", "值(前缀/后缀为数量,文本为要删除的文本):",
                text=str(existing.get("value", "")),
            )
            return {"delete_type": dtype, "value": value} if ok else None
        if op_type == OperationType.ADD_DATE.value:
            fmt, ok = QInputDialog.getText(
                self, "添加日期", "日期格式:", text=existing.get("format", "%Y%m%d")
            )
            return {"format": fmt if ok else "%Y%m%d"} if ok else None
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
        result = self._svc.apply_operations(self.selected_files, self.operations)
        self._render_preview(result)

    def _render_preview(self, result: dict):
        self.ui.table_preview.setRowCount(len(result))
        for row, (old, (new, status)) in enumerate(result.items()):
            self.ui.table_preview.setItem(row, 0, QTableWidgetItem(old.name))
            self.ui.table_preview.setItem(row, 1, QTableWidgetItem(new.name))
            self.ui.table_preview.setItem(
                row, 2, QTableWidgetItem(self._format_size(old.stat().st_size if old.exists() else 0))
            )
            self.ui.table_preview.setItem(row, 3, QTableWidgetItem(""))
            self.ui.table_preview.setItem(row, 4, QTableWidgetItem(status))

    def _execute(self):
        if not self.selected_files or not self.operations:
            QMessageBox.information(self, "提示", "请先选择文件并添加操作。")
            return
        valid, msg = self._svc.validate_operations(self.operations)
        if not valid:
            QMessageBox.warning(self, "操作无效", msg)
            return
        result = self._svc.apply_operations(self.selected_files, self.operations)
        ready = {old: new for old, (new, s) in result.items() if "准备" in s}
        if not ready:
            QMessageBox.warning(self, "无可执行", "没有就绪的文件(可能全部冲突或无变化)。")
            return
        reply = QMessageBox.question(
            self, "确认执行", f"将重命名 {len(ready)} 个文件,是否继续?"
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        count, errors = self._svc.execute_rename(ready)
        # 记录历史(用于撤销)
        self._history.add_record(
            "rename", {"rename_map": {str(k): str(v) for k, v in ready.items()}}
        )
        QMessageBox.information(self, "完成", f"已重命名 {count} 个文件。" + ("\n" + "\n".join(errors) if errors else ""))
        self._do_refresh_preview()

    def _show_history(self):
        records = self._history.get_records("rename")
        if not records:
            QMessageBox.information(self, "历史", "暂无历史记录。")
            return
        lines = [f"#{r['id']} {r['timestamp'][:19]}  {len(r['data'].get('rename_map', {}))} 个文件" for r in records]
        QMessageBox.information(self, "历史", "\n".join(lines))

    # ---------- 文件列表变更后刷新状态/预览 ----------
    def _update_status(self):
        n = len(self.selected_files)
        self.ui.label_status.setText(f"已选择 {n} 个文件")

    def _select_files(self, list_widget=None, auto_preview=True):
        super()._select_files(list_widget, auto_preview)
        self._update_status()

    def _select_folder(self, list_widget=None, ask_recursive=True, auto_preview=True):
        super()._select_folder(list_widget, ask_recursive, auto_preview)
        self._update_status()

    def _clear_files(self, list_widget=None, table_widget=None):
        super()._clear_files(list_widget, table_widget)
        self._update_status()

    def closeEvent(self, event):
        self._cleanup_batch_dialog()
        super().closeEvent(event)
