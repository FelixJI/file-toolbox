"""面向 GUI 的唯一更新 Interface。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from file_toolbox.updater.models import UpdateApplyResult, UpdateCheckResult


class UpdateCancelled(Exception):
    """progress callback 用于中止 SDK 下载且不触发 apply 的内部控制信号。"""


class UpdateCoordinator(Protocol):
    """隐藏 feed、SDK 类型、下载与 apply 细节的深 Module Interface。"""

    def check(self) -> UpdateCheckResult: ...

    def download_and_apply(
        self, progress: Callable[[int], None] | None = None
    ) -> UpdateApplyResult: ...
