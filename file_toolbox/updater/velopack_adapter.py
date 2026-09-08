"""Velopack 1.2.0 的生产 ``UpdateCoordinator`` Adapter。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from queue import Queue
from threading import Event, Thread
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

# 并发探测的单个结果:成功携带 (manager, update),失败携带异常。
_ProbeOutcome = tuple[str, tuple[_Manager, object]] | tuple[str, Exception]


def _default_manager_factory(source: str) -> _Manager:
    options = velopack.UpdateOptions(False, -1, "win")
    return cast(_Manager, velopack.UpdateManager(velopack.HttpSource(source), options))


class VelopackUpdateCoordinator:
    """选择单一 feed candidate，并把 SDK 对象封装在模块内。

    多候选且未配置 forward proxy 时,check() 并发探测全部候选,最先成功者
    (即最快可用者)被固定为该轮检查与下载的更新源;单候选或配置了 forward
    proxy 时按候选顺序串行尝试(进程级代理环境变量受互斥锁保护,并发只会
    退化成串行,不如直接走串行路径)。
    """

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
        """检查更新；成功后固定 manager/source 供后续下载。"""

        self._selected_manager = None
        self._selected_update = None
        if len(self._feed_candidates) > 1 and not self._forward_proxy.strip():
            return self._check_racing()
        return self._check_sequential()

    def _accept(self, manager: _Manager, update: object) -> UpdateCheckResult:
        """首个成功候选的结果映射(LATEST 不绑定 manager,下载需先 AVAILABLE)。"""
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

    @staticmethod
    def _all_failed() -> UpdateCheckResult:
        return UpdateCheckResult(
            UpdateCheckStatus.FAILED,
            message="无法连接更新源，请检查网络或代理设置",
        )

    def _probe(self, source: str, started: Event, outcomes: Queue[_ProbeOutcome]) -> None:
        """单候选探测(在独立 daemon 线程运行,任何异常都映射为该候选失败)。"""
        started.wait()  # 齐步起跑,避免线程创建顺序左右探测起点
        try:
            with forward_proxy_environment(self._forward_proxy):
                manager = self._manager_factory(source)
                update = manager.check_for_updates()
        except Exception as error:  # SDK/网络边界统一映射为项目结果
            outcomes.put((source, error))
            return
        outcomes.put((source, (manager, update)))

    def _check_racing(self) -> UpdateCheckResult:
        """并发探测全部候选,先成功者胜出。

        线程为 daemon:落败线程任其自行超时退出,不阻塞 check() 返回与进程退出。
        即使绑定层在阻塞网络调用期间不释放 GIL(未证实),也只是退化为按启动
        顺序的串行尝试,语义仍是"先成功者胜",不会劣于旧实现。
        """
        started = Event()
        outcomes: Queue[_ProbeOutcome] = Queue()
        threads = [
            Thread(target=self._probe, args=(source, started, outcomes), daemon=True)
            for source in self._feed_candidates
        ]
        for thread in threads:
            thread.start()
        started.set()
        for _ in threads:
            source, payload = outcomes.get()
            if isinstance(payload, Exception):
                _logger.info("更新源不可用 source=%s: %s", source, payload)
                continue
            manager, update = payload
            return self._accept(manager, update)
        return self._all_failed()

    def _check_sequential(self) -> UpdateCheckResult:
        for source in self._feed_candidates:
            try:
                with forward_proxy_environment(self._forward_proxy):
                    manager = self._manager_factory(source)
                    update = manager.check_for_updates()
            except Exception as error:  # SDK/网络边界统一映射为项目结果
                _logger.info("更新源不可用 source=%s: %s", source, error)
                continue
            return self._accept(manager, update)
        return self._all_failed()

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
