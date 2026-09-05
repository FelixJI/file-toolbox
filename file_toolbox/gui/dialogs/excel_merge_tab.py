"""Excel 合并 Tab:选文件 -> 后台合并 -> 结果表格。

把多个 .xlsx/.xlsm 的工作表合并为一个新工作簿(纯 openpyxl,不依赖 Office)。
UI 布局由 generated/ui_excel_merge_dialog.py 的 Ui_ExcelMergeDialog(setupUi)
构建,本类只做信号连接 + 业务编排(与其他 Tab 一致)。
"""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtGui import QBrush, QCloseEvent, QColor
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QWidget

from file_toolbox.common import settings
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.excel_merge import (
    DEFAULT_OUTPUT_NAME,
    SUPPORTED_SUFFIXES,
    ExcelMergeService,
)
from file_toolbox.gui.controllers.excel_merge_controller import ExcelMergeController
from file_toolbox.gui.generated.ui_excel_merge_dialog import Ui_ExcelMergeDialog
from file_toolbox.gui.workers.excel_merge_worker import ExcelMergeWorker

_FAIL_COLOR = QColor(255, 242, 204)  # 浅黄(失败行)
# 上次输出目录的 settings key:输出框留空时默认复用,避免每次落到程序目录
_LAST_OUTDIR_KEY = "excel_merge/last_output_dir"
_logger = logging.getLogger(__name__)


class ExcelMergeTab(QWidget):
    """Excel 合并 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_ExcelMergeDialog()
        self.ui.setupUi(self)
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = ExcelMergeService(history_store=self._history)
        self._controller = ExcelMergeController()
        self._files: list[Path] = []
        self._worker: ExcelMergeWorker | None = None
        self._connect()

    def _connect(self) -> None:
        self.ui.btn_add_files.clicked.connect(self._add_files)
        self.ui.btn_add_folder.clicked.connect(self._add_folder)
        self.ui.btn_clear.clicked.connect(self._clear)
        self.ui.btn_browse.clicked.connect(self._browse_outdir)
        self.ui.btn_merge.clicked.connect(self._merge)

    # --- 文件管理 ---

    def _is_source(self, path: Path) -> bool:
        """受支持的源文件:后缀匹配且非 Office 临时文件(~$ 开头)。"""
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
        exts = " ".join(f"*{ext}" for ext in SUPPORTED_SUFFIXES)
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 Excel 文件", "", f"Excel 文件 ({exts})")
        self._add_paths([Path(p) for p in paths])

    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not d:
            return
        recursive = (
            QMessageBox.question(
                self,
                "选择模式",
                "是否包含子文件夹中的 Excel 文件？",
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
            self.ui.cmb_naming.currentIndex(),
            self.ui.cmb_mode.currentIndex(),
            self.ui.chk_hidden.isChecked(),
        )

    # --- 合并 ---

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

    def _merge(self) -> None:
        if not self._files:
            QMessageBox.warning(self, "提示", "请先添加 Excel 文件")
            return
        # 避免重复启动(重复点击不泄漏多个 worker)
        if self._worker is not None and self._worker.isRunning():
            return
        outdir = self._resolve_outdir()
        output = outdir / DEFAULT_OUTPUT_NAME
        worker = ExcelMergeWorker(
            self._svc, list(self._files), output, self._options(), parent=self
        )
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_merge_ok)
        worker.failed.connect(self._on_merge_failed)
        self._worker = worker  # 持有引用防 GC
        self.ui.btn_merge.setEnabled(False)
        self.ui.lbl_status.setText("合并中…")
        worker.start()

    def _on_progress(self, current: int, total: int, msg: str) -> None:
        self.ui.lbl_status.setText(self._controller.format_progress(current, total, msg))

    def _on_merge_ok(self, result: Any) -> None:
        self._worker = None
        self.ui.btn_merge.setEnabled(True)
        self._populate_table(result)
        summary = self._controller.summarize(result)
        self.ui.lbl_status.setText(summary)
        if result.success:
            settings.set(_LAST_OUTDIR_KEY, str(Path(result.output).parent))
            QMessageBox.information(self, "合并完成", summary)
        else:
            QMessageBox.warning(self, "未生成输出", summary + "\n\n源文件均未被修改。")

    def _on_merge_failed(self, msg: str) -> None:
        self._worker = None
        self.ui.btn_merge.setEnabled(True)
        self.ui.lbl_status.setText("合并失败")
        QMessageBox.critical(self, "合并失败", msg)

    def _populate_table(self, result: Any) -> None:
        """结果表格:已合并工作表 + 失败文件(失败行浅黄)。"""
        rows: list[tuple[list[str], bool]] = [
            ([m.file, m.sheet, m.target_name, "已合并"], False) for m in result.sheets
        ]
        rows += [([f.file, "", "", f"失败:{f.error}"], True) for f in result.failed]
        self.ui.table.setRowCount(len(rows))
        for r, (values, is_failed) in enumerate(rows):
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                if is_failed:
                    item.setBackground(QBrush(_FAIL_COLOR))
                self.ui.table.setItem(r, c, item)

    def closeEvent(self, event: QCloseEvent) -> None:
        """关闭窗口时停止仍在运行的合并 worker,防泄漏(与 InvoiceTab 同款)。"""
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.quit()
            worker.wait(3000)
        self._worker = None
        super().closeEvent(event)
