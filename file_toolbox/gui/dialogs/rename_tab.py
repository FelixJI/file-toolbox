"""重命名 Tab:批量重命名界面(文件选择 + 操作列表 + 预览/执行)。"""

from pathlib import Path
from typing import Any

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QInputDialog,
    QListWidgetItem,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_rename import FileRenameService, OperationType
from file_toolbox.core.rename_template import RenameTemplateService
from file_toolbox.gui.batch_mixin import BatchDialogMixin
from file_toolbox.gui.controllers.operation_params import OperationParamCollector
from file_toolbox.gui.controllers.qt_prompter import QInputDialogPrompter
from file_toolbox.gui.generated.ui_rename_dialog import Ui_FileRenamerDialog


class FileRenamerDialog(QDialog, BatchDialogMixin):
    """文件重命名对话框(作为 Tab 嵌入)。"""

    SUPPORTED_FORMATS: set[str] = set()

    # 操作类型 -> 中文标签(操作列表展示、模板描述共用)
    _OP_LABELS: dict[str, str] = {
        OperationType.ADD_PREFIX.value: "添加前缀",
        OperationType.ADD_SUFFIX.value: "添加后缀",
        OperationType.REPLACE_TEXT.value: "替换字符",
        OperationType.REGEX_REPLACE.value: "正则替换",
        OperationType.ADD_NUMBER.value: "添加序号",
        OperationType.DELETE_CHARS.value: "删除字符",
        OperationType.ADD_DATE.value: "添加日期",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_batch_dialog()
        self.ui = Ui_FileRenamerDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI code

        self._svc = FileRenameService()
        self._history = JsonHistoryStore()
        self._template_svc = RenameTemplateService()
        self.operations: list[dict[str, Any]] = []

        # 隐藏 Tab 场景下不需要的按钮
        self.ui.btn_cancel.setVisible(False)

        self._connect_signals()
        self._update_status()

    # ---------- 信号连接 ----------
    def _connect_signals(self) -> None:
        self.ui.btn_select_files.clicked.connect(lambda: self._select_files(self.ui.list_files))
        self.ui.btn_select_folder.clicked.connect(lambda: self._select_folder(self.ui.list_files))
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
        self.ui.btn_load_template.clicked.connect(self._load_template)
        self.ui.btn_save_template.clicked.connect(self._save_template)

    # ---------- 操作管理 ----------
    def _add_operation(self, op_type: str) -> None:
        params = self._prompt_operation_params(op_type)
        if params is None:
            return
        self.operations.append({"type": op_type, "params": params})
        self._refresh_operation_list()
        self._refresh_preview()

    def _edit_operation(self) -> None:
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

    def _remove_operation(self) -> None:
        row = self.ui.list_operations.currentRow()
        if row < 0 or row >= len(self.operations):
            return
        del self.operations[row]
        self._refresh_operation_list()
        self._refresh_preview()

    def _refresh_operation_list(self) -> None:
        self.ui.list_operations.clear()
        for op in self.operations:
            label = self._OP_LABELS.get(op["type"], op["type"])
            item = QListWidgetItem(f"{label}: {op['params']}")
            self.ui.list_operations.addItem(item)

    def _prompt_operation_params(
        self, op_type: str, existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """通过输入对话框收集操作参数。existing 用于编辑预填。

        委托给 OperationParamCollector(纯逻辑,可无 Qt 单测),View 仅提供 QInputDialog 实现。
        """
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
        result = self._svc.apply_operations(self.selected_files, self.operations)
        self._render_preview(result)

    def _render_preview(self, result: dict[Path, tuple[Path, str]]) -> None:
        self.ui.table_preview.setRowCount(len(result))
        for row, (old, (new, status)) in enumerate(result.items()):
            info = self._svc.get_file_info(old)
            self.ui.table_preview.setItem(row, 0, QTableWidgetItem(old.name))
            self.ui.table_preview.setItem(row, 1, QTableWidgetItem(new.name))
            self.ui.table_preview.setItem(row, 2, QTableWidgetItem(info["size_str"]))
            self.ui.table_preview.setItem(row, 3, QTableWidgetItem(info["modified_str"]))
            self.ui.table_preview.setItem(row, 4, QTableWidgetItem(status))

    def _execute(self) -> None:
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
        reply = QMessageBox.question(self, "确认执行", f"将重命名 {len(ready)} 个文件,是否继续?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        count, errors = self._svc.execute_rename(ready)
        # 记录历史(用于撤销)
        self._history.add_record(
            "rename", {"rename_map": {str(k): str(v) for k, v in ready.items()}}
        )
        QMessageBox.information(
            self,
            "完成",
            f"已重命名 {count} 个文件。" + ("\n" + "\n".join(errors) if errors else ""),
        )
        self._do_refresh_preview()

    def _show_history(self) -> None:
        records = self._history.get_records("rename")
        if not records:
            QMessageBox.information(self, "历史", "暂无历史记录。")
            return
        lines = [
            f"#{r['id']} {r['timestamp'][:19]}  {len(r['data'].get('rename_map', {}))} 个文件"
            for r in records
        ]
        QMessageBox.information(self, "历史", "\n".join(lines))

    # ---------- 模板管理 ----------
    def _load_template(self) -> None:
        """加载已保存的重命名模板,替换当前操作列表。"""
        templates = self._template_svc.get_all_templates()
        if not templates:
            QMessageBox.information(self, "加载模板", "暂无已保存的模板。")
            return
        # 显示名:模板名 + 操作描述
        labels = []
        for t in templates:
            ops_desc = ", ".join(self._op_label(o) for o in t["operations"])
            labels.append(f"{t['name']}  ({ops_desc})")
        choice, ok = QInputDialog.getItem(self, "加载模板", "选择模板:", labels, 0, editable=False)
        if not ok:
            return
        idx = labels.index(choice)
        chosen = templates[idx]
        # 替换当前操作列表
        self.operations = [dict(o) for o in chosen["operations"]]
        self._refresh_operation_list()
        self._refresh_preview()
        QMessageBox.information(self, "加载模板", f"已加载模板「{chosen['name']}」。")

    def _save_template(self) -> None:
        """把当前操作列表保存为模板。同名时提示覆盖。"""
        if not self.operations:
            QMessageBox.information(self, "保存模板", "当前没有操作可保存。")
            return
        name, ok = QInputDialog.getText(self, "保存模板", "模板名称:")
        if not ok or not name.strip():
            return
        name = name.strip()
        exists = self._template_svc.template_exists(name)
        if exists:
            reply = QMessageBox.question(self, "覆盖确认", f"模板「{name}」已存在,是否覆盖?")
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._template_svc.update_template(name, self.operations)
        else:
            self._template_svc.add_template(name, self.operations)
        QMessageBox.information(self, "保存模板", f"已保存模板「{name}」。")

    def _op_label(self, op: dict[str, Any]) -> str:
        """操作转简短描述(供模板列表展示)。"""
        op_type = op.get("type", "")
        op_type_str = op_type if isinstance(op_type, str) else ""
        return self._OP_LABELS.get(op_type_str, op_type_str)

    # ---------- 文件列表变更后刷新状态/预览 ----------
    def _update_status(self) -> None:
        n = len(self.selected_files)
        self.ui.label_status.setText(f"已选择 {n} 个文件")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cleanup_batch_dialog()
        super().closeEvent(event)
