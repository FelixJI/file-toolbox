"""生成 PDF Tab:多格式文件批量转 PDF(支持合并、图片型)。"""

import contextlib
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QMessageBox,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_pdf import PDFGeneratorService
from file_toolbox.core.batch_pdf.constants import (
    DPI_DEFAULT,
    DPI_OPTIONS,
    OUTPUT_MERGE,
    OUTPUT_SEPARATE,
    PAPER_SIZES,
    PDF_TYPE_EDITABLE,
    PDF_TYPE_IMAGE,
    PRINT_MODE_DUPLEX,
    PRINT_MODE_SINGLE,
    SCALE_ACTUAL_SIZE,
    SCALE_DEFAULT,
    SCALE_FIT_MARGIN,
    SCALE_SHRINK_OVERSIZED,
)
from file_toolbox.core.batch_pdf.engine_manager import EngineManager
from file_toolbox.core.office_capability import format_statuses, tool_capability_statuses
from file_toolbox.gui.batch_mixin import BatchDialogMixin
from file_toolbox.gui.controllers.pdf_controller import PDFConfigState, PDFController
from file_toolbox.gui.file_models import table_model
from file_toolbox.gui.generated.ui_pdf_dialog import Ui_PDFGeneratorDialog
from file_toolbox.gui.task_lifecycle import TaskLifecycle
from file_toolbox.gui.workers.file_scan_worker import FileScanWorker, ScannedFile

# 下拉框显示文本 -> 服务层期望的常量值
_PAPER_AUTO = "自动"
_ORIENT_LABELS = {"自动": "auto", "纵向": "portrait", "横向": "landscape"}
_SCALE_LABELS = {
    "适合边距": SCALE_FIT_MARGIN,
    "实际大小": SCALE_ACTUAL_SIZE,
    "缩小过大页面": SCALE_SHRINK_OVERSIZED,
}


