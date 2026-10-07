"""Excel 合并 Tab:选文件 -> 后台合并 -> 结果表格。

把多个 .xlsx/.xlsm 的工作表合并为一个新工作簿(纯 openpyxl,不依赖 Office)。
UI 布局由 generated/ui_excel_merge_dialog.py 的 Ui_ExcelMergeDialog(setupUi)
构建,本类只做信号连接 + 业务编排(与其他 Tab 一致)。
"""

import logging
from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton, QWidget

from file_toolbox.common import settings
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.excel_merge import (
    DEFAULT_OUTPUT_NAME,
    SUPPORTED_SUFFIXES,
    ExcelMergeService,
    MergeOptions,
    MergeResult,
)
from file_toolbox.gui.batch_mixin import FileImportMixin
from file_toolbox.gui.controllers.excel_merge_controller import ExcelMergeController
from file_toolbox.gui.file_models import table_model
from file_toolbox.gui.generated.ui_excel_merge_dialog import Ui_ExcelMergeDialog
from file_toolbox.gui.task_lifecycle import TaskLifecycle
from file_toolbox.gui.workers.excel_merge_worker import ExcelMergeWorker

_FAIL_COLOR = QColor(255, 242, 204)  # 浅黄(失败行)
# 上次输出目录的 settings key:输出框留空时默认复用,避免每次落到程序目录
_LAST_OUTDIR_KEY = "excel_merge/last_output_dir"
_logger = logging.getLogger(__name__)


class ExcelMergeTab(QWidget, FileImportMixin):
    """Excel 合并 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 生命周期句柄:单一事实保存当前任务与延迟关闭,只在真实 finished 释放
        self._task = TaskLifecycle(self)
        self.ui = Ui_ExcelMergeDialog()
        self.ui.setupUi(self)
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = ExcelMergeService(history_store=self._history)
        self._controller = ExcelMergeController()
        self._files: list[Path] = []
        self._init_import(self._files, self.ui.list_files, resolved=True, check_files=True)
        self._scan_cancel = QPushButton("取消扫描", self)
        layout = self.layout()
        assert layout is not None
        layout.addWidget(self._scan_cancel)
        self._scan_cancel.hide()
        self._scan_cancel.clicked.connect(self._task.cancel)
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
        """是否正等待合并 worker 安全退出后重试关闭。"""
        return self._task.close_pending

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
        self._queue_import(paths, self._is_source)

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

    def _options(self) -> MergeOptions:
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
        # 避免重复启动(重复点击不泄漏多个 worker):任务未释放或延迟关闭中一律拒绝,
        # 不以 isRunning() 为准——排队的 finished 尚未消费时同样不能开下一轮
        if self._task.busy:
            return
        outdir = self._resolve_outdir()
        output = outdir / DEFAULT_OUTPUT_NAME
        worker = ExcelMergeWorker(
            self._svc, list(self._files), output, self._options(), parent=self
        )
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_merge_ok)
        worker.failed.connect(self._on_merge_failed)
        worker.warning.connect(self._on_history_warning)
        worker.finished.connect(self._on_worker_finished)
        self._business_generation = self._import_generation
        self._task.track(worker)  # 持有引用防 GC;在 start 前登记
        self.ui.btn_merge.setEnabled(False)
        self.ui.lbl_status.setText("合并中…")
        worker.start()

    def _on_progress(self, current: int, total: int, msg: str) -> None:
        if not self._accept_business_result():
            return
        self.ui.lbl_status.setText(self._controller.format_progress(current, total, msg))

    def _on_merge_ok(self, result: MergeResult) -> None:
        if not self._accept_business_result():
            return
        self._populate_table(result)
        summary = self._controller.summarize(result)
        self.ui.lbl_status.setText(summary)
        preference_warning = ""
        if result.success:
            assert result.output is not None
            try:
                settings.set(_LAST_OUTDIR_KEY, str(result.output.parent))
            except Exception as error:
                _logger.warning("Excel 合并输出目录偏好保存失败: %s", error)
                preference_warning = f"输出文件已保留,但未能记住上次输出目录: {error}"
            if not self._task.close_pending:
                QMessageBox.information(self, "合并完成", summary)
        elif not self._task.close_pending:
            QMessageBox.warning(self, "未生成输出", summary + "\n\n源文件均未被修改。")

        if preference_warning and not self._task.close_pending:
            QMessageBox.warning(self, "偏好保存失败", preference_warning)

    def _on_history_warning(self, msg: str) -> None:
        if not self._accept_business_result():
            return
        if not self._task.close_pending:
            title = "历史保存失败" if msg.startswith("历史保存失败:") else "合并收尾告警"
            QMessageBox.warning(self, title, msg)

    def _on_merge_failed(self, msg: str) -> None:
        if not self._accept_business_result():
            return
        self.ui.lbl_status.setText("合并失败")
        if not self._task.close_pending:
            QMessageBox.critical(self, "合并失败", msg)

    def _populate_table(self, result: MergeResult) -> None:
        """结果表格:已合并工作表 + 失败文件(失败行浅黄)。"""
        rows: list[tuple[list[str], bool]] = [
            ([m.file, m.sheet, m.target_name, "已合并"], False) for m in result.sheets
        ]
        rows += [([f.file, "", "", f"失败:{f.error}"], True) for f in result.failed]
        table_model(self.ui.table).replace_rows(
            [(values, _FAIL_COLOR if failed else None) for values, failed in rows]
        )

    def _on_worker_finished(self) -> None:
        """结果不释放线程;只消费当前 worker 的真实 finished,恢复按钮/续接关闭。"""
        if not self._task.finish(self.sender()):
            return
        self.ui.btn_merge.setEnabled(True)

        self._resume_import()

    def closeEvent(self, event: QCloseEvent) -> None:
        """协作取消后异步等待 finished,保留窗口及正在写入的线程。"""
        if self._task.defer_close(event):
            self.ui.lbl_status.setText("正在等待合并安全结束,完成后自动关闭…")
            return
        super().closeEvent(event)
