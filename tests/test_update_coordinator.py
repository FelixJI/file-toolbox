"""UpdateCoordinator 公共行为契约。"""

import threading
import time
from collections.abc import Callable

from file_toolbox.updater import (
    UpdateApplyStatus,
    UpdateCheckStatus,
    VelopackUpdateCoordinator,
)
from file_toolbox.updater.coordinator import UpdateCancelled


class FakeAsset:
    Version = "0.3.0"
    NotesMarkdown = "修复更新"


class FakeUpdateInfo:
    TargetFullRelease = FakeAsset()


class VersionedAsset:
    def __init__(self, version: str) -> None:
        self.Version = version
        self.NotesMarkdown = f"{version} 更新内容"


class VersionedUpdateInfo:
    def __init__(self, version: str) -> None:
        self.TargetFullRelease = VersionedAsset(version)


class FakeManager:
    def __init__(
        self,
        *,
        update: object | None = None,
        error: Exception | None = None,
        portable: bool = False,
        current_version: str = "",
    ) -> None:
        self.update = update
        self.error = error
        self.portable = portable
        self.current_version = current_version
        self.downloaded: object | None = None
        self.applied: object | None = None

    def get_is_portable(self) -> bool:
        return self.portable

    def get_current_version(self) -> str:
        return self.current_version

    def check_for_updates(self) -> object | None:
        if self.error is not None:
            raise self.error
        return self.update

    def download_updates(
        self, update: object, progress_callback: Callable[[int], None] | None = None
    ) -> None:
        self.downloaded = update
        if progress_callback is not None:
            progress_callback(37)
            progress_callback(100)

    def wait_exit_then_apply_updates(self, update: object, *, silent: bool, restart: bool) -> None:
        assert silent is False
        assert restart is True
        self.applied = update


def test_available_update_is_project_model_and_same_candidate_is_applied() -> None:
    failed = FakeManager(error=RuntimeError("prefix unavailable"))
    selected = FakeManager(update=FakeUpdateInfo())
    managers = iter([failed, selected])
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://prefix.invalid/feed/", "https://direct.invalid/feed/"),
        manager_factory=lambda _source: next(managers),
    )

    check = coordinator.check()

    assert check.status is UpdateCheckStatus.AVAILABLE
    assert check.version == "0.3.0"
    assert check.release_notes == "修复更新"

    progress: list[int] = []
    applied = coordinator.download_and_apply(progress.append)
    assert applied.status is UpdateApplyStatus.APPLY_STARTED
    assert progress == [37, 100]
    assert selected.downloaded is selected.update
    assert selected.applied is selected.update


def test_no_update_is_latest() -> None:
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://direct.invalid/feed/",),
        manager_factory=lambda _source: FakeManager(),
    )

    assert coordinator.check().status is UpdateCheckStatus.LATEST


def test_all_feed_candidates_failing_is_observable_without_sdk_exception_leak() -> None:
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://one.invalid/", "https://two.invalid/"),
        manager_factory=lambda source: FakeManager(error=RuntimeError(f"bad {source}")),
    )

    result = coordinator.check()

    assert result.status is UpdateCheckStatus.FAILED
    assert result.message == "无法连接更新源，请检查网络或代理设置"


# ---------------------------------------------------------------------------
# 并发竞速:多候选且未配置 forward proxy 时,先成功(最快可用)者胜出
# ---------------------------------------------------------------------------


class GatedManager(FakeManager):
    """check_for_updates 阻塞在门上(模拟慢镜像),放行后才返回。"""

    def __init__(self, update: object | None, gate: threading.Event) -> None:
        super().__init__(update=update)
        self._gate = gate

    def check_for_updates(self) -> object | None:
        assert self._gate.wait(10), "探测门 10s 内未放行"
        if self.error is not None:
            raise self.error
        return self.update


def test_racing_picks_fastest_available_candidate() -> None:
    """慢镜像阻塞时,快镜像立即胜出;串行实现会被首个慢候选拖满 10s。"""
    gate = threading.Event()
    slow = GatedManager(VersionedUpdateInfo("0.1.0"), gate)
    fast = FakeManager(update=VersionedUpdateInfo("0.2.0"))
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://slow.invalid/feed/", "https://fast.invalid/feed/"),
        manager_factory=lambda source: slow if "slow" in source else fast,
    )

    try:
        t0 = time.monotonic()
        result = coordinator.check()
        elapsed = time.monotonic() - t0

        assert result.status is UpdateCheckStatus.AVAILABLE
        assert result.version == "0.2.0"
        assert elapsed < 5
    finally:
        gate.set()  # 放行落败线程,不让 daemon 线程滞留整个测试会话


