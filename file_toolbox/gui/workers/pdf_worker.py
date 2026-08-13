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
from file_toolbox.core.batch_pdf.constants import OFFICE_EXTENSIONS


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

    def _needs_office(self) -> bool:
        """批处理是否含需 Office 引擎(Word/Excel/PowerPoint)的文档。

        纯图片/PDF 批处理返回 False —— 这类转换不依赖 Office COM,worker 据此
        完全跳过引擎兑现,避免无谓启动 Word/WPS 进程。
        """
        return any(path.suffix.lower() in OFFICE_EXTENSIONS for path in self._files)

    def run(self) -> None:  # noqa: D401 (QThread 命名)
        """worker 入口(在后台线程执行)。"""
        # COM:win32com 要求使用它的线程先 CoInitialize,否则进程退出抛致命异常。
        # ComSession 负责本线程 CoInitialize/CoUninitialize 配对(非 Windows / 无 pywin32
        # 时为 no-op)。__exit__ 在 with 体(含下方 finally)之后执行,故 svc.close() 仍在
        # CoUninitialize 之前——与原手写顺序一致。
        with ComSession():
            try:
                self.logger.info("PDF 生成 worker 开始 files=%d", len(self._files))
                # 一次性引擎兑现:仅当批处理含 Office 文档时才真 Dispatch 验证。
                # ensure_verified 进程内只兑现一次(_verified 标志),只检测缓存判定可用的
                # 引擎;纯图片/PDF 批处理(_needs_office=False)完全跳过,零 Office 开销。
                if self._needs_office():
                    try:
                        from file_toolbox.core.batch_pdf.engine_manager import EngineManager

                        EngineManager().ensure_verified()
                    except Exception:
                        # 兑现失败不致命:转换器 _prog_ids_to_try 会逐个 ProgID 尝试回退
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
