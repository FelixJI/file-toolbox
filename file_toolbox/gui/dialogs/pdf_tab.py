"""生成 PDF Tab:多格式文件批量转 PDF(支持合并、图片型)。"""

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QMessageBox,
    QTableWidgetItem,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_pdf import PDFGeneratorService
from file_toolbox.core.batch_pdf.engine_manager import EngineManager
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
from file_toolbox.gui.batch_mixin import BatchDialogMixin
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

    SUPPORTED_FORMATS: set[str] = {
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".gif", ".pdf",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_batch_dialog()
        self.ui = Ui_PDFGeneratorDialog()
        self.ui.setupUi(self)
        self._svc = PDFGeneratorService()
        self._history = JsonHistoryStore()
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

    def _setup_button_groups(self):
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

    def _init_combos(self):
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

    def _connect_signals(self):
        self.ui.btn_select_files.clicked.connect(self._on_select_files)
        self.ui.btn_select_folder.clicked.connect(self._on_select_folder)
        self.ui.btn_clear_files.clicked.connect(self._on_clear_files)
        self.ui.btn_browse_dir.clicked.connect(self._browse_output_dir)
        self.ui.btn_generate.clicked.connect(self._generate)
        self.ui.btn_refresh.clicked.connect(self._do_refresh_preview)
        self.ui.btn_cancel.clicked.connect(self._on_cancel)

    def _init_engine_info(self):
        """启动时异步检测可用 Office 引擎并更新提示。

        检测需 Dispatch COM 进程外服务器(Word/WPS),在无桌面/未装 Office 的环境
        (CI、无头会话、单元测试)中可能触发 RPC 致命异常(0x800706ba/be)。故:
        - 正常形态:经服务的异步接口在后台线程检测,回调通过 QTimer.singleShot(0,...)
          切回主线程更新,避免冻结 UI。
        - 测试/CI 形态:置环境变量 FILE_TOOLBOX_NO_COM_DETECT=1 跳过实时 Dispatch,
          仅回退为缓存信息(无缓存时显示占位),让纯 UI 逻辑测试不触碰 COM。
        """
        import os

        if os.environ.get("FILE_TOOLBOX_NO_COM_DETECT"):
            # 测试/CI:不触发 COM,仅用缓存(可能为空),避免致命异常
            self.ui.label_engine_info.setText(
                self._svc.get_engine_info(use_cache=True) if EngineManager._cached_engines
                else "未检测到Office软件"
            )
            return

        self.ui.label_engine_info.setText("正在检测可用引擎...")

        def _on_detected(info: str):
            QTimer.singleShot(0, lambda: self.ui.label_engine_info.setText(info))

        try:
            self._svc.detect_engines_async(callback=_on_detected)
        except Exception:
            # 非 Windows 或缺少 pywin32 时退回同步(带缓存)信息
            self.ui.label_engine_info.setText(self._svc.get_engine_info(use_cache=True))

    # ---------- 配置构建 ----------

    def _build_config(self) -> dict:
        output_mode = OUTPUT_MERGE if self.ui.radio_merge.isChecked() else OUTPUT_SEPARATE
        pdf_type = PDF_TYPE_IMAGE if self.ui.radio_type_image.isChecked() else PDF_TYPE_EDITABLE
        print_mode = PRINT_MODE_DUPLEX if self.ui.radio_print_duplex.isChecked() else PRINT_MODE_SINGLE
        same_as_source = self.ui.radio_same_dir.isChecked()
        engine = (
            "wps" if self.ui.radio_engine_wps.isChecked()
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

        config = {
            "pdf_type": pdf_type,
            "dpi": int(self.ui.combo_dpi.currentText() or DPI_DEFAULT),
            "paper_size": paper_size,
            "orientation": orientation,
            "scale_mode": scale_mode,
            "engine": engine,
            "output_mode": output_mode,
            "same_as_source": same_as_source,
            "print_mode": print_mode,
            "merge_filename": self.ui.edit_merge_filename.text().strip() or "合并文档.pdf",
        }
        if not same_as_source:
            config["output_dir"] = Path(self.ui.edit_output_dir.text().strip())
        return config

    # ---------- 业务 ----------

    # ---------- 文件选择包装器(适配 table,不改 mixin 签名) ----------

    def _on_select_files(self):
        """选文件:list_widget 传 None(mixin 只更新 selected_files),再刷新预览表。"""
        self._select_files(list_widget=None)
        self._refresh_preview()

    def _on_select_folder(self):
        """选文件夹:同上。"""
        self._select_folder(list_widget=None)
        self._refresh_preview()

    def _on_clear_files(self):
        """清空:同时清 selected_files 与 table_files。"""
        self._clear_files(table_widget=self.ui.table_files)
        self._refresh_preview()

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.ui.edit_output_dir.setText(d)

    def _generate(self):
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

        worker = PdfGenerateWorker(
            self._svc, list(self.selected_files), config, parent=self
        )
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_generate_ok)
        worker.failed.connect(self._on_generate_failed)
        self.worker = worker
        self._set_ui_enabled(False)
        worker.start()

    def _on_progress(self, cur: int, total: int, msg: str):
        self.ui.label_progress.setText(f"[{cur}/{total}] {msg}")
        pct = int(cur / total * 100) if total else 0
        self.ui.progress_bar.setValue(pct)

    def _on_generate_ok(self, results: list):
        self._render_results(results)
        ok = sum(1 for r in results if r["success"])
        fail = len(results) - ok
        self.ui.label_progress.setText(f"完成: 成功 {ok}, 失败 {fail}")
        # 记录历史(PDF 生成不可逆,仅供审计/复现)
        try:
            config = self._build_config()
            self._history.add_record(
                "pdf",
                {
                    "files": [str(f) for f in self.selected_files],
                    "success": ok,
                    "failed": fail,
                    "config": {
                        "pdf_type": config["pdf_type"],
                        "output_mode": config["output_mode"],
                        "engine": config["engine"],
                        "dpi": config["dpi"],
                    },
                },
            )
        except Exception:
            pass  # 历史写入失败不影响主流程
        self._set_ui_enabled(True)
        self.worker = None
        if fail:
            QMessageBox.warning(self, "部分失败", f"{fail} 个文件转换失败,详见预览表。")

    def _on_generate_failed(self, msg: str):
        self.ui.label_progress.setText("生成失败")
        self._set_ui_enabled(True)
        self.worker = None
        QMessageBox.critical(self, "生成失败", msg)

    def _on_cancel(self):
        if self.worker is not None and hasattr(self.worker, "cancel"):
            self.worker.cancel()
        self.ui.label_progress.setText("正在取消...")

    # ---------- 预览 ----------

    def _do_refresh_preview(self):
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

    def _render_results(self, results: list):
        """把生成结果填入 table_files(复用预览表)。

        结果数可能少于表行数(取消时):已处理的行更新为"成功"/"失败: xxx",
        未处理的行保持"待转换"(预览态)。
        """
        tbl = self.ui.table_files
        for row, r in enumerate(results):
            if row >= tbl.rowCount():
                break
            tbl.item(row, 0).setText(r["source"].name)
            tbl.item(row, 1).setText(r["output"].name)
            status = "成功" if r["success"] else f"失败: {r['error']}"
            tbl.item(row, 3).setText(status)

    def _set_ui_enabled(self, enabled: bool):
        """生成进行中禁用选择/生成按钮,显示取消按钮;完成则反之。"""
        self.ui.btn_select_files.setEnabled(enabled)
        self.ui.btn_select_folder.setEnabled(enabled)
        self.ui.btn_clear_files.setEnabled(enabled)
        self.ui.btn_generate.setEnabled(enabled)
        self.ui.btn_refresh.setEnabled(enabled)
        self.ui.btn_cancel.setVisible(not enabled)

    def _update_status(self):
        self.ui.label_status.setText(f"已选择 {len(self.selected_files)} 个文件")

    def closeEvent(self, event):
        self._cleanup_batch_dialog()
        try:
            self._svc.close()
        except Exception:
            pass
        super().closeEvent(event)
