"""内容替换 Tab:批量替换 Word/Excel/txt 文档内容(简单+正则),自动备份。"""

import contextlib
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QMessageBox,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_replace import ContentReplaceService, ReplaceOperationType
from file_toolbox.core.office_capability import format_statuses, tool_capability_statuses
from file_toolbox.gui.batch_mixin import BatchDialogMixin
from file_toolbox.gui.controllers.operation_params import OperationParamCollector
from file_toolbox.gui.controllers.qt_prompter import QInputDialogPrompter
from file_toolbox.gui.controllers.replace_controller import ReplaceController
from file_toolbox.gui.file_models import table_model
from file_toolbox.gui.generated.ui_replace_dialog import Ui_ContentReplaceDialog
from file_toolbox.gui.task_lifecycle import TaskLifecycle


class ContentReplaceDialog(QDialog, BatchDialogMixin):
    """批量内容替换对话框(作为 Tab 嵌入)。"""

    SUPPORTED_FORMATS: set[str] = {".docx", ".doc", ".xlsx", ".xls", ".txt", ".md"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 生命周期句柄先建:_init_batch_dialog 里 self.worker = None 经下方属性转发写入 task
        self._task = TaskLifecycle(self)
        self._init_batch_dialog()
        self.ui = Ui_ContentReplaceDialog()
        self.ui.setupUi(self)
        self.ui.list_files.setUniformItemSizes(True)
        self.ui.list_files.setModel(self._file_model)
        self._file_model.full_path = True
        self._controller = ReplaceController()
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = ContentReplaceService(history_store=self._history)
        self.operations: list[dict[str, Any]] = []
        # 预览运行期间的变更(增删改操作/文件)挂起于此,worker 结束后自动重跑
        self._preview_pending = False
        self.ui.btn_cancel.setVisible(False)
        self._connect_signals()
        self._refresh_capability_hint()
        self._update_status()

    def _refresh_capability_hint(self) -> None:
        """能力提示:按文件类型展示 Office 状态(消费统一登记声明,预筛结论)。

        txt/md 为纯文件处理,不因任何引擎缺失受影响;页面不禁用任何按钮,
        依赖缺失只在执行期对对应操作报错。除构造时外,真实 worker finished
        后也会刷新(F11):预览/替换/旧格式转换的 COM 成功已在进程内登记
        verified 证据,同一页面应及时从"检测失败/预检"更新为"已验证"。
        """
        statuses = format_statuses(tool_capability_statuses("replace"))
        self.ui.label_file_filter.setWordWrap(True)
        self.ui.label_file_filter.setText(
            f"支持格式: docx, doc, xlsx, xls, txt, md；txt/md 纯文件处理；{statuses}"
        )

    # 兼容旧 worker 字段:单一事实在 TaskLifecycle,读写均转发;只有真实
    # finished(task.finish 精确身份校验)才清空,结果信号不提前释放引用。
    @property
    def worker(self) -> QThread | None:
        return self._task.worker

    @worker.setter
    def worker(self, value: QThread | None) -> None:
        self._task.worker = value

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
    # 增删改后走 mixin 的防抖 _refresh_preview(200ms)而非立即 _do_refresh_preview:
    # 连续添加多条操作时合并为一次预览,且预览不再禁用操作按钮(见 _set_preview_busy),
    # 不会出现"每加一条就得等一次 COM 预览(单文件可达数十秒)"的阻塞。
    def _add_operation(self, op_type: str) -> None:
        params = self._prompt_params(op_type)
        if params is None:
            return
        self.operations.append({"type": op_type, "params": params})
        self._refresh_op_list()
        self._refresh_preview()

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
        self._refresh_preview()

    def _remove_operation(self) -> None:
        row = self.ui.list_operations.currentRow()
        if row < 0 or row >= len(self.operations):
            return
        del self.operations[row]
        self._refresh_op_list()
        self._refresh_preview()

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
    # 避免 freeze_watchdog 转储的 30-45s 冻结。结果经信号(queued)回主线程;
    # 线程引用/控件恢复只在真实 finished(task.finish)后进行,预览期间对操作/文件
    # 的变更挂起为 _preview_pending,同样等真实 finished 后重跑。
    def _do_refresh_preview(self) -> None:
        if not self.selected_files or not self.operations:
            table_model(self.ui.table_preview).replace_rows([])
            if self._task.busy:
                # 清空发生在老预览运行中:挂起待刷新,老结果返回时被丢弃,
                # 空表不会被旧结果覆盖
                self._preview_pending = True
            return
        if self._task.busy:
            # 预览期间操作/文件仍可编辑(见 _set_preview_busy),防抖定时器或手动
            # 刷新的重入不能像旧实现那样直接丢弃——否则预览会停留在旧操作集上;
            # 挂起为待刷新,当前 worker 真实结束后由 _on_worker_finished 重跑
            self._preview_pending = True
            return
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
        worker.finished.connect(self._on_worker_finished)
        # 启动即清挂起标记:本次启动就是最新状态的消费
        self._preview_pending = False
        self._set_preview_busy(True)
        self.ui.label_status.setText("正在预览匹配...")
        self.ui.progress_bar.setRange(0, 0)  # 不定态:预览无逐文件进度回调
        self.ui.progress_bar.setVisible(True)
        self._business_generation = self._import_generation
        self._task.track(worker)
        worker.start()

    def _rerun_pending_preview(self) -> None:
        """预览运行期间有变更被挂起时,结束后用最新状态自动重跑一次。"""
        if self._preview_pending:
            self._preview_pending = False
            self._refresh_preview()

    def _on_preview_ok(self, result: dict[Path, dict[str, Any]]) -> None:
        if not self._accept_business_result():
            return
        if self._preview_pending:
            # 运行期间操作/文件已变:这份结果过期,丢弃;真实 finished 后用
            # 最新状态重跑(含清空后的空表),空表不被旧结果覆盖
            return
        self._render_preview(result)

    def _render_preview(self, result: dict[Path, dict[str, Any]]) -> None:
        table_model(self.ui.table_preview).replace_rows(
            [
                ([path.name, str(info["match_count"]), info["status"], "", ""], None)
                for path, info in result.items()
            ]
        )

    def _refresh_preview(self) -> None:
        if self._task.busy:
            self._preview_pending = True
        super()._refresh_preview()

    def _execute(self) -> None:
        if not self.selected_files or not self.operations:
            QMessageBox.information(self, "提示", "请先选择文件并添加操作。")
            return
        # 任务未在真实 finished 中释放(或预览仍在跑/延迟关闭中)时拒绝重复启动,
        # 不以 isRunning() 为准——排队的 finished 尚未消费时同样不能开下一轮
        if self._task.busy:
            return
        reply = QMessageBox.question(
            self,
            "确认执行",
            f"将对 {len(self.selected_files)} 个文件执行替换,执行前自动备份。是否继续?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        # 确认框的嵌套事件循环期间,防抖预览可能已启动:Yes 返回后必须复查,
        # 否则 track 拋错或与预览 worker 并发改写文件
        if self._task.busy:
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
        worker.finished.connect(self._on_worker_finished)
        self._set_ui_enabled(False)
        self.ui.label_status.setText("正在执行替换...")
        self.ui.progress_bar.setRange(0, len(self.selected_files))
        self.ui.progress_bar.setValue(0)
        self.ui.progress_bar.setVisible(True)
        self._business_generation = self._import_generation
        self._task.track(worker)
        worker.start()

    def _on_execute_progress(self, processed: int, total: int) -> None:
        if not self._accept_business_result():
            return
        self.ui.progress_bar.setMaximum(total)
        self.ui.progress_bar.setValue(processed)

    def _on_execute_ok(self, success: int, total: int, errors: list[str]) -> None:
        """结果槽:只展示结果;引用释放/控件恢复/预览重跑等真实 finished。"""
        if not self._accept_business_result():
            return
        # 执行改写了文件:预览已过期,标记待刷新,真实 finished 后重跑。
        # 必须先于下方模态框设置——information 的嵌套事件循环可能先投递并消费
        # finished(_on_worker_finished 读 _preview_pending),迟设会漏掉自动刷新。
        self._preview_pending = True
        # 历史记录已下沉 ContentReplaceService.execute_replace(注入了 history_store)
        if not self._task.close_pending:
            QMessageBox.information(
                self,
                "完成",
                f"处理 {success} 个文件, 替换 {total} 处。"
                + ("\n" + "\n".join(errors) if errors else ""),
            )

    def _on_worker_failed(self, msg: str) -> None:
        if not self._accept_business_result():
            return
        if not self._task.close_pending:
            QMessageBox.critical(self, "替换失败", msg)
        # 失败后控件恢复与挂起标记的消费均在真实 finished(_on_worker_finished)

    def _on_worker_finished(self) -> None:
        """真实 finished 后释放线程、恢复控件并消费挂起的预览刷新。

        同时刷新能力提示(F11):预览/执行/失败收尾共享本入口,真实 COM
        成功登记的 verified 证据在同一页面即时呈现,无需重建页面。
        """
        if not self._task.finish(self.sender()):
            return
        self._restore_ui()
        self._refresh_capability_hint()
        if self._task.close_pending:
            return  # 关闭中:不重跑预览,交给 TaskLifecycle 续接关闭
        if not self._resume_import():
            self._rerun_pending_preview()

    def _on_cancel(self) -> None:
        self._preview_pending = False
        self._preview_timer.stop()
        if not self._cancel_import():
            self._task.cancel()
        self.ui.label_status.setText("正在取消(当前文件完成后停止)...")

    def _set_ui_enabled(self, enabled: bool) -> None:
        """执行进行中禁用全部操作按钮并显示取消;完成则反之。

        预览只做轻量禁用(_set_preview_busy):保留增删改操作与文件选择入口,
        不阻塞连续添加;全量禁用仅用于真正改写文件的执行阶段。
        """
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

    def _set_preview_busy(self, busy: bool) -> None:
        """预览进行中只禁用会并发启动 worker 的入口(执行/手动刷新)。

        预览只读、worker 持有文件与操作列表的快照,进行期间继续增删改操作、
        选文件、看历史都安全;旧实现全量禁用,导致"每加一条查找替换都要等
        一次 COM 预览才能继续添加"。变更由 _preview_pending 挂起,结束后重跑。
        """
        self.ui.btn_execute.setEnabled(not busy)
        self.ui.btn_refresh_preview.setEnabled(not busy)
        self.ui.btn_cancel.setVisible(busy)

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
        """任务未结束时延迟关闭:协作取消后等真实 finished 异步重关。

        不再 wait/terminate 后假定线程结束——worker 持 COM 对象,同步等待会冻结
        关闭、强杀会泄漏 Office 进程;_cleanup_batch_dialog(停防抖定时器、断管理
        信号、关 svc)只在 worker 已释放后执行,关闭等待期不触发新预览、不弹模态框。
        """
        if self._task.defer_close(event):
            # 关闭等待期不再触发新预览(不等 finished 后的清理):立即停防抖定时器
            self._preview_timer.stop()
            self.ui.label_status.setText("正在等待替换任务安全结束,完成后自动关闭…")
            return
        self._cleanup_batch_dialog()
        with contextlib.suppress(Exception):
            self._svc.close()
        super().closeEvent(event)
