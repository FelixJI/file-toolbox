"""考勤预览/生成后台线程。"""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.core.attendance import (
    AttendancePreview,
    AttendanceRequest,
    AttendanceResult,
    AttendanceService,
)


class AttendanceWorker(QThread, LoggableMixin):
    """在自身 STA 线程内执行 Excel COM，避免阻塞 GUI。"""

    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: AttendanceService,
        request: AttendanceRequest,
        mode: Literal["preview", "generate"],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._request = request
        self._mode = mode
        self._cancel_requested = False

    def cancel(self) -> None:
        """请求在下一个安全检查点取消。"""
        self._cancel_requested = True

    def _cancel_check(self) -> bool:
        return self._cancel_requested

    def run(self) -> None:
        try:
            result: AttendancePreview | AttendanceResult
            if self._mode == "preview":
                result = self._service.preview(self._request, self._cancel_check)
            else:
                result = self._service.generate(self._request, self._cancel_check)
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001 - 跨线程统一转换为失败信号
            self.logger.error(f"考勤 {self._mode} worker 异常: {exc}")
            self.failed.emit(str(exc))
