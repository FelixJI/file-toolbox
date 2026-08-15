"""Velopack 1.2.0 的生产 ``UpdateCoordinator`` Adapter。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Protocol, cast

import velopack

from file_toolbox.updater.coordinator import UpdateCancelled
from file_toolbox.updater.models import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)
from file_toolbox.updater.transport import forward_proxy_environment

_logger = logging.getLogger(__name__)
_DEFAULT_FEED = "https://github.com/FelixJI/file-toolbox/releases/latest/download/"


class _Asset(Protocol):
    Version: str
    NotesMarkdown: str


class _UpdateInfo(Protocol):
    TargetFullRelease: _Asset


class _Manager(Protocol):
    def check_for_updates(self) -> object | None: ...

    def download_updates(
        self, update: object, progress_callback: Callable[[int], None] | None = None
    ) -> None: ...

    def wait_exit_then_apply_updates(
        self, update: object, *, silent: bool, restart: bool
    ) -> None: ...


ManagerFactory = Callable[[str], _Manager]


def _default_manager_factory(source: str) -> _Manager:
    options = velopack.UpdateOptions(False, -1, "win")
    return cast(_Manager, velopack.UpdateManager(velopack.HttpSource(source), options))


class VelopackUpdateCoordinator:
    """选择单一 feed candidate，并把 SDK 对象封装在模块内。"""

    def __init__(
        self,
        *,
        feed_candidates: Iterable[str] = (_DEFAULT_FEED,),
        manager_factory: ManagerFactory = _default_manager_factory,
        forward_proxy: str = "",
    ) -> None:
        self._feed_candidates = tuple(feed_candidates)
        self._manager_factory = manager_factory
        self._forward_proxy = forward_proxy
        self._selected_manager: _Manager | None = None
        self._selected_update: object | None = None

    def check(self) -> UpdateCheckResult:
        """按 candidate 顺序检查；成功后固定 manager/source 供后续下载。"""

        self._selected_manager = None
        self._selected_update = None
        for source in self._feed_candidates:
            try:
                with forward_proxy_environment(self._forward_proxy):
                    manager = self._manager_factory(source)
                    update = manager.check_for_updates()
            except Exception as error:  # SDK/网络边界统一映射为项目结果
                _logger.info("更新源不可用 source=%s: %s", source, error)
                continue
            if update is None:
                return UpdateCheckResult(UpdateCheckStatus.LATEST)
            info = cast(_UpdateInfo, update)
            self._selected_manager = manager
            self._selected_update = update
            return UpdateCheckResult(
                UpdateCheckStatus.AVAILABLE,
                version=info.TargetFullRelease.Version,
                release_notes=info.TargetFullRelease.NotesMarkdown,
            )
        return UpdateCheckResult(
            UpdateCheckStatus.FAILED,
            message="无法连接更新源，请检查网络或代理设置",
        )

    def download_and_apply(
        self, progress: Callable[[int], None] | None = None
    ) -> UpdateApplyResult:
        """下载并交由 Velopack 安排 apply/restart。"""

        if self._selected_manager is None or self._selected_update is None:
            return UpdateApplyResult(UpdateApplyStatus.FAILED, "请先检查更新")
        try:
            with forward_proxy_environment(self._forward_proxy):
                self._selected_manager.download_updates(self._selected_update, progress)
                self._selected_manager.wait_exit_then_apply_updates(
                    self._selected_update, silent=False, restart=True
                )
        except UpdateCancelled:
            return UpdateApplyResult(UpdateApplyStatus.CANCELLED)
        except Exception as error:
            _logger.warning("Velopack 下载或应用更新失败: %s", error, exc_info=True)
            return UpdateApplyResult(UpdateApplyStatus.FAILED, f"更新失败: {error}")
        return UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)


def create_update_coordinator() -> VelopackUpdateCoordinator:
    """创建 GUI 使用的生产 Coordinator。"""

    from file_toolbox.common import settings
    from file_toolbox.updater.proxy import get_enabled_proxies
    from file_toolbox.updater.transport import build_feed_candidates

    feeds = build_feed_candidates(get_enabled_proxies())
    forward_proxy = str(settings.get("forward_proxy", "") or "").strip()
    return VelopackUpdateCoordinator(
        feed_candidates=feeds,
        forward_proxy=forward_proxy,
    )
