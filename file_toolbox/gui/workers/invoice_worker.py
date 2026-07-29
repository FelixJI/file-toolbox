"""发票解析后台 worker(QThread)。

把 InvoiceService.parse_files 搬到后台线程,避免大量 PDF/OFD/XML 解析时冻结 GUI。
与 PdfGenerateWorker 同范式,但发票解析是纯 Python/pdfplumber,不需要 COM 初始化。

信号(均跨线程安全投递回主线程):
  progress(int, int)  — (current, total)
  finished_ok(object) — ParseResult
  failed(str)         — 错误信息(中文友好)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from file_toolbox.common.loggable import LoggableMixin


class InvoiceParseWorker(QThread, LoggableMixin):
    """发票解析后台线程。

    用法(主线程):
      worker = InvoiceParseWorker(svc, files, dedupe_strategy)
      worker.progress.connect(on_progress)
      worker.finished_ok.connect(on_done)
      worker.failed.connect(on_error)
      worker.start()
    """

    progress = Signal(int, int)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        svc: Any,
        files: list[Path],
        dedupe_strategy: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = svc
        self._files = list(files)
        self._dedupe_strategy = dedupe_strategy
        self._cancel = False

    def cancel(self) -> None:
        """请求取消(下一个文件前生效)。"""
        self._cancel = True

    def _cancel_check(self) -> bool:
        return self._cancel

    def run(self) -> None:  # noqa: D401 (QThread 命名)
        """worker 入口(在后台线程执行)。"""
        try:
            result = self._svc.parse_files(
                self._files,
                dedupe_strategy=self._dedupe_strategy,
                progress_callback=lambda c, t: self.progress.emit(c, t),
                cancel_check=self._cancel_check,
            )
            self.finished_ok.emit(result)
        except Exception as e:  # noqa: BLE001 - 任意异常转 failed 信号
            self.logger.error(f"发票解析 worker 异常: {e}")
            self.failed.emit(str(e))
