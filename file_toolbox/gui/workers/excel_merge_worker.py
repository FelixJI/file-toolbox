"""Excel 合并后台 worker(QThread)。

把 ExcelMergeService.merge 搬到后台线程,避免大文件读写期间冻结 GUI。
与 InvoiceParseWorker 同范式:纯 openpyxl,不需要 COM 初始化。

信号(均跨线程安全投递回主线程):
  progress(int, int, str)  — (current, total, message)
  finished_ok(object)      — MergeResult(含 cancelled/success 语义)
  failed(str)              — 错误信息(中文友好)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.core.excel_merge import MergeOptions


class ExcelMergeWorker(QThread, LoggableMixin):
    """Excel 合并后台线程。

    用法(主线程):
      worker = ExcelMergeWorker(svc, files, output, options)
      worker.progress.connect(on_progress)
      worker.finished_ok.connect(on_done)
      worker.failed.connect(on_error)
      worker.start()
    """

    progress = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        svc: Any,
        files: list[Path],
        output: Path,
        options: MergeOptions,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = svc
        self._files = list(files)
        self._output = output
        self._options = options
        self._cancel = False

    def cancel(self) -> None:
        """请求取消(下一个源文件前生效)。"""
        self._cancel = True

    def _cancel_check(self) -> bool:
        return self._cancel

    def run(self) -> None:  # noqa: D401 (QThread 命名)
        """worker 入口(在后台线程执行)。"""
        try:
            self.logger.info("Excel 合并 worker 开始 files=%d", len(self._files))
            result = self._svc.merge(
                self._files,
                self._output,
                self._options,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                cancel_check=self._cancel_check,
            )
            self.logger.info(
                "Excel 合并 worker 完成 files=%d cancelled=%s",
                len(self._files),
                result.cancelled,
            )
            self.finished_ok.emit(result)
        except Exception as e:  # noqa: BLE001 - 任意异常转 failed 信号
            self.logger.exception("Excel 合并 worker 异常 files=%d", len(self._files))
            self.failed.emit(str(e))
