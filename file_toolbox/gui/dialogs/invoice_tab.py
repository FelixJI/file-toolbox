"""发票识别 Tab:选文件 -> 解析 -> 表格预览 -> 导出。

标色:重复行黄底,PDF 弱解析行灰底。嵌入主窗口作为第 5 个 Tab。
UI 布局由 generated/ui_invoice_dialog.py 的 Ui_InvoiceDialog(setupUi) 构建,
本类只做信号连接 + 业务编排(与其他 Tab 一致)。
"""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton, QWidget

from file_toolbox.common import settings
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.invoice.service import InvoiceService
from file_toolbox.core.invoice.types import ParseResult
from file_toolbox.gui.batch_mixin import FileImportMixin
from file_toolbox.gui.controllers.invoice_controller import InvoiceController
from file_toolbox.gui.file_models import table_model
from file_toolbox.gui.generated.ui_invoice_dialog import Ui_InvoiceDialog
from file_toolbox.gui.task_lifecycle import TaskLifecycle
from file_toolbox.gui.workers.invoice_worker import InvoiceParseWorker

_DUP_COLOR = QColor(255, 242, 204)  # 浅黄(重复)
_PDF_COLOR = QColor(230, 230, 230)  # 浅灰(PDF 弱解析)
_INVOICE_EXTS = (".zip", ".xml", ".ofd", ".pdf")
# 上次导出目录的 settings key:输出框留空时默认复用,避免每次落到程序目录
_LAST_OUTDIR_KEY = "invoice/last_output_dir"
_logger = logging.getLogger(__name__)


