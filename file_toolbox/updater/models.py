"""更新 Module 的稳定结果模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class UpdateCheckStatus(StrEnum):
    """检查更新的调用方可见状态。"""

    AVAILABLE = "available"
    LATEST = "latest"
    FAILED = "failed"
    # 当前运行形态没有有效 Velopack 安装布局(源码/开发/缺失清单),
    # 与网络失败区分:重试网络无意义,应说明运行形态而非伪装成网络错误。
    UNSUPPORTED = "unsupported"


class UpdateApplyStatus(StrEnum):
    """下载并应用更新的调用方可见状态。"""

    APPLY_STARTED = "apply_started"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class UpdateCheckResult:
    """不暴露 Velopack ``UpdateInfo`` 的检查结果。

    ``current_version``: SDK locator 读到的本机当前安装版本(离线,无网络),
    供 UI 展示"当前 vX → 目标 vY"与跨启动对账;布局不可用时为空串。
    ``source``: 本轮获胜的 feed 候选,写入诊断日志/结果便于定位镜像问题。
    """

    status: UpdateCheckStatus
    version: str = ""
    release_notes: str = ""
    message: str = ""
    current_version: str = ""
    source: str = ""


@dataclass(frozen=True)
class UpdateApplyResult:
    """下载/apply 的最终可观察结果。"""

    status: UpdateApplyStatus
    message: str = ""
