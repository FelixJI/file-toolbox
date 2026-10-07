"""Velopack 的生产 ``UpdateCoordinator`` Adapter。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from queue import Empty, Queue
from threading import Event, Thread
from typing import Protocol, cast

import velopack

from file_toolbox.updater.coordinator import UpdateCancelled, UpdateRequest
from file_toolbox.updater.models import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)
from file_toolbox.updater.transport import forward_proxy_environment

_logger = logging.getLogger(__name__)
_DEFAULT_FEED = "https://github.com/FelixJI/file-toolbox/releases/latest/download/"

# 竞速检查中首个成功结果为 LATEST 时,再为其余候选保留的有限确认窗口:
# 防止陈旧镜像抢先返回"已是最新"掩盖直连/其他镜像上的真实新版;窗口有界,
# 不退回无界等待全部慢镜像(见 #128 AC3 契约)。
_LATEST_GRACE_SECONDS = 2.0


class _Asset(Protocol):
    Version: str
    NotesMarkdown: str


class _UpdateInfo(Protocol):
    TargetFullRelease: _Asset


class _Manager(Protocol):
    def check_for_updates(self) -> object | None: ...

    def get_current_version(self) -> str: ...

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


def _is_layout_error(error: BaseException) -> bool:
    """是否为"本机没有有效 Velopack 安装布局"错误(与网络失败区分)。

    SDK 的布局错误文本 ``This application is not properly installed: Could not
    auto-locate app manifest``;按特征片段匹配,避免绑定完整措辞。
    """

    text = str(error)
    return "not properly installed" in text or "auto-locate app manifest" in text


def _safe_current_version(manager: _Manager) -> str:
    """读 SDK 本机当前版本;异常时返回空串,不让诊断信息破坏检查结果。"""

    try:
        return str(manager.get_current_version())
    except Exception:  # noqa: BLE001 — locator 诊断读取失败不影响检查主流程
        _logger.info("读取 SDK 当前版本失败", exc_info=True)
        return ""


class VelopackUpdateCoordinator:
    """选择单一 feed candidate，并把 SDK 对象封装在模块内。

    多候选且未配置 forward proxy 时,check() 并发探测全部候选:先到的
    AVAILABLE 立即胜出并固定为该轮检查与下载的更新源;首个 LATEST 只在
    有界宽限窗口内让位给更晚的 AVAILABLE(防陈旧镜像)。单候选或配置了
    forward proxy 时按候选顺序串行尝试(进程级代理环境变量受互斥锁保护,
    并发只会退化成串行,不如直接走串行路径)。
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

    def _accept(self, manager: _Manager, update: object, source: str) -> UpdateCheckResult:
        """首个成功候选的结果映射(LATEST 不绑定 manager,下载需先 AVAILABLE)。"""

        current_version = _safe_current_version(manager)
        if update is None:
            return UpdateCheckResult(
                UpdateCheckStatus.LATEST, current_version=current_version, source=source
            )
        info = cast("_UpdateInfo", update)
        self._selected_manager = manager
        self._selected_update = update
        _logger.info(
            "更新检查选定候选 source=%s current=%s target=%s",
            source,
            current_version,
            info.TargetFullRelease.Version,
        )
        return UpdateCheckResult(
            UpdateCheckStatus.AVAILABLE,
            version=info.TargetFullRelease.Version,
            release_notes=info.TargetFullRelease.NotesMarkdown,
            current_version=current_version,
            source=source,
        )

    @staticmethod
    def _all_failed() -> UpdateCheckResult:
        return UpdateCheckResult(
            UpdateCheckStatus.FAILED,
            message="无法连接更新源，请检查网络或代理设置",
        )

    @staticmethod
    def _unsupported() -> UpdateCheckResult:
        return UpdateCheckResult(
            UpdateCheckStatus.UNSUPPORTED,
            message="当前运行形态未检测到有效的 Velopack 安装布局，不支持应用内更新；"
            "源码/开发运行请以便携发行包运行以获得自动更新",
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
        """并发探测全部候选:先到的 AVAILABLE 立即胜出。

        首个成功结果为 LATEST 时,再等待其余候选至多 ``_LATEST_GRACE_SECONDS``
        (或全部返回):期间出现任一 AVAILABLE 则改判该结果,避免陈旧镜像的
        "已是最新"掩盖真实新版;超时仍无更新则维持 LATEST,不无界等待。
        线程为 daemon:落败线程任其自行超时退出,不阻塞 check() 返回与进程退出。
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
        latest: tuple[_Manager, object, str] | None = None
        remaining = len(threads)
        grace_deadline: float | None = None
        while remaining > 0:
            timeout = (
                None if grace_deadline is None else max(0.0, grace_deadline - time.monotonic())
            )
            try:
                source, payload = outcomes.get(timeout=timeout)
            except Empty:
                break  # LATEST 宽限窗口耗尽,不再等待其余慢镜像
            remaining -= 1
            if isinstance(payload, Exception):
                if _is_layout_error(payload):
                    # 安装布局缺失对所有候选同样失败,重试网络无意义。
                    return self._unsupported()
                _logger.info("更新源不可用 source=%s: %s", source, payload)
                continue
            manager, update = payload
            if update is not None:
                return self._accept(manager, update, source)
            if latest is None:
                latest = (manager, update, source)
                grace_deadline = time.monotonic() + _LATEST_GRACE_SECONDS
        if latest is not None:
            manager, update, source = latest
            return self._accept(manager, update, source)
        return self._all_failed()

    def _check_sequential(self) -> UpdateCheckResult:
        for source in self._feed_candidates:
            try:
                with forward_proxy_environment(self._forward_proxy):
                    manager = self._manager_factory(source)
                    update = manager.check_for_updates()
            except Exception as error:  # SDK/网络边界统一映射为项目结果
                if _is_layout_error(error):
                    return self._unsupported()
                _logger.info("更新源不可用 source=%s: %s", source, error)
                continue
            return self._accept(manager, update, source)
        return self._all_failed()

    def download_and_apply(
        self,
        progress: Callable[[int], None] | None = None,
        *,
        request: UpdateRequest | None = None,
        before_apply: Callable[[], None] | None = None,
        expected_version: str | None = None,
    ) -> UpdateApplyResult:
        """下载并交由 Velopack 安排 apply/restart。

        ``expected_version``: 调用方确认下载时展示给用户的版本;与本轮实际
        绑定的候选版本不一致时直接失败,防止过期 UI 状态触发错误目标的更新。
        """

        if self._selected_manager is None or self._selected_update is None:
            return UpdateApplyResult(UpdateApplyStatus.FAILED, "请先检查更新")
        bound_version = cast("_UpdateInfo", self._selected_update).TargetFullRelease.Version
        if expected_version is not None and bound_version != expected_version:
            return UpdateApplyResult(
                UpdateApplyStatus.FAILED,
                f"更新候选已变化（确认 v{expected_version}，当前绑定 v{bound_version}），请重新检查更新",
            )
        request = request or UpdateRequest()
        manager, update = self._selected_manager, self._selected_update

        def report_progress(value: int) -> None:
            request.check_cancelled()
            if progress is not None:
                progress(value)

        try:
            request.check_cancelled()
            with forward_proxy_environment(self._forward_proxy):
                manager.download_updates(update, report_progress)
                request.begin_apply()
                # 进入提交阶段后消费候选,禁止无新检查的重复 apply。
                self._selected_manager = None
                self._selected_update = None
                if before_apply is not None:
                    before_apply()
                manager.wait_exit_then_apply_updates(update, silent=False, restart=True)
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
