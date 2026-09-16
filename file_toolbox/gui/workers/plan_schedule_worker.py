"""计划排布后台 worker(QThread)。

把 PlanScheduleService.generate 搬到后台线程,避免写出工作簿期间冻结 GUI。
与 ExcelMergeWorker 同范式:纯 openpyxl,不需要 COM 初始化。

信号(均跨线程安全投递回主线程):
  progress(int, int, str)  — (current, total, message)
  finished_ok(object)      — ScheduleResult(含 success 语义)
  failed(str)              — 错误信息(中文友好)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.core.plan_schedule import ScheduleOptions


class PlanScheduleWorker(QThread, LoggableMixin):
    """计划排布后台线程(不提供取消;关闭时由 Tab 等待 finished 收尾)。"""

    progress = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        svc: Any,
        input_path: Path,
        output: Path,
        options: ScheduleOptions,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = svc
        self._input_path = input_path
        self._output = output
        self._options = options

    def run(self) -> None:  # noqa: D401 (QThread 命名)
        """worker 入口(在后台线程执行)。"""
        try:
            self.logger.info("计划排布 worker 开始: %s", self._input_path)
            result = self._svc.generate(
                self._input_path,
                self._output,
                self._options,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
            )
            self.logger.info(
                "计划排布 worker 完成: success=%s items=%d", result.success, len(result.items)
            )
            self.finished_ok.emit(result)
        except Exception as e:  # noqa: BLE001 - 任意异常转 failed 信号
            self.logger.exception("计划排布 worker 异常: %s", self._input_path)
            self.failed.emit(str(e))