def test_racing_fastest_latest_response_wins() -> None:
    """快镜像返回 None(已是最新)最终胜出,不被慢镜像无限阻塞。

    #128 AC3 契约:首个 LATEST 只在有界宽限窗口内等待其余候选(防陈旧镜像
    掩盖真实新版);门控镜像在窗口内不放行时,LATEST 结果照常返回。
    """
    gate = threading.Event()
    slow = GatedManager(VersionedUpdateInfo("0.1.0"), gate)
    fast = FakeManager()  # update=None → LATEST
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://slow.invalid/feed/", "https://fast.invalid/feed/"),
        manager_factory=lambda source: slow if "slow" in source else fast,
    )

    try:
        t0 = time.monotonic()
        result = coordinator.check()
        elapsed = time.monotonic() - t0
        assert result.status is UpdateCheckStatus.LATEST
        # 宽限窗口有界:远超窗口仍立即返回,不等待全部慢镜像
        assert elapsed < 3.5
    finally:
        gate.set()


def test_racing_latest_grace_prefers_later_available() -> None:
    """陈旧镜像抢先报 LATEST 时,宽限窗口内到达的真实新版必须胜出(#128 AC3)。

    旧契约"先成功者胜"会把陈旧镜像的 LATEST 当成全局最新,用户停留在旧版。
    """
    gate = threading.Event()
    stale = FakeManager()  # 立即返回 LATEST(陈旧镜像)

    class DelayedAvailableManager(FakeManager):
        def check_for_updates(self) -> object | None:
            gate.wait(5)
            return self.update

    fresh = DelayedAvailableManager(update=VersionedUpdateInfo("0.2.0"))
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://stale.invalid/feed/", "https://fresh.invalid/feed/"),
        manager_factory=lambda source: stale if "stale" in source else fresh,
    )

    try:
        # 在宽限窗口内放行真实新版
        threading.Timer(0.3, gate.set).start()
        result = coordinator.check()
        assert result.status is UpdateCheckStatus.AVAILABLE
        assert result.version == "0.2.0"
    finally:
        gate.set()


def test_racing_maps_factory_failure_to_candidate_loss() -> None:
    """某候选 manager 构造失败只淘汰该候选,不影响其余候选胜出。"""

    def factory(source: str) -> FakeManager:
        if "broken" in source:
            raise RuntimeError("no local manifest")
        return FakeManager(update=VersionedUpdateInfo("0.3.0"))

    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://broken.invalid/feed/", "https://ok.invalid/feed/"),
        manager_factory=factory,
    )

    result = coordinator.check()

    assert result.status is UpdateCheckStatus.AVAILABLE
    assert result.version == "0.3.0"


def test_forward_proxy_keeps_sequential_candidate_order() -> None:
    """配置 forward proxy 时代理环境变量互斥,按候选顺序串行且短路(非并发)。"""
    calls: list[str] = []

    class SlowFirstManager(FakeManager):
        def check_for_updates(self) -> object | None:
            time.sleep(0.2)
            return self.update

    def factory(source: str) -> FakeManager:
        calls.append(source)
        if "first" in source:
            return SlowFirstManager(update=VersionedUpdateInfo("1.0.0"))
        return FakeManager(update=VersionedUpdateInfo("2.0.0"))

    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://first.invalid/feed/", "https://second.invalid/feed/"),
        manager_factory=factory,
        forward_proxy="http://127.0.0.1:7890",
    )

    result = coordinator.check()

    # 首个(慢)候选胜出;若误入并发路径,立即返回的 2.0.0 会赢
    assert result.status is UpdateCheckStatus.AVAILABLE
    assert result.version == "1.0.0"
    # 串行短路:首个候选成功后不再构造后续候选的 manager
    assert calls == ["https://first.invalid/feed/"]


def test_apply_requires_prior_available_check() -> None:
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://direct.invalid/",),
        manager_factory=lambda _source: FakeManager(),
    )

    result = coordinator.download_and_apply()

    assert result.status is UpdateApplyStatus.FAILED
    assert result.message == "请先检查更新"


def test_real_velopack_binding_construction_failure_is_observable() -> None:
    """开发态无 manifest 时按 UNSUPPORTED 报告,不再误报为网络失败(#128 AC3)。

    旧契约把"本机没有有效 Velopack 安装布局"折叠进 FAILED 的"无法连接更新
    源"文案,开发态手动检查必然误导用户排查网络。
    """

    coordinator = VelopackUpdateCoordinator(feed_candidates=("http://127.0.0.1:1/",))

    result = coordinator.check()
    assert result.status is UpdateCheckStatus.UNSUPPORTED
    assert "Velopack 安装布局" in result.message


def test_layout_error_classified_unsupported_in_racing_too() -> None:
    """并发竞速路径同样识别布局错误:任何候选都不必重试网络。"""

    def factory(_source: str) -> FakeManager:
        raise RuntimeError(
            "This application is not properly installed: Could not auto-locate app manifest"
        )

    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://one.invalid/feed/", "https://two.invalid/feed/"),
        manager_factory=factory,
    )

    assert coordinator.check().status is UpdateCheckStatus.UNSUPPORTED


