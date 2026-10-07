"""重命名 Tab:批量重命名界面(文件选择 + 操作列表 + 预览/执行)。"""

from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QInputDialog,
    QListWidgetItem,
    QMessageBox,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_rename import FileRenameService, OperationType
from file_toolbox.core.rename_execution import PlanEntry, PlanState, RenameResult
from file_toolbox.core.rename_template import RenameTemplateService
from file_toolbox.gui.batch_mixin import BatchDialogMixin
from file_toolbox.gui.controllers.operation_params import OperationParamCollector
from file_toolbox.gui.controllers.qt_prompter import QInputDialogPrompter
from file_toolbox.gui.controllers.rename_controller import RenameController
from file_toolbox.gui.file_models import table_model
from file_toolbox.gui.generated.ui_rename_dialog import Ui_FileRenamerDialog
from file_toolbox.gui.task_lifecycle import TaskLifecycle
from file_toolbox.gui.workers.file_scan_worker import ScannedFile
from file_toolbox.gui.workers.rename_worker import RenameExecuteWorker, RenamePreviewWorker


class FileRenamerDialog(QDialog, BatchDialogMixin):
    """文件重命名对话框(作为 Tab 嵌入)。"""

    SUPPORTED_FORMATS: set[str] = set()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task = TaskLifecycle(self)
        self._init_batch_dialog()
        self.ui = Ui_FileRenamerDialog()
        self.ui.setupUi(self)
        self.ui.list_files.setUniformItemSizes(True)
        self.ui.list_files.setModel(self._file_model)
        self._file_model.full_path = True
        self._preview_plan: dict[Path, PlanEntry] = {}
        self._preview_snapshot: tuple[list[Path], list[dict[str, Any]]] | None = None
        self._preview_pending = False

        self._controller = RenameController()
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = FileRenameService(history_store=self._history)
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
        self.ui.btn_cancel.clicked.connect(self._on_cancel)
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
            label = self._controller.op_label(op["type"])
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
    @property
    def worker(self) -> QThread | None:
        return self._task.worker

    @worker.setter
    def worker(self, worker: QThread | None) -> None:
        self._task.worker = worker

    def _refresh_preview(self) -> None:
        self._preview_snapshot = None
        self._preview_plan = {}
        if isinstance(self.worker, RenamePreviewWorker):
            self._preview_pending = True
            self._task.cancel()
        super()._refresh_preview()

    def _do_refresh_preview(self) -> None:
        self._preview_timer.stop()
        self._preview_snapshot = None
        self._preview_plan = {}
        if not self.selected_files or not self.operations:
            table_model(self.ui.table_preview).replace_rows([])
            return
        if self._task.busy:
            self._preview_pending = True
            return
        if self._task.close_pending:
            return
        self._preview_pending = False
        snapshot = (list(self.selected_files), deepcopy(self.operations))
        worker = RenamePreviewWorker(self._svc, *snapshot, self._file_metadata, self)
        self._requested_snapshot = snapshot
        worker.preview_ok.connect(self._on_preview_ok)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._on_worker_finished)
        self._business_generation = self._import_generation
        self._task.track(worker)
        self._set_busy(True)
        self.ui.label_status.setText("正在计算预览…")
        worker.start()

    def _on_preview_ok(
        self, plan: dict[Path, PlanEntry], rows: list[tuple[list[str], None]]
    ) -> None:
        if (
            self.sender() is not self.worker
            or not self._accept_business_result()
            or self._preview_pending
            or self._task.close_pending
        ):
            return
        if self._requested_snapshot != (self.selected_files, self.operations):
            self._preview_pending = True
            return
        self._preview_snapshot = deepcopy(self._requested_snapshot)
        self._preview_plan = plan
        if isinstance(self.worker, RenamePreviewWorker):
            self._file_metadata.update(self.worker.metadata)
        table_model(self.ui.table_preview).replace_rows(rows)

    def _render_preview(self, result: dict[Path, tuple[Path, str]]) -> None:
        # 显示已有数据；元数据只能由扫描/预览 worker 提供。
        table_model(self.ui.table_preview).replace_rows(
            [
                (
                    [
                        old.name,
                        new.name,
                        self._file_metadata.get(old, ScannedFile(old)).size,
                        self._file_metadata.get(old, ScannedFile(old)).modified,
                        status,
                    ],
                    None,
                )
                for old, (new, status) in result.items()
            ]
        )

    def _execute(self) -> None:
        if self._task.busy:
            return
        if self._preview_snapshot != (self.selected_files, self.operations):
            QMessageBox.information(self, "提示", "请先等待当前文件和规则的预览完成。")
            self._do_refresh_preview()
            return
        ready = {
            old: entry.target
            for old, entry in self._preview_plan.items()
            if entry.state == PlanState.READY
        }
        if not ready:
            QMessageBox.warning(self, "无可执行", "没有就绪的文件(可能全部冲突或无变化)。")
            return
        snapshot = deepcopy(self._preview_snapshot)
        reply = QMessageBox.question(self, "确认执行", f"将重命名 {len(ready)} 个文件,是否继续?")
        if (
            reply != QMessageBox.StandardButton.Yes
            or self._task.busy
            or snapshot != (self.selected_files, self.operations)
            or snapshot != self._preview_snapshot
        ):
            return
        self._preview_timer.stop()
        self._preview_snapshot = None
        worker = RenameExecuteWorker(self._svc, ready, self)
        worker.execute_ok.connect(self._on_execute_ok)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._on_worker_finished)
        self._task.track(worker)
        self._set_busy(True, executing=True)
        self.ui.label_status.setText("正在重命名…")
        worker.start()

    def _on_execute_ok(self, outcome: RenameResult) -> None:
        if self.sender() is not self.worker:
            return
        self._sync_selected_paths_after_rename(outcome.successful)
        self._preview_pending = not (
            outcome.cancelled or bool(self.worker and self.worker.isInterruptionRequested())
        )
        if not self._task.close_pending:
            QMessageBox.information(
                self,
                "已取消" if outcome.cancelled else "完成",
                f"已重命名 {outcome.count} 个文件。"
                + ("\n" + "\n".join(outcome.messages) if outcome.messages else ""),
            )

    def _on_worker_failed(self, message: str) -> None:
        if self.sender() is not self.worker or self._task.close_pending:
            return
        if isinstance(self.worker, RenamePreviewWorker) and (
            self.worker.isInterruptionRequested()
            or self._preview_pending
            or not self._accept_business_result()
            or self._requested_snapshot != (self.selected_files, self.operations)
        ):
            return
        QMessageBox.warning(self, "重命名失败", message)

    def _on_worker_finished(self) -> None:
        if not self._task.finish(self.sender()):
            return
        self._set_busy(False)
        self._update_status()
        if self._task.close_pending or self._resume_import():
            return
        if self._preview_pending:
            self._preview_pending = False
            self._refresh_preview()

    def _set_busy(self, busy: bool, executing: bool = False) -> None:
        self.ui.btn_execute.setEnabled(not busy)
        self.ui.btn_cancel.setVisible(busy)
        for button in (
            self.ui.btn_select_files,
            self.ui.btn_select_folder,
            self.ui.btn_clear_files,
            self.ui.btn_add_prefix,
            self.ui.btn_add_suffix,
            self.ui.btn_replace_text,
            self.ui.btn_regex_replace,
            self.ui.btn_add_number,
            self.ui.btn_delete_chars,
            self.ui.btn_add_date,
            self.ui.btn_edit_operation,
            self.ui.btn_remove_operation,
            self.ui.btn_load_template,
        ):
            button.setEnabled(not (busy and executing))

    def _on_cancel(self) -> None:
        self._preview_pending = False
        self._preview_timer.stop()
        self._task.cancel()
        self.ui.label_status.setText("正在取消，等待当前操作安全结束…")

    def _sync_selected_paths_after_rename(self, rename_map: dict[Path, Path]) -> None:
        self._file_model.replace_paths([rename_map.get(p, p) for p in self.selected_files])
        self._file_metadata = {
            rename_map.get(p, p): value for p, value in self._file_metadata.items()
        }

    def _show_history(self) -> None:
        records = self._history.get_records("rename")
        if not records:
            QMessageBox.information(self, "历史", "暂无历史记录。")
            return
        lines = [self._controller.format_history_line(r) for r in records]
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
        """操作转简短描述(供模板列表展示)。委托给 RenameController。"""
        return self._controller.op_label(op.get("type", ""))

    # ---------- 文件列表变更后刷新状态/预览 ----------
    def _update_status(self) -> None:
        n = len(self.selected_files)
        self.ui.label_status.setText(f"已选择 {n} 个文件")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._task.defer_close(event):
            self._preview_timer.stop()
            return
        self._cleanup_batch_dialog()
        super().closeEvent(event)
