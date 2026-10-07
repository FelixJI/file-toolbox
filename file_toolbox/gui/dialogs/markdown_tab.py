"""Markdown 转换 Tab:选文件 -> 后台批量转 Word/Excel -> 结果表格。

把 .md 批量转为 Word(.docx,经 Pandoc)或 Excel(.xlsx,表格独立工作表,
可选正文工作表)。UI 布局由 generated/ui_markdown_dialog.py 的
Ui_MarkdownConvertDialog(setupUi)构建,本类只做信号连接 + 业务编排
(与其他 Tab 一致,不另设 controller 层)。
"""

import logging
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QBrush, QCloseEvent, QColor
from PySide6.QtWidgets import QFileDialog, QHeaderView, QMessageBox, QTableWidgetItem, QWidget

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.markdown_convert import (
    SUPPORTED_SUFFIXES,
    ConversionResult,
    MarkdownConvertService,
)
from file_toolbox.gui.generated.ui_markdown_dialog import Ui_MarkdownConvertDialog
from file_toolbox.gui.workers.markdown_worker import MarkdownConvertWorker

_FAIL_COLOR = QColor(255, 242, 204)  # 浅黄(失败行)
# 目标格式/Excel 模式:下拉框索引 -> service 字符串(与 core 契约一致)
_TARGETS = ("docx", "xlsx")
_EXCEL_MODES = ("tables", "document")
_HINT_DOCX = (
    "Word 输出由 Pandoc 转换:保留标题、列表、表格、代码、链接与公式;"
    "不加载外部图片,含图片的文件会转换失败并在结果中报告,不会静默成功。"
)
_HINT_XLSX = (
    "Excel 输出:每个源文件一个工作簿,每张表格独立工作表;"
    "“包含正文”模式额外生成正文工作表,表格仍独立工作表。"
)
_logger = logging.getLogger(__name__)


