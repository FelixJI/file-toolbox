"""PDF 排序 Tab:选文件 -> 后台按文字层排序 -> 结果表格。

按用户给定的正则匹配每页文字(日期/流水号等)作为排序键,重排页面写出新 PDF。
UI 布局由 generated/ui_pdf_sort_dialog.py 的 Ui_PdfSortDialog(setupUi)构建,
本类只做信号连接 + 业务编排(与其他 Tab 一致)。
"""

import logging
from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton, QWidget

from file_toolbox.common import settings
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.pdf_sort import (
    SORTED_MARKER,
    SUPPORTED_SUFFIXES,
    PdfSortService,
    SortOptions,
    SortResult,
    compile_pattern,
)
from file_toolbox.gui.batch_mixin import FileImportMixin
from file_toolbox.gui.controllers.pdf_sort_controller import PdfSortController
from file_toolbox.gui.file_models import table_model
from file_toolbox.gui.generated.ui_pdf_sort_dialog import Ui_PdfSortDialog
from file_toolbox.gui.task_lifecycle import TaskLifecycle
from file_toolbox.gui.workers.pdf_sort_worker import PdfSortWorker

_FAIL_COLOR = QColor(255, 242, 204)  # 浅黄(失败行)
# 上次输出目录的 settings key:输出框留空时默认复用,避免每次落到程序目录
_LAST_OUTDIR_KEY = "pdf_sort/last_output_dir"
_logger = logging.getLogger(__name__)


class PdfSortTab(QWidget, FileImportMixin):
    """PDF 排序 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 生命周期句柄:单一事实保存当前任务与延迟关闭,只在真实 finished 释放
        self._task = TaskLifecycle(self)
        self.ui = Ui_PdfSortDialog()
        self.ui.setupUi(self)
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = PdfSortService(history_store=self._history)
        self._controller = PdfSortController()
        self._files: list[Path] = []
        self._init_import(self._files, self.ui.list_files, resolved=True, check_files=True)
        self._scan_cancel = QPushButton("取消扫描", self)
        layout = self.layout()
        assert layout is not None
        layout.addWidget(self._scan_cancel)
        self._scan_cancel.hide()
        self._scan_cancel.clicked.connect(self._cancel_import)
        self._connect()

    # 兼容旧 _worker 字段:读写均转发 TaskLifecycle;只有真实
    # finished(task.finish 精确身份校验)才清空,结果信号不提前释放引用。
    @property
    def _worker(self) -> QThread | None:
        return self._task.worker

    @_worker.setter
    def _worker(self, value: QThread | None) -> None:
        self._task.worker = value

    @property
    def close_pending(self) -> bool:
        """是否正等待排序 worker 安全退出后重试关闭。"""
        return self._task.close_pending

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
        self._queue_import(paths, self._is_source)

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
        self._queue_import([], self._is_source, Path(d), recursive)

    def _import_status(self, text: str) -> None:
        self.ui.lbl_status.setText(text)

    def _import_busy(self, busy: bool) -> None:
        self._scan_cancel.setVisible(busy)

    def _clear(self) -> None:
        self._invalidate_import()
        table_model(self.ui.table).replace_rows([])
        self.ui.lbl_status.setText("就绪")

    def _browse_outdir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.ui.edit_outdir.setText(d)

    def _options(self) -> SortOptions:
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
        # 避免重复启动(重复点击不泄漏多个 worker):任务未释放或延迟关闭中一律拒绝,
        # 不以 isRunning() 为准——排队的 finished 尚未消费时同样不能开下一轮
        if self._task.busy:
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
        worker.warning.connect(self._on_history_warning)
        worker.finished.connect(self._on_worker_finished)
        self._business_generation = self._import_generation
        self._task.track(worker)  # 持有引用防 GC;在 start 前登记
        self.ui.btn_sort.setEnabled(False)
        self.ui.lbl_status.setText("排序中…")
        worker.start()

    def _on_progress(self, current: int, total: int, msg: str) -> None:
        if not self._accept_business_result():
            return
        self.ui.lbl_status.setText(self._controller.format_progress(current, total, msg))

    def _on_sort_ok(self, result: SortResult) -> None:
        if not self._accept_business_result():
            return
        self._populate_table(result)
        summary = self._controller.summarize(result)
        self.ui.lbl_status.setText(summary)
        outputs = [Path(f.output) for f in result.sorted_files if f.output is not None]
        preference_warning = ""
        if outputs:
            try:
                settings.set(_LAST_OUTDIR_KEY, str(outputs[0].parent))
            except Exception as error:
                _logger.warning("PDF 排序输出目录偏好保存失败: %s", error)
                preference_warning = f"输出文件已保留,但未能记住上次输出目录: {error}"
        if self._task.close_pending:
            return
        if result.cancelled:
            details = "\n".join(str(path) for path in outputs)
            QMessageBox.warning(
                self, "排序已取消", summary + "\n" + details + "\n源文件均未被修改。"
            )
        elif result.success:
            QMessageBox.information(self, "排序完成", summary)
        else:
            QMessageBox.warning(self, "未生成输出", summary + "\n\n源文件均未被修改。")

        if preference_warning and not self._task.close_pending:
            QMessageBox.warning(self, "偏好保存失败", preference_warning)

    def _on_history_warning(self, msg: str) -> None:
        if not self._accept_business_result():
            return
        if not self._task.close_pending:
            QMessageBox.warning(self, "历史保存失败", msg)

    def _on_sort_failed(self, msg: str) -> None:
        if not self._accept_business_result():
            return
        self.ui.lbl_status.setText("排序失败")
        if not self._task.close_pending:
            QMessageBox.critical(self, "排序失败", msg)

    def _populate_table(self, result: SortResult) -> None:
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
        table_model(self.ui.table).replace_rows(
            [(values, _FAIL_COLOR if failed else None) for values, failed in rows]
        )

    def _on_worker_finished(self) -> None:
        """结果不释放线程;只消费当前 worker 的真实 finished,恢复按钮/续接关闭。"""
        if not self._task.finish(self.sender()):
            return
        self.ui.btn_sort.setEnabled(True)

        self._resume_import()

    def closeEvent(self, event: QCloseEvent) -> None:
        """协作取消后异步等待 finished,保留窗口及正在写入的线程。"""
        if self._task.defer_close(event):
            self.ui.lbl_status.setText("正在等待排序安全结束,完成后自动关闭…")
            return
        super().closeEvent(event)
