"""面向 GUI 的唯一更新 Interface。"""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Protocol

from file_toolbox.updater.models import UpdateApplyResult, UpdateCheckResult


class UpdateCancelled(Exception):
    """progress callback 用于中止 SDK 下载且不触发 apply 的内部控制信号。"""


class UpdateRequest:
    """一轮更新的取消与 apply 提交门;请求创建后不清空取消状态。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._claimed = False
        self._cancelled = False
        self._applying = False
        self._finished = False

    def claim(self) -> bool:
        with self._lock:
            if self._claimed or self._finished:
                return False
            self._claimed = True
            return True

    def cancel(self) -> bool:
        """True 表示已接受且保证不进入 apply;提交后明确拒绝取消。"""
        with self._lock:
            if self._applying or self._finished:
                return False
            self._cancelled = True
            return True

    def check_cancelled(self) -> None:
        with self._lock:
            if self._cancelled:
                raise UpdateCancelled

    def begin_apply(self) -> None:
        """与 cancel 共享唯一锁:取消胜出则抛出,提交胜出则之后不可取消。"""
        with self._lock:
            if self._cancelled:
                raise UpdateCancelled
            if self._applying or self._finished:
                raise RuntimeError("该更新请求已进入 apply 或已经结束")
            self._applying = True

    @property
    def applying(self) -> bool:
        with self._lock:
            return self._applying

    def finish(self) -> bool:
        """固定终态并返回先于结束接受的取消;结束后不再接受取消。"""
        with self._lock:
            self._finished = True
            return self._cancelled


class UpdateCoordinator(Protocol):
    """隐藏 feed、SDK 类型、下载与 apply 细节的深 Module Interface。"""

    def check(self) -> UpdateCheckResult: ...

    def download_and_apply(
        self,
        progress: Callable[[int], None] | None = None,
        *,
        request: UpdateRequest | None = None,
        before_apply: Callable[[], None] | None = None,
    ) -> UpdateApplyResult: ...