class MarkdownConvertTab(QWidget):
    """Markdown 转换 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_MarkdownConvertDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI code
        header = self.ui.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = MarkdownConvertService(history_store=self._history)
        self._files: list[Path] = []
        self._worker: MarkdownConvertWorker | None = None
        self._close_pending = False
        self._connect()
        self._sync_target_ui()

    @property
    def close_pending(self) -> bool:
        return self._close_pending

    def _connect(self) -> None:
        self.ui.btn_add_files.clicked.connect(self._add_files)
        self.ui.btn_add_folder.clicked.connect(self._add_folder)
        self.ui.btn_clear.clicked.connect(self._clear)
        self.ui.btn_browse.clicked.connect(self._browse_outdir)
        self.ui.btn_convert.clicked.connect(self._convert)
        self.ui.btn_cancel.clicked.connect(self._cancel_run)
        self.ui.cmb_target.currentIndexChanged.connect(self._sync_target_ui)

    # --- 文件管理 ---

    def _is_source(self, path: Path) -> bool:
        """受支持的源文件:后缀匹配且非编辑器临时文件(~$ 开头)。"""
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
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择 Markdown 文件", "", f"Markdown 文件 ({exts})"
        )
        self._add_paths([Path(p) for p in paths])

    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not d:
            return
        recursive = (
            QMessageBox.question(
                self,
                "选择模式",
                "是否包含子文件夹中的 Markdown 文件？",
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

    # --- 目标格式联动 ---

    def _sync_target_ui(self) -> None:
        """目标格式切换:Excel 模式仅对 .xlsx 有效;提示随目标更新。"""
        is_excel = self._target() == "xlsx"
        self.ui.cmb_excel_mode.setEnabled(is_excel)
        self.ui.label_excel_mode.setEnabled(is_excel)
        self.ui.lbl_hint.setText(_HINT_XLSX if is_excel else _HINT_DOCX)

    def _target(self) -> str:
        return _TARGETS[self.ui.cmb_target.currentIndex()]

    def _excel_mode(self) -> str:
        return _EXCEL_MODES[self.ui.cmb_excel_mode.currentIndex()]

    # --- 转换 ---

    def _convert(self) -> None:
        if not self._files:
            QMessageBox.warning(self, "提示", "请先添加 Markdown 文件")
            return
        # 避免重复启动(重复点击不泄漏多个 worker)
        if self._worker is not None or self._close_pending:
            return
        text = self.ui.edit_outdir.text().strip()
        # 输出目录留空:各源文件旁输出(None 由 service 解释)
        output_dir = Path(text) if text else None
        worker = MarkdownConvertWorker(
            self._svc,
            list(self._files),
            output_dir,
            self._target(),
            self._excel_mode(),
            parent=self,
        )
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_convert_ok)
        worker.failed.connect(self._on_convert_failed)
        worker.warning.connect(self._on_history_warning)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker  # 持有引用防 GC
        self._set_running(True)
        self.ui.lbl_status.setText("转换中…")
        worker.start()

    def _set_running(self, running: bool) -> None:
        """工作期间锁住输入控件,仅保留取消可用。"""
        for w in (
            self.ui.btn_add_files,
            self.ui.btn_add_folder,
            self.ui.btn_clear,
            self.ui.btn_browse,
            self.ui.edit_outdir,
            self.ui.cmb_target,
            self.ui.cmb_excel_mode,
            self.ui.btn_convert,
        ):
            w.setEnabled(not running)
        self.ui.btn_cancel.setEnabled(running)

    def _cancel_run(self) -> None:
        worker = self._worker
        if worker is None:
            return
        worker.cancel()
        self.ui.btn_cancel.setEnabled(False)
        self.ui.lbl_status.setText("正在取消,等待当前文件安全结束…")

    def _on_progress(self, current: int, total: int, msg: str) -> None:
        if self.sender() is not None and self.sender() is not self._worker:
            return
        self.ui.lbl_status.setText(f"[{current}/{total}] {msg}")

    def _on_convert_ok(self, result: ConversionResult) -> None:
        if self.sender() is not None and self.sender() is not self._worker:
            return
        self._populate_table(result)
        summary = self._summarize(result)
        self.ui.lbl_status.setText(summary)
        outputs = [item.output for item in result.items if item.output is not None]
        if self._close_pending:
            return
        if result.cancelled:
            details = "\n".join(str(p) for p in outputs)
            QMessageBox.warning(
                self, "转换已取消", summary + "\n" + details + "\n源文件均未被修改。"
            )
        elif result.success:
            QMessageBox.information(self, "转换完成", summary)
        else:
            QMessageBox.warning(self, "部分失败", summary)

    def _summarize(self, result: ConversionResult) -> str:
        """结果摘要:成功/跳过/失败计数;取消时前缀“已取消”。"""
        ok = sum(1 for i in result.items if i.output is not None and not i.skipped)
        skipped = sum(1 for i in result.items if i.skipped)
        failed = len(result.items) - ok - skipped
        parts = [f"成功 {ok}"]
        if skipped:
            parts.append(f"跳过 {skipped}")
        if failed:
            parts.append(f"失败 {failed}")
        base = "、".join(parts)
        return f"已取消:{base}" if result.cancelled else f"转换完成:{base}"

    def _populate_table(self, result: ConversionResult) -> None:
        """结果表格:每个源文件一行;失败行浅黄,跳过行状态“已跳过”。"""
        rows: list[tuple[list[str], bool]] = []
        for item in result.items:
            if item.skipped:
                rows.append(([item.source.name, "已跳过", "—", item.error], False))
            elif item.output is not None:
                rows.append(([item.source.name, "成功", str(item.output), ""], False))
            else:
                rows.append(([item.source.name, "失败", "—", item.error], True))
        self.ui.table.setRowCount(len(rows))
        for r, (values, is_failed) in enumerate(rows):
            for c, val in enumerate(values):
                cell_item = QTableWidgetItem(val)
                cell_item.setToolTip(val)
                if is_failed:
                    cell_item.setBackground(QBrush(_FAIL_COLOR))
                self.ui.table.setItem(r, c, cell_item)

    def _on_history_warning(self, msg: str) -> None:
        if self.sender() is not None and self.sender() is not self._worker:
            return
        if not self._close_pending:
            QMessageBox.warning(self, "历史保存失败", msg)

    def _on_convert_failed(self, msg: str) -> None:
        if self.sender() is not None and self.sender() is not self._worker:
            return
        self.ui.lbl_status.setText("转换失败")
        if not self._close_pending:
            QMessageBox.critical(self, "转换失败", msg)

    def _on_worker_finished(self) -> None:
        """结果不释放线程;只消费当前 worker 的真实 finished。"""
        worker = self._worker
        if worker is None or self.sender() is not worker:
            return
        self._worker = None
        worker.deleteLater()
        self._set_running(False)
        # _set_running 会无条件恢复模式控件;Word 目标下须重新禁用 Excel 模式
        self._sync_target_ui()
        if self._close_pending:
            self._close_pending = False
            QTimer.singleShot(0, self.window().close)

    def closeEvent(self, event: QCloseEvent) -> None:
        """协作取消后异步等待 finished,保留窗口及正在写入的线程。"""
        if self._worker is not None:
            if not self._close_pending:
                self._worker.cancel()
            self._close_pending = True
            self.ui.lbl_status.setText("正在等待转换安全结束,完成后自动关闭…")
            event.ignore()
            return
        super().closeEvent(event)