class InvoiceTab(QWidget, FileImportMixin):
    """发票识别 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 生命周期句柄:单一事实保存当前任务,只在真实 finished(task.finish)释放
        self._task = TaskLifecycle(self)
        self.ui = Ui_InvoiceDialog()
        self.ui.setupUi(self)
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = InvoiceService(history_store=self._history)
        self._controller = InvoiceController()
        self._result: ParseResult | None = None
        self._files: list[Path] = []
        self._init_import(self._files, self.ui.list_files, resolved=True, check_files=True)
        self._scan_cancel = QPushButton("取消扫描", self)
        layout = self.layout()
        assert layout is not None
        layout.addWidget(self._scan_cancel)
        self._scan_cancel.hide()
        self._scan_cancel.clicked.connect(self._task.cancel)
        self._connect()

    # 兼容旧 _parse_worker 字段:读写均转发 TaskLifecycle;只有真实
    # finished(task.finish 精确身份校验)才清空,结果信号不提前释放引用。
    @property
    def _parse_worker(self) -> QThread | None:
        return self._task.worker

    @_parse_worker.setter
    def _parse_worker(self, value: QThread | None) -> None:
        self._task.worker = value

    def _connect(self) -> None:
        self.ui.btn_add_files.clicked.connect(self._add_files)
        self.ui.btn_add_folder.clicked.connect(self._add_folder)
        self.ui.btn_clear.clicked.connect(self._clear)
        self.ui.btn_browse.clicked.connect(self._browse_outdir)
        self.ui.btn_parse.clicked.connect(self._parse)
        self.ui.btn_export.clicked.connect(self._export)

    # --- 文件管理 ---
    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择发票文件", "", "发票文件 (*.zip *.xml *.ofd *.pdf)"
        )
        if paths:
            # 显式选择原本不滤后缀、不查存在、不去重；仅移入同一批次队列。
            self._queue_import([Path(p) for p in paths], lambda p: True, unchecked=True)

    def _is_source(self, path: Path) -> bool:
        return path.suffix.lower() in _INVOICE_EXTS

    def _add_folder(self) -> None:
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
        self._queue_import([], self._is_source, Path(d), recursive)

    def _import_status(self, text: str) -> None:
        self.ui.lbl_status.setText(text)

    def _import_busy(self, busy: bool) -> None:
        self._scan_cancel.setVisible(busy)

    def _clear(self) -> None:
        self._invalidate_import()
        table_model(self.ui.table).replace_rows([])
        self._result = None
        self.ui.btn_export.setEnabled(False)
        self.ui.lbl_status.setText("就绪")

    def _browse_outdir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.ui.edit_outdir.setText(d)

    def _dedupe_strategy(self) -> str:
        return self._controller.dedupe_strategy(self.ui.cmb_dedupe.currentIndex())

    def _format(self) -> str:
        return self._controller.format(self.ui.rb_json.isChecked(), self.ui.rb_both.isChecked())

    # --- 解析 ---
    def _parse(self) -> None:
        if not self._files:
            QMessageBox.warning(self, "提示", "请先添加发票文件")
            return
        # 避免重复启动(重复点击不泄漏多个 worker):任务尚未在真实 finished 中释放
        # (或正在延迟关闭)时一律拒绝,不以 isRunning() 为准
        if self._task.busy:
            return
        strategy = self._dedupe_strategy()
        worker = InvoiceParseWorker(self._svc, list(self._files), strategy, parent=self)
        worker.progress.connect(self._on_parse_progress)
        worker.finished_ok.connect(self._on_parse_ok)
        worker.failed.connect(self._on_parse_failed)
        worker.finished.connect(self._on_worker_finished)
        self._business_generation = self._import_generation
        self._task.track(worker)  # 持有引用防 GC;在 start 前登记
        # 解析期间禁用相关按钮
        self.ui.btn_parse.setEnabled(False)
        self.ui.btn_export.setEnabled(False)
        self.ui.lbl_status.setText("解析中…")
        worker.start()

    def _on_parse_progress(self, current: int, total: int) -> None:
        if not self._accept_business_result():
            return
        self.ui.lbl_status.setText(f"解析中… {current}/{total}")

    def _on_parse_ok(self, result: Any) -> None:
        """结果槽:只渲染结果;引用释放与启动按钮恢复等真实 finished。"""
        if not self._accept_business_result():
            return
        self._result = result
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

    def _on_parse_failed(self, msg: str) -> None:
        if not self._accept_business_result():
            return
        # 解析失败:按已有结果重置 btn_export(若曾解析成功则保留可导出状态)
        self.ui.btn_export.setEnabled(self._result is not None and bool(self._result.invoices))
        self.ui.lbl_status.setText("解析失败")
        if not self._task.close_pending:
            QMessageBox.warning(self, "解析失败", msg)

    def _on_worker_finished(self) -> None:
        """真实 finished 后释放线程并恢复启动按钮;延迟关闭由 TaskLifecycle 续接。"""
        if not self._task.finish(self.sender()):
            return
        self.ui.btn_parse.setEnabled(True)

        self._resume_import()

    def closeEvent(self, event: QCloseEvent) -> None:
        """任务未结束时延迟关闭:协作取消后等真实 finished 异步重关。

        InvoiceParseWorker 是无事件循环的 QThread(quit() 无效),仅靠协作式 cancel()
        在文件间停止。旧实现在这里同步 cancel + wait(3000) 后假定线程结束——等待
        冻结关闭,且 wait 超时后清理仍可能撞上仍在运行的线程(持有 self 为 parent,
        进程退出可能崩溃/泄漏)。现在引用释放/重新关闭全部由 TaskLifecycle 在
        真实 finished 消费时完成。
        """
        if self._task.defer_close(event):
            self.ui.lbl_status.setText("正在等待解析安全结束,完成后自动关闭…")
            return
        super().closeEvent(event)

    def _populate_table(self) -> None:
        assert self._result is not None
        table_model(self.ui.table).replace_rows(
            [
                (
                    [
                        inv.invoice_number,
                        inv.invoice_type,
                        inv.issue_date,
                        inv.seller_name,
                        inv.buyer_name,
                        inv.amount_with_tax,
                        inv.source_file,
                        inv.parse_method,
                    ],
                    _DUP_COLOR
                    if inv.is_duplicate
                    else _PDF_COLOR
                    if inv.parse_method == "pdf"
                    else None,
                )
                for inv in self._result.invoices
            ]
        )

    # --- 导出 ---
    def _resolve_outdir(self) -> Path:
        """导出目录解析:输出框内容 > 上次导出目录(仍存在) > 首个源文件所在目录 > 当前目录。

        输出框留空时不再落到 "."(GUI 双击启动时即程序目录),默认跟随上次导出
        或源文件所在目录。
        """
        text = self.ui.edit_outdir.text().strip()
        if text:
            return Path(text)
        last = settings.get(_LAST_OUTDIR_KEY)
        if isinstance(last, str) and last.strip() and Path(last.strip()).is_dir():
            return Path(last.strip())
        if self._files:
            return self._files[0].parent
        return Path(".")

    def _export(self) -> None:
        if not self._result or not self._result.invoices:
            QMessageBox.warning(self, "提示", "无数据可导出")
            return
        outdir_path = self._resolve_outdir()
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
                file_count=len(self._files),
                invoice_count=len(self._result.invoices),
            )
        except Exception as e:  # noqa: BLE001
            _logger.exception("发票导出失败 output_dir=%s format=%s", outdir_path, self._format())
            QMessageBox.critical(self, "导出失败", str(e))
            return
        # 历史记录已下沉 InvoiceService.export(注入了 history_store)
        settings.set(_LAST_OUTDIR_KEY, str(outdir_path))
        QMessageBox.information(self, "完成", "已导出:\n" + "\n".join(str(w) for w in written))
