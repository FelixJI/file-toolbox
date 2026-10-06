"""PDF 生成后台 worker(QThread)。

把 PDFGeneratorService.batch_generate 搬到后台线程,避免转换期间冻结 GUI。
worker 负责:
  - COM 线程初始化(pythoncom.CoInitialize/CoUninitialize,win32com 跨线程要求)
  - 批量生成(透传 cancel_check)
  - 信号回主线程:progress / finished_ok / failed

引擎策略(Issue #123 后):worker 不做任何"验证预检" Dispatch——注册表探测负责
展示识别,真实 Dispatch 的成功由转换器 `_init_office_app` 就地喂养引擎缓存;
纯图片/PDF 批处理天然不触碰 Office,含 Office 文档的批处理只按需 Dispatch 本次
文件类型所需应用,临时失败由转换器的 ProgID 回退兜底。

参考 gui/updater_widget.py 的 QThread + Signal 模式。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.common.office_session import ComSession


class PdfGenerateWorker(QThread, LoggableMixin):
    """PDF 生成后台线程。

    信号(均跨线程安全投递回主线程):
      progress(int, int, str)  — (current, total, message)
      finished_ok(list)        — results: list[dict],每项 {source, output, success, error}
      failed(str)              — 错误信息(中文友好)

    用法(主线程):
      worker = PdfGenerateWorker(svc, files, config)
      worker.progress.connect(on_progress)
      worker.finished_ok.connect(on_done)
      worker.failed.connect(on_error)
      worker.start()
    """

    progress = Signal(int, int, str)
    finished_ok = Signal(list)
    failed = Signal(str)
    cleanup_warning = Signal(str)

    def __init__(
        self,
        svc: Any,
        files: list[Path],
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = svc
        self._files = list(files)
        self._config = config
        self._cancel = False

    def cancel(self) -> None:
        """请求取消(下一个文件前生效)。"""
        self._cancel = True

    def _cancel_check(self) -> bool:
        return self._cancel

    def run(self) -> None:  # noqa: D401 (QThread 命名)
        """结果先投递；同线程严格清理之后才真正 finished。"""
        outcome_emitted = False
        try:
            with ComSession():
                try:
                    self.logger.info("PDF 生成 worker 开始 files=%d", len(self._files))
                    results = self._svc.batch_generate(
                        self._files,
                        self._config,
                        progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                        cancel_check=self._cancel_check,
                    )
                    outcome_emitted = True
                    self.finished_ok.emit(results)
                except Exception as error:
                    self.logger.exception("PDF 生成 worker 异常 files=%d", len(self._files))
                    outcome_emitted = True
                    self.failed.emit(str(error))
                finally:
                    self._svc.close(strict=True)
        except Exception as error:
            self.logger.exception("PDF worker COM/资源释放失败")
            if outcome_emitted:
                self.cleanup_warning.emit(f"已完成的输出保留；资源清理失败: {error}")
            else:
                self.failed.emit(str(error))
