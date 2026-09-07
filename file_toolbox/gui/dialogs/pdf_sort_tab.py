"""PDF 排序 Tab:选文件 -> 后台按文字层排序 -> 结果表格。

按用户给定的正则匹配每页文字(日期/流水号等)作为排序键,重排页面写出新 PDF。
UI 布局由 generated/ui_pdf_sort_dialog.py 的 Ui_PdfSortDialog(setupUi)构建,
本类只做信号连接 + 业务编排(与其他 Tab 一致)。
"""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtGui import QBrush, QCloseEvent, QColor
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QWidget

from file_toolbox.common import settings
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.pdf_sort import (
    SORTED_MARKER,
    SUPPORTED_SUFFIXES,
    PdfSortService,
    compile_pattern,
)
from file_toolbox.gui.controllers.pdf_sort_controller import PdfSortController
from file_toolbox.gui.generated.ui_pdf_sort_dialog import Ui_PdfSortDialog
from file_toolbox.gui.workers.pdf_sort_worker import PdfSortWorker

_FAIL_COLOR = QColor(255, 242, 204)  # 浅黄(失败行)
# 上次输出目录的 settings key:输出框留空时默认复用,避免每次落到程序目录
_LAST_OUTDIR_KEY = "pdf_sort/last_output_dir"
_logger = logging.getLogger(__name__)


