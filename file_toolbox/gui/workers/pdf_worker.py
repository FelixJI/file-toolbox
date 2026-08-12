"""PDF 生成后台 worker(QThread)。

把 PDFGeneratorService.batch_generate 搬到后台线程,避免转换期间冻结 GUI。
worker 负责:
  - COM 线程初始化(pythoncom.CoInitialize/CoUninitialize,win32com 跨线程要求)
  - 首次引擎兑现检测(注册表判定 → 真 Dispatch 验证,见 engine_manager)
  - 批量生成(透传 cancel_check)
  - 信号回主线程:progress / finished_ok / failed

参考 gui/updater_widget.py 的 QThread + Signal 模式。
"""

from __future__ import annotations

import contextlib
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
        """worker 入口(在后台线程执行)。"""
        # COM:win32com 要求使用它的线程先 CoInitialize,否则进程退出抛致命异常。
        # ComSession 负责本线程 CoInitialize/CoUninitialize 配对(非 Windows / 无 pywin32
        # 时为 no-op)。__exit__ 在 with 体(含下方 finally)之后执行,故 svc.close() 仍在
        # CoUninitialize 之前——与原手写顺序一致。
        with ComSession():
            try:
                self.logger.info("PDF 生成 worker 开始 files=%d", len(self._files))
                # 首次引擎兑现:注册表说有 → 真 Dispatch 验证一次
                # (force_refresh=True 才走真 Dispatch;失败则修正缓存,转换单元内会尝试另一引擎)
                try:
                    from file_toolbox.core.batch_pdf.engine_manager import EngineManager

                    EngineManager()._detect_available_engines(force_refresh=True)
                except Exception:
                    # 兑现失败不致命:auto 引擎下转换单元会逐个 ProgID 尝试
                    self.logger.warning("引擎兑现检测失败（继续生成）", exc_info=True)

                results = self._svc.batch_generate(
                    self._files,
                    self._config,
                    progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                    cancel_check=self._cancel_check,
                )
                self.logger.info("PDF 生成 worker 完成 files=%d", len(self._files))
                self.finished_ok.emit(results)
            except Exception as e:
                self.logger.exception("PDF 生成 worker 异常 files=%d", len(self._files))
                self.failed.emit(str(e))
            finally:
                with contextlib.suppress(Exception):
                    self._svc.close()
