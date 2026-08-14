"""更新 Module 的稳定结果模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class UpdateCheckStatus(StrEnum):
    """检查更新的调用方可见状态。"""

    AVAILABLE = "available"
    LATEST = "latest"
    FAILED = "failed"


class UpdateApplyStatus(StrEnum):
    """下载并应用更新的调用方可见状态。"""

    APPLY_STARTED = "apply_started"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class UpdateCheckResult:
    """不暴露 Velopack ``UpdateInfo`` 的检查结果。"""

    status: UpdateCheckStatus
    version: str = ""
    release_notes: str = ""
    message: str = ""


@dataclass(frozen=True)
class UpdateApplyResult:
    """下载/apply 的最终可观察结果。"""

    status: UpdateApplyStatus
    message: str = ""
