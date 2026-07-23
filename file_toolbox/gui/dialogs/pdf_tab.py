"""生成 PDF Tab:多格式文件批量转 PDF(支持合并、图片型)。"""

import contextlib
import logging
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QMessageBox,
    QTableWidgetItem,
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
from file_toolbox.gui.batch_mixin import BatchDialogMixin
from file_toolbox.gui.controllers.pdf_controller import PDFConfigState, PDFController
from file_toolbox.gui.generated.ui_pdf_dialog import Ui_PDFGeneratorDialog

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
        self._init_batch_dialog()
        self.ui = Ui_PDFGeneratorDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI code
        self._svc = PDFGeneratorService()
        self._history = JsonHistoryStore()
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
        self._init_engine_info()

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
        """启动时异步检测可用 Office 引擎并更新提示。

        启动检测走**注册表探测**(force_refresh=False,毫秒级、不启动 Office 进程);
        真正的 COM Dispatch 兑现留到生成时由 PdfGenerateWorker 以 force_refresh=True
        完成。故:
        - 正常形态:经服务的异步接口在后台线程做注册表探测,回调通过
          QTimer.singleShot(0,...) 切回主线程更新,避免冻结 UI。
        - 测试/CI 形态:置环境变量 FILE_TOOLBOX_NO_COM_DETECT=1 跳过后台探测,
          仅回退为缓存信息(无缓存时显示占位),让纯 UI 逻辑测试不触碰 COM。
        """
        import os

        if os.environ.get("FILE_TOOLBOX_NO_COM_DETECT"):
            # 测试/CI:不触发 COM,仅用缓存(可能为空),避免致命异常
            self.ui.label_engine_info.setText(
                self._svc.get_engine_info(use_cache=True)
                if EngineManager._cached_engines
                else "未检测到Office软件"
            )
            return

        self.ui.label_engine_info.setText("正在检测可用引擎...")

        def _on_detected(info: str) -> None:
            QTimer.singleShot(0, lambda: self.ui.label_engine_info.setText(info))

        try:
            self._svc.detect_engines_async(callback=_on_detected)
        except Exception:
            # 非 Windows 或缺少 pywin32 时退回同步(带缓存)信息
            self.ui.label_engine_info.setText(self._svc.get_engine_info(use_cache=True))

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
        """选文件:list_widget 传 None(mixin 只更新 selected_files),再刷新预览表。"""
        self._select_files(list_widget=None)
        self._refresh_preview()

    def _on_select_folder(self) -> None:
        """选文件夹:同上。"""
        self._select_folder(list_widget=None)
        self._refresh_preview()

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
        # 避免重复启动
        if self.worker is not None and self.worker.isRunning():
            return

        config = self._build_config()
        self.ui.label_progress.setText("处理中...")
        self.ui.progress_bar.setValue(0)

        from file_toolbox.gui.workers.pdf_worker import PdfGenerateWorker

        worker = PdfGenerateWorker(self._svc, list(self.selected_files), config, parent=self)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_generate_ok)
        worker.failed.connect(self._on_generate_failed)
        self.worker = worker
        self._set_ui_enabled(False)
        worker.start()

    def _on_progress(self, cur: int, total: int, msg: str) -> None:
        self.ui.label_progress.setText(self._controller.format_progress(cur, total, msg))
        pct = int(cur / total * 100) if total else 0
        self.ui.progress_bar.setValue(pct)

    def _on_generate_ok(self, results: list[dict[str, Any]]) -> None:
        self._render_results(results)
        ok, fail = self._controller.summarize_results(results)
        self.ui.label_progress.setText(f"完成: 成功 {ok}, 失败 {fail}")
        # 记录历史(PDF 生成不可逆,仅供审计/复现)
        try:
            config = self._build_config()
            self._history.add_record(
                "pdf",
                self._controller.build_history_record(list(self.selected_files), ok, fail, config),
            )
        except Exception as e:
            self._module_logger.warning(f"写入历史失败: {e}", exc_info=True)
        self._set_ui_enabled(True)
        self.worker = None
        if fail:
            QMessageBox.warning(self, "部分失败", f"{fail} 个文件转换失败,详见预览表。")

    def _on_generate_failed(self, msg: str) -> None:
        self.ui.label_progress.setText("生成失败")
        self._set_ui_enabled(True)
        self.worker = None
        QMessageBox.critical(self, "生成失败", msg)

    def _on_cancel(self) -> None:
        if self.worker is not None and hasattr(self.worker, "cancel"):
            self.worker.cancel()
        self.ui.label_progress.setText("正在取消...")

    def _stop_worker(self, timeout_ms: int = 30000) -> None:
        """停止 PDF worker —— 协作式取消 + 较长等待,绝不强制 terminate。

        覆盖 BatchDialogMixin._stop_worker:PDF worker 持有 COM 对象,强制 terminate
        (QThread.terminate)会在线程仍处于 win32com/Word 调用中途时杀掉它,可能泄漏
        Office 进程、留下未初始化 COM、甚至死锁。quit() 对无事件循环的 worker 是
        no-op,cancel() 仅在文件间生效,故大文件转换(>3s)会让基类的 wait(3000) 超时
        进而触发 terminate —— 必须禁用。改用 30s 宽限等待,超时仅记日志。

        closeEvent → _cleanup_batch_dialog → _stop_worker 自动受益于此覆盖。
        """
        if self.worker and self.worker.isRunning():
            if hasattr(self.worker, "cancel"):
                self.worker.cancel()
            # quit() 对无事件循环的 worker 无效,但仍调用以保持一致
            self.worker.quit()
            if not self.worker.wait(timeout_ms):
                self._module_logger.warning(
                    f"{self.__class__.__name__}: PDF worker 未能在 {timeout_ms}ms 内停止"
                    "(可能仍在转换大文件);不强制 terminate 以避免 COM 泄漏"
                )
            # 不调用 self.worker.terminate() —— COM 线程强终止不安全
        self.worker = None

    # ---------- 预览 ----------

    def _do_refresh_preview(self) -> None:
        """刷新预览表(选文件/清空后由防抖定时器触发)。

        把 selected_files 填入 table_files 4 列:
          源文件 / 输出(预期 PDF 名) / 大小 / 状态(待转换)
        合并模式输出列填合并文件名;分离模式填 {stem}.pdf。
        """
        from file_toolbox.common.file_utils import format_file_size

        tbl = self.ui.table_files
        tbl.setRowCount(0)  # 先清空
        if not self.selected_files:
            return

        merge_mode = self.ui.radio_merge.isChecked()
        merge_name = self.ui.edit_merge_filename.text().strip() or "合并文档.pdf"

        tbl.setRowCount(len(self.selected_files))
        for row, path in enumerate(self.selected_files):
            tbl.setItem(row, 0, QTableWidgetItem(path.name))
            # 输出列:合并模式 → 合并文件名;分离模式 → {stem}.pdf
            out_name = merge_name if merge_mode else f"{path.stem}.pdf"
            tbl.setItem(row, 1, QTableWidgetItem(out_name))
            # 大小列:不存在则空
            try:
                size = format_file_size(path.stat().st_size)
            except (OSError, ValueError):
                size = ""
            tbl.setItem(row, 2, QTableWidgetItem(size))
            tbl.setItem(row, 3, QTableWidgetItem("待转换"))

    def _render_results(self, results: list[dict[str, Any]]) -> None:
        """把生成结果填入 table_files(复用预览表)。

        结果数可能少于表行数(取消时):已处理的行更新为"成功"/"失败: xxx",
        未处理的行保持"待转换"(预览态)。
        """
        tbl = self.ui.table_files
        for row, r in enumerate(results):
            if row >= tbl.rowCount():
                break
            # tbl.item() 在单元格未设置时返回 None;预览态行均填了 0/1/3 列,
            # 但防御性判空以匹配 QTableWidgetItem | None 的类型契约。
            item0 = tbl.item(row, 0)
            if item0 is not None:
                item0.setText(r["source"].name)
            item1 = tbl.item(row, 1)
            if item1 is not None:
                item1.setText(r["output"].name)
            status = "成功" if r["success"] else f"失败: {r['error']}"
            item3 = tbl.item(row, 3)
            if item3 is not None:
                item3.setText(status)

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
        self._cleanup_batch_dialog()
        with contextlib.suppress(Exception):
            self._svc.close()
        super().closeEvent(event)