class PDFGeneratorDialog(QDialog, BatchDialogMixin):
    """批量生成 PDF 对话框(作为 Tab 嵌入)。"""

    # 模块级 logger(不通过 LoggableMixin 混入:该 mixin 的 @property logger 与
    # QDialog/Qt 元类在解释器退出期 GC 交互会触发 Windows 堆损坏 0xc0000374)。
    _module_logger = logging.getLogger(__name__)
    # BatchDialogMixin 的 _cleanup_batch_dialog / _stop_worker 调用 self.logger,
    # 暴露为类属性以满足该契约(无需混入 LoggableMixin,避免上述 GC 风险)。
    logger = _module_logger

    # 引擎检测回显桥:检测 daemon 线程只 emit,Qt queued 连接投递回对话框线程。
    # 对话框销毁即自动断连,晚到的检测结果被安全丢弃(AC1/AC5)。载荷携带请求
    # 代次 token,槽侧只接受最新请求的结果,旧代次不覆盖新状态(AC5)。
    _engine_detected = Signal(int, str)

    SUPPORTED_FORMATS: set[str] = {
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tif",
        ".tiff",
        ".gif",
        ".pdf",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 生命周期句柄先建:_init_batch_dialog 里 self.worker = None 经下方属性转发写入 task
        self._task = TaskLifecycle(self)
        self._init_batch_dialog()
        self.ui = Ui_PDFGeneratorDialog()
        self.ui.setupUi(self)
        self._pdf_preview_pending = False
        self._pdf_metadata_snapshot: list[Path] = []
        self._pdf_display_files: list[Path] = []
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = PDFGeneratorService(history_store=self._history)
        self._controller = PDFController()
        # 各组 QButtonGroup,避免所有单选按钮因共享父控件而互相排斥
        self._type_group = QButtonGroup(self)
        self._engine_group = QButtonGroup(self)
        self._output_group = QButtonGroup(self)
        self._dir_group = QButtonGroup(self)
        self._print_group = QButtonGroup(self)
        self.ui.btn_cancel.setVisible(False)
        self._setup_button_groups()
        self._init_combos()
        self._connect_signals()
        self._engine_echo_token = 0
        self._engine_detected.connect(self._on_engine_detected)
        self._init_engine_info()

    # 兼容旧 worker 字段:单一事实在 TaskLifecycle,读写均转发;只有真实
    # finished(task.finish 精确身份校验)才清空,结果信号不提前释放引用。
    @property
    def worker(self) -> QThread | None:
        return self._task.worker

    @worker.setter
    def worker(self, value: QThread | None) -> None:
        self._task.worker = value

    # ---------- 初始化 ----------

    def _setup_button_groups(self) -> None:
        """为每组单选按钮建立独立的互斥组。

        生成的 UI 里所有 QRadioButton 共用同一父控件(group_settings),
        Qt 默认按父控件自动互斥,会导致选中"图片型"时连带取消"合并"
        等无关选项。这里显式分组以纠正该行为。
        """
        for rb in (self.ui.radio_type_editable, self.ui.radio_type_image):
            self._type_group.addButton(rb)
        for rb in (
            self.ui.radio_engine_auto,
            self.ui.radio_engine_office,
            self.ui.radio_engine_wps,
        ):
            self._engine_group.addButton(rb)
        for rb in (self.ui.radio_separate, self.ui.radio_merge):
            self._output_group.addButton(rb)
        for rb in (self.ui.radio_same_dir, self.ui.radio_custom_dir):
            self._dir_group.addButton(rb)
        for rb in (self.ui.radio_print_single, self.ui.radio_print_duplex):
            self._print_group.addButton(rb)

    def _init_combos(self) -> None:
        """填充设置区下拉框(DPI / 纸张 / 方向 / 缩放)。"""
        self.ui.combo_dpi.clear()
        for dpi in DPI_OPTIONS:
            self.ui.combo_dpi.addItem(str(dpi))
        # 默认 DPI
        default_dpi_idx = self.ui.combo_dpi.findText(str(DPI_DEFAULT))
        if default_dpi_idx >= 0:
            self.ui.combo_dpi.setCurrentIndex(default_dpi_idx)

        self.ui.combo_paper_size.clear()
        self.ui.combo_paper_size.addItem(_PAPER_AUTO)
        for name in PAPER_SIZES:
            self.ui.combo_paper_size.addItem(name)
        self.ui.combo_paper_size.setCurrentIndex(0)

        self.ui.combo_orientation.clear()
        for label in _ORIENT_LABELS:
            self.ui.combo_orientation.addItem(label)
        self.ui.combo_orientation.setCurrentIndex(0)

        self.ui.combo_scale.clear()
        for label, value in _SCALE_LABELS.items():
            self.ui.combo_scale.addItem(label, userData=value)
        default_scale_idx = self.ui.combo_scale.findData(SCALE_DEFAULT)
        if default_scale_idx >= 0:
            self.ui.combo_scale.setCurrentIndex(default_scale_idx)

    def _connect_signals(self) -> None:
        self.ui.btn_select_files.clicked.connect(self._on_select_files)
        self.ui.btn_select_folder.clicked.connect(self._on_select_folder)
        self.ui.btn_clear_files.clicked.connect(self._on_clear_files)
        self.ui.btn_browse_dir.clicked.connect(self._browse_output_dir)
        self.ui.btn_generate.clicked.connect(self._generate)
        self.ui.btn_refresh.clicked.connect(self._do_refresh_preview)
        self.ui.btn_cancel.clicked.connect(self._on_cancel)

    def _init_engine_info(self) -> None:
        """启动时异步检测可用 Office 引擎并更新提示(回显经信号桥回 GUI 线程)。

        启动检测走**注册表探测**(force_refresh=False,毫秒级、不启动 Office 进程);
        真实 COM Dispatch 的证据由转换成功时的 record_engine_evidence 喂养持久缓存,
        不存在独立"验证预检"步骤(Issue #123)。回显链:检测 daemon 线程只
        ``_engine_detected.emit(token, info)``——Qt queued 连接把结果投递回对话框
        所在线程更新 label。不能用无 context 的 ``QTimer.singleShot(0, ...)``:
        从 daemon 线程调用时 Qt 在**调用线程**建 timer,而该线程没有事件循环,
        回调永不投递(仓库锁定 PySide6 6.11.2 上实证,Issue #123 WP-A 探针),
        label 会永久停留"正在检测"——这正是用户看到"检测慢"的直接根因。
        - 正常形态:经服务的异步接口在后台线程做注册表探测(single-flight 合并
          并发请求),结果经信号回主线程,不冻结 UI。
        - 测试/CI 形态:置环境变量 FILE_TOOLBOX_NO_COM_DETECT=1 跳过后台探测,
          仅回退为缓存信息(无缓存时显示占位),让纯 UI 逻辑测试不触碰 COM。
        """
        import os

        if os.environ.get("FILE_TOOLBOX_NO_COM_DETECT"):
            # 测试/CI:不触发 COM,仅用缓存(可能为空),避免致命异常
            info = (
                self._svc.get_engine_info(use_cache=True)
                if EngineManager._cached_engines
                else "未检测到Office软件"
            )
            self.ui.label_engine_info.setText(info + "\n" + self._kind_status_text())
            return

        self.ui.label_engine_info.setText("正在检测可用引擎...")
        self._engine_echo_token += 1
        token = self._engine_echo_token

        def _on_detected(info: str) -> None:
            # 检测 daemon 线程内执行:只 emit(线程安全),UI 写入全部发生在
            # _on_engine_detected 槽(对话框线程)。token 随载荷传递,槽侧裁决。
            self._engine_detected.emit(token, info)

        try:
            self._svc.detect_engines_async(callback=_on_detected)
        except Exception:
            # 非 Windows 或缺少 pywin32 时退回同步(带缓存)信息
            self.ui.label_engine_info.setText(self._svc.get_engine_info(use_cache=True))

    def _kind_status_text(self) -> str:
        """按文件类型的 Office 能力行(消费统一登记声明,注册表预筛)。

        各 kind 独立探测自己的 ProgID:套件级缓存(以 Word/KWPS 判定)不能
        据此否定 Excel/PPT。纯图片/PDF 路径不启动 Office,预筛命中也不冒称
        真实转换验证(文案见 office_capability.format_statuses)。
        """
        return "按文件类型: " + format_statuses(tool_capability_statuses("pdf"))

    def _on_engine_detected(self, token: int, info: str) -> None:
        """引擎检测回显槽(对话框线程):只接受最新代次请求的结果。

        旧代次的晚到结果直接丢弃,不覆盖新状态(AC5);异常终态文案同样经此
        槽回显,页面不会停留在"正在检测"。第二行为按文件类型的独立预筛结论。
        """
        if token != self._engine_echo_token:
            return
        self.ui.label_engine_info.setText(info + "\n" + self._kind_status_text())

    def _refresh_engine_info_label(self) -> None:
        """用当前缓存刷新引擎信息 label,消除"正在检测..."残留。

        仅当 get_engine_info 返回非占位文案(即缓存已就绪)时才更新;缓存尚未填充
        (仍为 None → 返回"正在检测可用引擎...")时保持现状,避免把后台探测中的
        状态误覆盖成过期文本。生成开始/结束时各调一次,确保生成期间 label 不再
        卡在"正在检测"。
        """
        info = self._svc.get_engine_info(use_cache=True)
        if info and info != "正在检测可用引擎...":
            self.ui.label_engine_info.setText(info + "\n" + self._kind_status_text())

    # ---------- 配置构建 ----------

    def _build_config(self) -> dict[str, object]:
        """从 UI 控件读取当前值 → PDFConfigState → 交 controller 编排为 config dict。

        UI→值映射(常量字符串)保留在此处(与 Qt 控件耦合);纯编排逻辑落在
        PDFController.build_config(可无 Qt 单测)。
        """
        output_mode = OUTPUT_MERGE if self.ui.radio_merge.isChecked() else OUTPUT_SEPARATE
        pdf_type = PDF_TYPE_IMAGE if self.ui.radio_type_image.isChecked() else PDF_TYPE_EDITABLE
        print_mode = (
            PRINT_MODE_DUPLEX if self.ui.radio_print_duplex.isChecked() else PRINT_MODE_SINGLE
        )
        same_as_source = self.ui.radio_same_dir.isChecked()
        engine = (
            "wps"
            if self.ui.radio_engine_wps.isChecked()
            else ("office" if self.ui.radio_engine_office.isChecked() else "auto")
        )

        paper_label = self.ui.combo_paper_size.currentText()
        paper_size = "auto" if paper_label == _PAPER_AUTO else paper_label

        orient_label = self.ui.combo_orientation.currentText()
        orientation = _ORIENT_LABELS.get(orient_label, "auto")

        scale_mode = (
            self.ui.combo_scale.currentData()
            or _SCALE_LABELS.get(self.ui.combo_scale.currentText())
            or SCALE_DEFAULT
        )

        state = PDFConfigState(
            pdf_type=pdf_type,
            dpi=int(self.ui.combo_dpi.currentText() or DPI_DEFAULT),
            paper_size=paper_size,
            orientation=orientation,
            scale_mode=scale_mode,
            engine=engine,
            output_mode=output_mode,
            same_as_source=same_as_source,
            print_mode=print_mode,
            merge_filename=self.ui.edit_merge_filename.text(),
            output_dir=self.ui.edit_output_dir.text(),
        )
        return self._controller.build_config(state)

    # ---------- 业务 ----------

    # ---------- 文件选择包装器(适配 table,不改 mixin 签名) ----------

    def _on_select_files(self) -> None:
        """文件进入扫描队列，元数据批次直接填表，全部完成后刷新旧结果状态。"""
        self._select_files(list_widget=None)

    def _on_select_folder(self) -> None:
        """目录进入相同的追加队列，保留递归选择与过滤规则。"""
        self._select_folder(list_widget=None)

    def _on_clear_files(self) -> None:
        """清空:同时清 selected_files 与 table_files。"""
        self._clear_files(table_widget=self.ui.table_files)
        self._refresh_preview()

    def _browse_output_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.ui.edit_output_dir.setText(d)

    def _generate(self) -> None:
        if not self.selected_files:
            QMessageBox.information(self, "提示", "请先选择文件。")
            return
        # 避免重复启动:任务尚未在真实 finished 中释放(或正在延迟关闭)时一律拒绝,
        # 不以 isRunning() 为准——排队的 finished 尚未消费时同样不能开下一轮
        if self._task.busy:
            return

        config = self._build_config()
        self.ui.label_progress.setText("处理中...")
        self.ui.progress_bar.setValue(0)
        # 立即用当前缓存刷新引擎信息,消除"正在检测..."残留(此时后台注册表探测基本
        # 已完成、缓存已填充);生成期间 label_engine_info 不再停留在检测态。
        self._refresh_engine_info_label()

        from file_toolbox.gui.workers.pdf_worker import PdfGenerateWorker

        worker = PdfGenerateWorker(self._svc, list(self.selected_files), config, parent=self)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_generate_ok)
        worker.failed.connect(self._on_generate_failed)
        worker.cleanup_warning.connect(self._on_cleanup_warning)
        worker.finished.connect(self._on_worker_finished)
        self._business_generation = self._import_generation
        self._task.track(worker)
        self._set_ui_enabled(False)
        worker.start()

    def _on_progress(self, cur: int, total: int, msg: str) -> None:
        if not self._accept_business_result():
            return
        self.ui.label_progress.setText(self._controller.format_progress(cur, total, msg))
        pct = int(cur / total * 100) if total else 0
        self.ui.progress_bar.setValue(pct)

    def _on_generate_ok(self, results: list[dict[str, Any]]) -> None:
        """结果槽:只渲染结果;引用释放与控件恢复等真实 finished。"""
        if not self._accept_business_result():
            return
        self._render_results(results)
        ok, fail = self._controller.summarize_results(results)
        self.ui.label_progress.setText(f"完成: 成功 {ok}, 失败 {fail}")
        # 历史记录已下沉 PDFGeneratorService.batch_generate(注入了 history_store,
        # 在 worker 线程内由 JsonHistoryStore 的锁保护写入)
        # 兑现已完成(若含 Office 文档),刷新引擎信息反映真实状态。
        self._refresh_engine_info_label()
        if fail and not self._task.close_pending:
            QMessageBox.warning(self, "部分失败", f"{fail} 个文件转换失败,详见预览表。")

    def _on_generate_failed(self, msg: str) -> None:
        if not self._accept_business_result():
            return
        self.ui.label_progress.setText("生成失败")
        self._refresh_engine_info_label()
        if not self._task.close_pending:
            QMessageBox.critical(self, "生成失败", msg)

    def _on_cleanup_warning(self, msg: str) -> None:
        if not self._accept_business_result():
            return
        self.ui.label_progress.setText("任务结果已保留，资源清理失败")
        if not self._task.close_pending:
            QMessageBox.warning(self, "资源清理警告", msg)

    def _on_worker_finished(self) -> None:
        """真实 finished 后释放线程并恢复控件;延迟关闭由 TaskLifecycle 续接。"""
        if not self._task.finish(self.sender()):
            return
        self._set_ui_enabled(True)
        if not self._task.close_pending and not self._resume_import() and self._pdf_preview_pending:
            self._pdf_preview_pending = False
            self._do_refresh_preview()

    def _on_cancel(self) -> None:
        self._pdf_preview_pending = False
        self._preview_timer.stop()
        if not self._cancel_import():
            self._task.cancel()
        self.ui.label_progress.setText("正在取消...")

    # ---------- 预览 ----------

    def _pdf_preview_rows(self, paths: list[Path]) -> list[tuple[list[str], None]]:
        merge = self.ui.radio_merge.isChecked()
        name = self.ui.edit_merge_filename.text().strip() or "合并文档.pdf"
        return [
            (
                [
                    path.name,
                    name if merge else f"{path.stem}.pdf",
                    self._file_metadata.get(path, ScannedFile(path)).size,
                    "待转换",
                ],
                None,
            )
            for path in paths
        ]

    def _import_updated(self, batch: list[ScannedFile]) -> None:
        self._update_status()
        table_model(self.ui.table_files).append_rows(
            self._pdf_preview_rows([i.path for i in batch])
        )

    def _after_import(self) -> None:
        self._pdf_display_files = list(self.selected_files)
        # 首批已带元数据；队列全部完成后同步消费配置变更和旧结果状态。
        if self._import_changed or self._pdf_preview_pending:
            self._pdf_preview_pending = False
            self._do_refresh_preview()

    def _import_cancelled(self) -> None:
        super()._import_cancelled()
        self._pdf_preview_pending = False

    def _do_refresh_preview(self) -> None:
        self._preview_timer.stop()
        if self._task.busy:
            self._pdf_preview_pending = True
            return
        model = table_model(self.ui.table_files)
        rows = self._pdf_preview_rows(self.selected_files)
        if self._pdf_display_files == self.selected_files and model.rowCount() == len(rows):
            model.update_rows(rows)
        else:
            model.replace_rows(rows)
            self._pdf_display_files = list(self.selected_files)
        missing = [p for p in self.selected_files if p not in self._file_metadata]
        if not missing or self._task.close_pending:
            return
        worker = FileScanWorker(
            self._import_generation,
            missing,
            None,
            False,
            lambda p: True,
            [],
            False,
            False,
            True,
            self,
        )
        self._pdf_metadata_snapshot = list(self.selected_files)
        worker.batch.connect(self._on_pdf_metadata)
        worker.failed.connect(self._on_import_error)
        worker.finished.connect(self._on_pdf_metadata_finished)
        self._task.track(worker)
        self._import_busy(True)
        worker.start()

    def _on_pdf_metadata(self, generation: int, batch: list[ScannedFile]) -> None:
        if (
            self.sender() is not self.worker
            or generation != self._import_generation
            or self._task.close_pending
        ):
            return
        self._file_metadata.update({i.path: i for i in batch})
        model = table_model(self.ui.table_files)
        positions = {p: n for n, p in enumerate(self._pdf_metadata_snapshot)}
        changed = []
        for item in batch:
            row = positions[item.path]
            if row < len(model.rows):
                model.rows[row][0][2] = item.size
                changed.append(row)
        if changed:
            model.dataChanged.emit(model.index(min(changed), 2), model.index(max(changed), 2))

    def _on_pdf_metadata_finished(self) -> None:
        worker = self.worker
        cancelled = isinstance(worker, FileScanWorker) and worker.cancel_requested
        if not self._task.finish(self.sender()):
            return
        self._import_busy(False)
        if cancelled:
            self._import_cancelled()
        if not self._task.close_pending and not self._resume_import() and self._pdf_preview_pending:
            self._pdf_preview_pending = False
            self._do_refresh_preview()

    def _render_results(self, results: list[dict[str, Any]]) -> None:
        model = table_model(self.ui.table_files)
        rows = []
        for row, result in enumerate(results):
            if row >= len(model.rows):
                break
            values = list(model.rows[row][0])
            values[0] = result["source"].name
            values[1] = result["output"].name
            values[3] = "成功" if result["success"] else f"失败: {result['error']}"
            rows.append((values, None))
        model.update_rows(rows)

    def _set_ui_enabled(self, enabled: bool) -> None:
        """生成进行中禁用选择/生成按钮,显示取消按钮;完成则反之。"""
        self.ui.btn_select_files.setEnabled(enabled)
        self.ui.btn_select_folder.setEnabled(enabled)
        self.ui.btn_clear_files.setEnabled(enabled)
        self.ui.btn_generate.setEnabled(enabled)
        self.ui.btn_refresh.setEnabled(enabled)
        self.ui.btn_cancel.setVisible(not enabled)

    def _update_status(self) -> None:
        self.ui.label_status.setText(f"已选择 {len(self.selected_files)} 个文件")

    def closeEvent(self, event: QCloseEvent) -> None:
        """任务未结束时延迟关闭:协作取消后等真实 finished 异步重关。

        不再 wait/terminate 后假定线程结束——worker 持 COM 对象,同步等待会冻结
        关闭、强杀会泄漏 Office 进程;清空引用/恢复控件/重新关闭全部由
        TaskLifecycle 在真实 finished 消费时完成。
        """
        if self._task.defer_close(event):
            self._preview_timer.stop()
            self.ui.label_progress.setText("正在等待转换安全结束,完成后自动关闭…")
            return
        self._cleanup_batch_dialog()
        # svc.close 只在 worker 线程已退出(run() 的 finally 已先行关闭)后执行
        with contextlib.suppress(Exception):
            self._svc.close()
        super().closeEvent(event)
