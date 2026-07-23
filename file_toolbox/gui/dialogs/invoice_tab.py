"""发票识别 Tab:选文件 -> 解析 -> 表格预览 -> 导出。

标色:重复行黄底,PDF 弱解析行灰底。嵌入主窗口作为第 5 个 Tab。
"""

from pathlib import Path

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.invoice.dedupe import DEDUPE, KEEP_ALL, MARK
from file_toolbox.core.invoice.service import InvoiceService
from file_toolbox.core.invoice.types import ParseResult

_DUP_COLOR = QColor(255, 242, 204)  # 浅黄(重复)
_PDF_COLOR = QColor(230, 230, 230)  # 浅灰(PDF 弱解析)
_HEADERS = [
    "发票号码",
    "发票类型",
    "开票日期",
    "销售方",
    "购买方",
    "价税合计",
    "来源",
    "解析方式",
]
_INVOICE_EXTS = (".zip", ".xml", ".ofd", ".pdf")


class InvoiceTab(QWidget):
    """发票识别 Tab。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._svc = InvoiceService()
        self._history = JsonHistoryStore()
        self._result: ParseResult | None = None
        self._files: list[Path] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 文件选择
        file_row = QHBoxLayout()
        self._btn_add_files = QPushButton("添加文件")
        self._btn_add_folder = QPushButton("添加文件夹")
        self._btn_clear = QPushButton("清空")
        self._list_files = QListWidget()
        for btn in (self._btn_add_files, self._btn_add_folder, self._btn_clear):
            file_row.addWidget(btn)
        file_row.addStretch(1)
        layout.addLayout(file_row)
        layout.addWidget(self._list_files)

        # 选项行
        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("格式:"))
        self._rb_excel = QRadioButton("Excel")
        self._rb_json = QRadioButton("JSON")
        self._rb_both = QRadioButton("两者")
        self._rb_excel.setChecked(True)
        self._fmt_group = QButtonGroup(self)
        for rb in (self._rb_excel, self._rb_json, self._rb_both):
            self._fmt_group.addButton(rb)
            opt_row.addWidget(rb)

        opt_row.addWidget(QLabel("去重:"))
        self._cmb_dedupe = QComboBox()
        self._cmb_dedupe.addItems(["keep_all(不处理)", "dedupe(去重)", "mark(标色)"])
        self._cmb_dedupe.setCurrentIndex(0)
        opt_row.addWidget(self._cmb_dedupe)

        opt_row.addWidget(QLabel("输出目录:"))
        self._edit_outdir = QLineEdit()
        self._edit_outdir.setPlaceholderText("选择或输入输出目录")
        self._btn_browse = QPushButton("浏览")
        opt_row.addWidget(self._edit_outdir)
        opt_row.addWidget(self._btn_browse)
        opt_row.addStretch(1)
        layout.addLayout(opt_row)

        # 按钮
        btn_row = QHBoxLayout()
        self._btn_parse = QPushButton("开始解析")
        self._btn_export = QPushButton("导出")
        self._btn_export.setEnabled(False)
        btn_row.addWidget(self._btn_parse)
        btn_row.addWidget(self._btn_export)
        btn_row.addStretch(1)
        self._lbl_status = QLabel("就绪")
        btn_row.addWidget(self._lbl_status)
        layout.addLayout(btn_row)

        # 表格
        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, stretch=1)

        self._connect()

    def _connect(self):
        self._btn_add_files.clicked.connect(self._add_files)
        self._btn_add_folder.clicked.connect(self._add_folder)
        self._btn_clear.clicked.connect(self._clear)
        self._btn_browse.clicked.connect(self._browse_outdir)
        self._btn_parse.clicked.connect(self._parse)
        self._btn_export.clicked.connect(self._export)

    # --- 文件管理 ---
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择发票文件", "", "发票文件 (*.zip *.xml *.ofd *.pdf)"
        )
        for p in paths:
            self._files.append(Path(p))
            self._list_files.addItem(Path(p).name)

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
            self._list_files.addItem(p.name)

    def _clear(self):
        self._files.clear()
        self._list_files.clear()
        self._table.setRowCount(0)
        self._result = None
        self._btn_export.setEnabled(False)
        self._lbl_status.setText("就绪")

    def _browse_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._edit_outdir.setText(d)

    def _dedupe_strategy(self) -> str:
        idx = self._cmb_dedupe.currentIndex()
        return [KEEP_ALL, DEDUPE, MARK][idx]

    def _format(self) -> str:
        if self._rb_json.isChecked():
            return "json"
        if self._rb_both.isChecked():
            return "both"
        return "excel"

    # --- 解析 ---
    def _parse(self):
        if not self._files:
            QMessageBox.warning(self, "提示", "请先添加发票文件")
            return
        strategy = self._dedupe_strategy()
        self._result = self._svc.parse_files(self._files, dedupe_strategy=strategy)
        self._populate_table()
        self._btn_export.setEnabled(bool(self._result.invoices))
        dup = sum(1 for i in self._result.invoices if i.is_duplicate)
        self._lbl_status.setText(
            f"成功 {len(self._result.invoices)} | 重复标记 {dup} | "
            f"去重移除 {len(self._result.duplicates)} | 失败 {len(self._result.failed)}"
        )

    def _populate_table(self):
        assert self._result is not None
        self._table.setRowCount(len(self._result.invoices))
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
                self._table.setItem(r, c, item)

    # --- 导出 ---
    def _export(self):
        if not self._result or not self._result.invoices:
            QMessageBox.warning(self, "提示", "无数据可导出")
            return
        outdir = self._edit_outdir.text().strip() or "."
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
            {
                "file_count": len(self._files),
                "invoice_count": len(self._result.invoices),
                "dedupe_strategy": self._dedupe_strategy(),
                "fmt": self._format(),
                "outputs": [str(w) for w in written],
            },
        )
        QMessageBox.information(self, "完成", "已导出:\n" + "\n".join(str(w) for w in written))
