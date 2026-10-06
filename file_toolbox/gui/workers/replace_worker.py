"""内容替换后台 worker(QThread):预览与执行两个入口。

把 ContentReplaceService.preview_replace / execute_replace 搬到后台线程,
避免 Word/Excel COM 的 Dispatch/Open(单文件可达数十秒)冻结 GUI 主线程
(freeze_watchdog 曾对此多次转储 30-45s 冻结)。与 pdf_worker 同构:
  - COM 线程初始化(pythoncom.CoInitialize/CoUninitialize,win32com 跨线程要求)
  - 协作式取消(cancel → service 的 cancel_check,文件间生效)
  - 信号回主线程:preview_ok / execute_ok / progress / failed

Office 引用由 handler 在创建线程释放；service.close 仅清理本服务临时文件。
取消在 COM 调用返回后的检查点生效，不能硬中断正在进行的调用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.common.office_session import ComSession


class ReplacePreviewWorker(QThread, LoggableMixin):
    """预览(统计匹配,不改文件)后台线程。

    信号(跨线程安全投递回主线程):
      preview_ok(object) — dict[Path, dict[str, Any]],与 service.preview_replace 同形
      failed(str)        — 错误信息(中文友好)
    """

    preview_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        svc: Any,
        files: list[Path],
        operations: list[dict[str, Any]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = svc
        self._files = list(files)
        self._operations = list(operations)
        self._cancel = False

    def cancel(self) -> None:
        """请求取消；正在进行的 COM 调用返回后，在下一个检查点停止。"""
        self._cancel = True

    def run(self) -> None:  # noqa: D401 (QThread 命名)
        """worker 入口(在后台线程执行)。"""
        # COM:win32com 要求使用它的线程先 CoInitialize(非 Windows/无 pywin32 时 no-op)
        try:
            with ComSession():
                self.logger.info("替换预览 worker 开始 files=%d", len(self._files))
                result = self._svc.preview_replace(
                    self._files, self._operations, cancel_check=lambda: self._cancel
                )
                self.logger.info("替换预览 worker 完成 files=%d", len(self._files))
                self.preview_ok.emit(result)
        except Exception as e:
            self.logger.exception("替换预览 worker 异常 files=%d", len(self._files))
            self.failed.emit(str(e))


class ReplaceExecuteWorker(QThread, LoggableMixin):
    """执行替换(含备份/转换/写回)后台线程。

    信号(跨线程安全投递回主线程):
      progress(int, int)   — (processed, total_files)
      execute_ok(int, int, list) — (成功数, 替换处数, 错误消息列表)
      failed(str)          — 错误信息(中文友好)
    """

    progress = Signal(int, int)
    execute_ok = Signal(int, int, list)
    failed = Signal(str)

    def __init__(
        self,
        svc: Any,
        files: list[Path],
        operations: list[dict[str, Any]],
        keep_new_format: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = svc
        self._files = list(files)
        self._operations = list(operations)
        self._keep_new_format = keep_new_format
        self._cancel = False

    def cancel(self) -> None:
        """请求取消；正在进行的 COM 调用返回后，在下一个检查点停止。"""
        self._cancel = True

    def run(self) -> None:  # noqa: D401 (QThread 命名)
        """worker 入口(在后台线程执行)。"""
        try:
            with ComSession():
                self.logger.info("替换执行 worker 开始 files=%d", len(self._files))
                success, total, errors = self._svc.execute_replace(
                    self._files,
                    self._operations,
                    keep_new_format=self._keep_new_format,
                    progress_callback=lambda cur, tot: self.progress.emit(cur, tot),
                    cancel_check=lambda: self._cancel,
                )
                self.logger.info(
                    "替换执行 worker 完成 files=%d success=%d", len(self._files), success
                )
                self.execute_ok.emit(success, total, list(errors))
        except Exception as e:
            self.logger.exception("替换执行 worker 异常 files=%d", len(self._files))
            self.failed.emit(str(e))