def test_check_reports_current_version_and_selected_source() -> None:
    """检查结果携带 SDK 本机版本与获胜候选源(诊断与 UI 展示,#128 AC4)。"""

    manager = FakeManager(update=VersionedUpdateInfo("0.4.0"), current_version="0.3.5")
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://mirror.invalid/https://github.com/feed/", "https://direct/feed/"),
        manager_factory=lambda source: manager if "mirror" in source else FakeManager(),
    )

    check = coordinator.check()

    assert check.status is UpdateCheckStatus.AVAILABLE
    assert check.current_version == "0.3.5"
    assert check.source == "https://mirror.invalid/https://github.com/feed/"


def test_download_rejects_stale_expected_version() -> None:
    """过期 UI 状态(确认版本 ≠ 绑定候选)不得触发下载错误目标(#128 AC2)。"""

    coordinator = _selected_coordinator(FakeManager(update=VersionedUpdateInfo("0.4.0")))

    result = coordinator.download_and_apply(expected_version="0.3.9")

    assert result.status is UpdateApplyStatus.FAILED
    assert "重新检查更新" in result.message
    # 未进入下载:候选未被消费,仍可重新确认后下载
    assert coordinator.download_and_apply(expected_version="0.4.0").status is (
        UpdateApplyStatus.APPLY_STARTED
    )


def test_download_accepts_matching_expected_version() -> None:
    manager = FakeManager(update=VersionedUpdateInfo("0.4.0"))
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://direct.invalid/feed/",),
        manager_factory=lambda _source: manager,
    )
    assert coordinator.check().status is UpdateCheckStatus.AVAILABLE

    result = coordinator.download_and_apply(expected_version="0.4.0")

    assert result.status is UpdateApplyStatus.APPLY_STARTED
    assert manager.downloaded is manager.update


def test_portable_manager_applies_updates_without_installer() -> None:
    """便携是唯一发行形态，自更新不得再被阻断。"""

    manager = FakeManager(update=FakeUpdateInfo(), portable=True)

    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://direct.invalid/feed/",),
        manager_factory=lambda _source: manager,
    )
    result = coordinator.check()
    applied = coordinator.download_and_apply()

    assert result.status is UpdateCheckStatus.AVAILABLE
    assert applied.status is UpdateApplyStatus.APPLY_STARTED
    assert manager.applied is manager.update


class CancellingManager(FakeManager):
    """progress callback 阶段取消或失败:下载中止且不得进入 apply。"""

    def __init__(self, update: object, error: Exception | None = None) -> None:
        super().__init__(update=update)
        self.download_error = error
        self.applied = None

    def download_updates(
        self, update: object, progress_callback: Callable[[int], None] | None = None
    ) -> None:
        if self.download_error is not None:
            raise self.download_error
        if progress_callback is not None:
            progress_callback(10)
            raise UpdateCancelled

    def wait_exit_then_apply_updates(self, update: object, *, silent: bool, restart: bool) -> None:
        raise AssertionError("取消/失败路径不得安排 apply")


def _selected_coordinator(manager: FakeManager) -> VelopackUpdateCoordinator:
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://direct.invalid/feed/",),
        manager_factory=lambda _source: manager,
    )
    assert coordinator.check().status is UpdateCheckStatus.AVAILABLE
    return coordinator


def test_download_cancel_maps_to_cancelled_without_apply() -> None:
    coordinator = _selected_coordinator(CancellingManager(FakeUpdateInfo()))

    result = coordinator.download_and_apply(lambda _value: None)

    assert result.status is UpdateApplyStatus.CANCELLED


def test_download_failure_maps_to_failed_with_message() -> None:
    coordinator = _selected_coordinator(
        CancellingManager(FakeUpdateInfo(), error=RuntimeError("磁盘已满"))
    )

    result = coordinator.download_and_apply(lambda _value: None)

    assert result.status is UpdateApplyStatus.FAILED
    assert "磁盘已满" in (result.message or "")


def test_create_update_coordinator_wires_proxies_and_forward_proxy(monkeypatch) -> None:
    from file_toolbox.updater import velopack_adapter

    captured_feeds: list[tuple[str, ...]] = []

    def fake_build_feed_candidates(
        prefixes, *, direct_feed="https://github.com/FelixJI/file-toolbox/releases/latest/download/"
    ):
        captured_feeds.append(tuple(prefixes))
        return tuple(f"{prefix}/{direct_feed}" for prefix in prefixes) + (direct_feed,)

    monkeypatch.setattr(
        "file_toolbox.updater.proxy.get_enabled_proxies", lambda: ("https://mirror.example", "")
    )
    monkeypatch.setattr(
        "file_toolbox.updater.transport.build_feed_candidates", fake_build_feed_candidates
    )
    monkeypatch.setattr(
        "file_toolbox.common.settings.get",
        lambda key, default=None: (
            " http://proxy.local:8080 " if key == "forward_proxy" else default
        ),
    )

    coordinator = velopack_adapter.create_update_coordinator()

    assert captured_feeds == [("https://mirror.example", "")]
    assert coordinator._forward_proxy == "http://proxy.local:8080"
    assert coordinator._feed_candidates[-1].startswith("https://github.com/")
