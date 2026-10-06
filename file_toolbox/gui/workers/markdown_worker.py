"""Markdown 转换后台 worker(QThread)。

把 MarkdownConvertService.convert 搬到后台线程,避免 Pandoc/工作簿写出期间冻结
GUI。与 ExcelMergeWorker 同范式:纯文件转换,不需要 COM 初始化。

信号(均跨线程安全投递回主线程):
  progress(int, int, str)  — (current, total, message)
  finished_ok(object)      — ConversionResult(含 cancelled/success 语义)
  failed(str)              — 错误信息(中文友好)
  warning(str)             — 历史等附属保存告警,不丢弃已完成结果
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.common.operation_errors import OperationResultError
from file_toolbox.core.markdown_convert import MarkdownConvertService


class MarkdownConvertWorker(QThread, LoggableMixin):
    """Markdown 批量转换后台线程。

    用法(主线程):
      worker = MarkdownConvertWorker(svc, files, output_dir, target, excel_mode)
      worker.progress.connect(on_progress)
      worker.finished_ok.connect(on_done)
      worker.start()
    """

    progress = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)
    warning = Signal(str)

    def __init__(
        self,
        svc: MarkdownConvertService,
        files: list[Path],
        output_dir: Path | None,
        target: str,
        excel_mode: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = svc
        self._files = list(files)
        self._output_dir = output_dir
        self._target = target
        self._excel_mode = excel_mode
        self._cancel = False

    def cancel(self) -> None:
        """请求取消(下一个源文件前生效)。"""
        self._cancel = True

    def _cancel_check(self) -> bool:
        return self._cancel

    def run(self) -> None:  # noqa: D401 (QThread 命名)
        """worker 入口(在后台线程执行)。"""
        try:
            self.logger.info(
                "Markdown 转换 worker 开始 files=%d target=%s mode=%s",
                len(self._files),
                self._target,
                self._excel_mode,
            )
            result = self._svc.convert(
                self._files,
                self._output_dir,
                target=self._target,
                excel_mode=self._excel_mode,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                cancel_check=self._cancel_check,
            )
            self.logger.info(
                "Markdown 转换 worker 完成 files=%d cancelled=%s",
                len(self._files),
                result.cancelled,
            )
            self.finished_ok.emit(result)
        except OperationResultError as error:
            # 历史等附属操作失败:业务结果(已写出的输出)仍要完整呈现给用户。
            self.logger.warning("Markdown 转换附属操作失败: %s", error)
            self.finished_ok.emit(error.result)
            self.warning.emit(str(error))
        except Exception as e:  # noqa: BLE001 - 任意异常转 failed 信号
            self.logger.exception("Markdown 转换 worker 异常 files=%d", len(self._files))
            self.failed.emit(str(e))