class PdfSortTab(QWidget):
    """PDF 排序 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_PdfSortDialog()
        self.ui.setupUi(self)
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = PdfSortService(history_store=self._history)
        self._controller = PdfSortController()
        self._files: list[Path] = []
        self._worker: PdfSortWorker | None = None
        self._connect()

    def _connect(self) -> None:
        self.ui.btn_add_files.clicked.connect(self._add_files)
        self.ui.btn_add_folder.clicked.connect(self._add_folder)
        self.ui.btn_clear.clicked.connect(self._clear)
        self.ui.btn_browse.clicked.connect(self._browse_outdir)
        self.ui.btn_sort.clicked.connect(self._sort)

    # --- 文件管理 ---

    def _is_source(self, path: Path) -> bool:
        """受支持的源文件:后缀匹配且非 Office/阅读器临时文件(~$ 开头)。"""
        return path.suffix.lower() in SUPPORTED_SUFFIXES and not path.name.startswith("~$")

    def _add_paths(self, paths: list[Path]) -> None:
        """按去重后的顺序追加受支持文件到列表。"""
        seen = {p.resolve() for p in self._files}
        added = 0
        for p in paths:
            rp = p.resolve()
            if not (p.is_file() and self._is_source(p)) or rp in seen:
                continue
            seen.add(rp)
            self._files.append(p)
            self.ui.list_files.addItem(p.name)
            added += 1
        if added:
            self.ui.lbl_status.setText(f"已选择 {len(self._files)} 个文件")

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 PDF 文件", "", "PDF 文件 (*.pdf)")
        self._add_paths([Path(p) for p in paths])

    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not d:
            return
        recursive = (
            QMessageBox.question(
                self,
                "选择模式",
                "是否包含子文件夹中的 PDF 文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            == QMessageBox.StandardButton.Yes
        )
        root = Path(d)
        candidates = root.rglob("*") if recursive else root.iterdir()
        self._add_paths([p for p in candidates if p.is_file()])

    def _clear(self) -> None:
        self._files.clear()
        self.ui.list_files.clear()
        self.ui.table.setRowCount(0)
        self.ui.lbl_status.setText("就绪")

    def _browse_outdir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.ui.edit_outdir.setText(d)

    def _options(self) -> Any:
        return self._controller.build_options(
            self.ui.edit_pattern.text().strip(),
            self.ui.cmb_order.currentIndex(),
            self.ui.cmb_unmatched.currentIndex(),
        )

    # --- 排序 ---

    def _resolve_outdir(self) -> Path:
        """输出目录解析:输出框内容 > 上次输出目录(仍存在) > 首个源文件目录 > 当前目录。"""
        text = self.ui.edit_outdir.text().strip()
        if text:
            return Path(text)
        last = settings.get(_LAST_OUTDIR_KEY)
        if isinstance(last, str) and last.strip() and Path(last.strip()).is_dir():
            return Path(last.strip())
        if self._files:
            return self._files[0].parent
        return Path(".")

    def _sort(self) -> None:
        if not self._files:
            QMessageBox.warning(self, "提示", "请先添加 PDF 文件")
            return
        pattern = self.ui.edit_pattern.text().strip()
        if not pattern:
            QMessageBox.warning(self, "提示", "请先填写匹配格式(正则表达式)")
            return
        try:
            compile_pattern(pattern)
        except ValueError as e:
            QMessageBox.warning(self, "匹配格式无效", str(e))
            return
        # 避免重复启动(重复点击不泄漏多个 worker)
        if self._worker is not None and self._worker.isRunning():
            return
        outdir = self._resolve_outdir()
        # 单文件:输出文件;多文件:输出目录(命名策略由 service 决定)
        if len(self._files) == 1:
            output: Path | None = outdir / f"{self._files[0].stem}{SORTED_MARKER}.pdf"
        else:
            output = outdir
        worker = PdfSortWorker(self._svc, list(self._files), output, self._options(), parent=self)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_sort_ok)
        worker.failed.connect(self._on_sort_failed)
        self._worker = worker  # 持有引用防 GC
        self.ui.btn_sort.setEnabled(False)
        self.ui.lbl_status.setText("排序中…")
        worker.start()

    def _on_progress(self, current: int, total: int, msg: str) -> None:
        self.ui.lbl_status.setText(self._controller.format_progress(current, total, msg))

    def _on_sort_ok(self, result: Any) -> None:
        self._worker = None
        self.ui.btn_sort.setEnabled(True)
        self._populate_table(result)
        summary = self._controller.summarize(result)
        self.ui.lbl_status.setText(summary)
        if result.success:
            outputs = [Path(f.output) for f in result.sorted_files if f.output is not None]
            if outputs:
                settings.set(_LAST_OUTDIR_KEY, str(outputs[0].parent))
            QMessageBox.information(self, "排序完成", summary)
        else:
            QMessageBox.warning(self, "未生成输出", summary + "\n\n源文件均未被修改。")

    def _on_sort_failed(self, msg: str) -> None:
        self._worker = None
        self.ui.btn_sort.setEnabled(True)
        self.ui.lbl_status.setText("排序失败")
        QMessageBox.critical(self, "排序失败", msg)

    def _populate_table(self, result: Any) -> None:
        """结果表格:每个已处理文件每页一行(原页->新页+排序文字),失败文件浅黄行。"""
        rows: list[tuple[list[str], bool]] = []
        for f in result.sorted_files:
            prefix = "" if f.output is not None else "顺序未变,"
            for p in f.pages:
                new_pos = str(p.new_index + 1) if p.new_index >= 0 else "-"
                status = prefix + ("已排序" if p.matched else "未匹配")
                rows.append(
                    ([f.file, str(p.page + 1), new_pos, p.key if p.matched else "—", status], False)
                )
        rows += [([f.file, "", "", "", f"失败:{f.error}"], True) for f in result.failed]
        self.ui.table.setRowCount(len(rows))
        for r, (values, is_failed) in enumerate(rows):
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                if is_failed:
                    item.setBackground(QBrush(_FAIL_COLOR))
                self.ui.table.setItem(r, c, item)

    def closeEvent(self, event: QCloseEvent) -> None:
        """关闭窗口时停止仍在运行的排序 worker,防泄漏(与 InvoiceTab 同款)。"""
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.quit()
            worker.wait(3000)
        self._worker = None
        super().closeEvent(event)
