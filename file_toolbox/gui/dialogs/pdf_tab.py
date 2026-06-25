"""生成 PDF Tab:多格式文件批量转 PDF(支持合并、图片型)。"""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QListWidgetItem,
    QMessageBox,
    QTableWidgetItem,
)

from file_toolbox.core.batch_pdf import PDFGeneratorService
from file_toolbox.core.batch_pdf.constants import (
    DPI_DEFAULT,
    OUTPUT_MERGE,
    OUTPUT_SEPARATE,
    PDF_TYPE_EDITABLE,
    PDF_TYPE_IMAGE,
    PRINT_MODE_DUPLEX,
    PRINT_MODE_SINGLE,
)
from file_toolbox.gui.batch_mixin import BatchDialogMixin
from file_toolbox.gui.generated.ui_pdf_dialog import Ui_PDFGeneratorDialog


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
        self.ui.btn_cancel.setVisible(False)
        self._connect_signals()

    def _connect_signals(self):
        self.ui.btn_select_files.clicked.connect(lambda: self._select_files(self.ui.list_files))
        self.ui.btn_select_folder.clicked.connect(
            lambda: self._select_folder(self.ui.list_files)
        )
        self.ui.btn_clear_files.clicked.connect(lambda: self._clear_files(self.ui.list_files))
        self.ui.btn_browse_dir.clicked.connect(self._browse_output_dir)
        self.ui.btn_generate.clicked.connect(self._generate)
        self.ui.btn_refresh.clicked.connect(self._refresh_engine_info)

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.ui.edit_output_dir.setText(d)

    def _build_config(self) -> dict:
        output_mode = OUTPUT_MERGE if self.ui.radio_merge.isChecked() else OUTPUT_SEPARATE
        pdf_type = PDF_TYPE_IMAGE if self.ui.radio_type_image.isChecked() else PDF_TYPE_EDITABLE
        print_mode = PRINT_MODE_DUPLEX if self.ui.radio_print_duplex.isChecked() else PRINT_MODE_SINGLE
        same_as_source = self.ui.radio_same_dir.isChecked()
        engine = (
            "wps" if self.ui.radio_engine_wps.isChecked()
            else ("office" if self.ui.radio_engine_office.isChecked() else "auto")
        )
        config = {
            "pdf_type": pdf_type,
            "dpi": int(self.ui.combo_dpi.currentText() or DPI_DEFAULT),
            "paper_size": self.ui.combo_paper_size.currentText(),
            "orientation": self.ui.combo_orientation.currentText().lower(),
            "scale_mode": self.ui.combo_scale.currentData() or self.ui.combo_scale.currentText(),
            "engine": engine,
            "output_mode": output_mode,
            "same_as_source": same_as_source,
            "print_mode": print_mode,
            "merge_filename": self.ui.edit_merge_filename.text().strip() or "合并文档.pdf",
        }
        if not same_as_source:
            config["output_dir"] = Path(self.ui.edit_output_dir.text().strip())
        return config

    def _generate(self):
        if not self.selected_files:
            QMessageBox.information(self, "提示", "请先选择文件。")
            return
        config = self._build_config()
        self.ui.label_progress.setText("处理中...")

        def progress(cur, total, msg):
            self.ui.label_progress.setText(f"[{cur}/{total}] {msg}")

        results = self._svc.batch_generate(list(self.selected_files), config, progress)
        self._render_results(results)
        ok = sum(1 for r in results if r["success"])
        fail = len(results) - ok
        self.ui.label_progress.setText(f"完成: 成功 {ok}, 失败 {fail}")
        if fail:
            QMessageBox.warning(self, "部分失败", f"{fail} 个文件转换失败,详见预览表。")

    def _render_results(self, results):
        tbl = self.ui.table_preview
        tbl.setRowCount(len(results))
        for row, r in enumerate(results):
            tbl.setItem(row, 0, QTableWidgetItem(r["source"].name))
            tbl.setItem(row, 1, QTableWidgetItem(r["output"].name))
            tbl.setItem(row, 2, QTableWidgetItem("成功" if r["success"] else f"失败: {r['error']}"))

    def _refresh_engine_info(self):
        self.ui.label_engine_info.setText(self._svc.get_engine_info(use_cache=True))

    def _update_status(self):
        self.ui.label_status.setText(f"已选择 {len(self.selected_files)} 个文件")

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
        try:
            self._svc.close()
        except Exception:
            pass
        super().closeEvent(event)
