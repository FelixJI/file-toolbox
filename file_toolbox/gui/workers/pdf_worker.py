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

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from file_toolbox.common.loggable import LoggableMixin


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
        svc,
        files: list[Path],
        config: dict,
        parent=None,
    ):
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
        # COM:win32com 要求使用它的线程先 CoInitialize,否则进程退出抛致命异常
        try:
            import pythoncom

            pythoncom.CoInitialize()
            com_inited = True
        except Exception:
            com_inited = False  # 非 Windows / 无 pywin32

        try:
            # 首次引擎兑现:注册表说有 → 真 Dispatch 验证一次
            # (force_refresh=True 才走真 Dispatch;失败则修正缓存,转换单元内会尝试另一引擎)
            try:
                from file_toolbox.core.batch_pdf.engine_manager import EngineManager

                EngineManager._detect_available_engines(force_refresh=True)
            except Exception as e:
                # 兑现失败不致命:auto 引擎下转换单元会逐个 ProgID 尝试
                self.logger.warning(f"引擎兑现检测失败(继续生成): {e}")

            results = self._svc.batch_generate(
                self._files,
                self._config,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                cancel_check=self._cancel_check,
            )
            self.finished_ok.emit(results)
        except Exception as e:
            self.logger.error(f"PDF 生成 worker 异常: {e}")
            self.failed.emit(str(e))
        finally:
            with __import__("contextlib").suppress(Exception):
                self._svc.close()
            if com_inited:
                with __import__("contextlib").suppress(Exception):
                    pythoncom.CoUninitialize()
