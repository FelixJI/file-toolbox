"""发票识别 Tab:选文件 -> 解析 -> 表格预览 -> 导出。

标色:重复行黄底,PDF 弱解析行灰底。嵌入主窗口作为第 5 个 Tab。
UI 布局由 generated/ui_invoice_dialog.py 的 Ui_InvoiceDialog(setupUi) 构建,
本类只做信号连接 + 业务编排(与其他 Tab 一致)。
"""

from pathlib import Path

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QWidget

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.invoice.service import InvoiceService
from file_toolbox.core.invoice.types import ParseResult
from file_toolbox.gui.controllers.invoice_controller import InvoiceController
from file_toolbox.gui.generated.ui_invoice_dialog import Ui_InvoiceDialog

_DUP_COLOR = QColor(255, 242, 204)  # 浅黄(重复)
_PDF_COLOR = QColor(230, 230, 230)  # 浅灰(PDF 弱解析)
_INVOICE_EXTS = (".zip", ".xml", ".ofd", ".pdf")


class InvoiceTab(QWidget):
    """发票识别 Tab。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_InvoiceDialog()
        self.ui.setupUi(self)
        self._svc = InvoiceService()
        self._history = JsonHistoryStore()
        self._controller = InvoiceController()
        self._result: ParseResult | None = None
        self._files: list[Path] = []
        self._connect()

    def _connect(self):
        self.ui.btn_add_files.clicked.connect(self._add_files)
        self.ui.btn_add_folder.clicked.connect(self._add_folder)
        self.ui.btn_clear.clicked.connect(self._clear)
        self.ui.btn_browse.clicked.connect(self._browse_outdir)
        self.ui.btn_parse.clicked.connect(self._parse)
        self.ui.btn_export.clicked.connect(self._export)

    # --- 文件管理 ---
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择发票文件", "", "发票文件 (*.zip *.xml *.ofd *.pdf)"
        )
        for p in paths:
            self._files.append(Path(p))
            self.ui.list_files.addItem(Path(p).name)

    def _add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not d:
            return
        recursive = (
            QMessageBox.question(
                self,
                "选择模式",
                "是否包含子文件夹中的发票文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            == QMessageBox.StandardButton.Yes
        )
        root = Path(d)
        candidates = root.rglob("*") if recursive else root.iterdir()
        seen = {p.resolve() for p in self._files}
        for p in candidates:
            if not (p.is_file() and p.suffix.lower() in _INVOICE_EXTS):
                continue
            if p.resolve() in seen:
                continue
            seen.add(p.resolve())
            self._files.append(p)
            self.ui.list_files.addItem(p.name)

    def _clear(self):
        self._files.clear()
        self.ui.list_files.clear()
        self.ui.table.setRowCount(0)
        self._result = None
        self.ui.btn_export.setEnabled(False)
        self.ui.lbl_status.setText("就绪")

    def _browse_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.ui.edit_outdir.setText(d)

    def _dedupe_strategy(self) -> str:
        return self._controller.dedupe_strategy(self.ui.cmb_dedupe.currentIndex())

    def _format(self) -> str:
        return self._controller.format(self.ui.rb_json.isChecked(), self.ui.rb_both.isChecked())

    # --- 解析 ---
    def _parse(self):
        if not self._files:
            QMessageBox.warning(self, "提示", "请先添加发票文件")
            return
        strategy = self._dedupe_strategy()
        self._result = self._svc.parse_files(self._files, dedupe_strategy=strategy)
        self._populate_table()
        self.ui.btn_export.setEnabled(bool(self._result.invoices))
        dup = sum(1 for i in self._result.invoices if i.is_duplicate)
        self.ui.lbl_status.setText(
            self._controller.format_status(
                len(self._result.invoices),
                dup,
                len(self._result.duplicates),
                len(self._result.failed),
            )
        )

    def _populate_table(self):
        assert self._result is not None
        self.ui.table.setRowCount(len(self._result.invoices))
        for r, inv in enumerate(self._result.invoices):
            values = [
                inv.invoice_number,
                inv.invoice_type,
                inv.issue_date,
                inv.seller_name,
                inv.buyer_name,
                inv.amount_with_tax,
                inv.source_file,
                inv.parse_method,
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                if inv.is_duplicate:
                    item.setBackground(QBrush(_DUP_COLOR))
                elif inv.parse_method == "pdf":
                    item.setBackground(QBrush(_PDF_COLOR))
                self.ui.table.setItem(r, c, item)

    # --- 导出 ---
    def _export(self):
        if not self._result or not self._result.invoices:
            QMessageBox.warning(self, "提示", "无数据可导出")
            return
        outdir = self.ui.edit_outdir.text().strip() or "."
        outdir_path = Path(outdir)
        outdir_path.mkdir(parents=True, exist_ok=True)
        base = outdir_path / "发票结果"
        xlsx_path = base.with_suffix(".xlsx")
        json_path = base.with_suffix(".json")
        try:
            written = self._svc.export(
                self._result,
                xlsx_path,
                fmt=self._format(),
                json_path=json_path,
                dedupe_strategy=self._dedupe_strategy(),
            )
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(e))
            return
        # 记录历史(发票识别结果不可逆,仅供审计/复现)
        assert self._result is not None
        self._history.add_record(
            "invoice",
            self._controller.build_history_record(
                len(self._files),
                len(self._result.invoices),
                self._dedupe_strategy(),
                self._format(),
                written,
            ),
        )
        QMessageBox.information(self, "完成", "已导出:\n" + "\n".join(str(w) for w in written))
