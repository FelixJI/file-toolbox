"""UpdateCoordinator 公共行为契约。"""

from collections.abc import Callable

from file_toolbox.updater import (
    UpdateApplyStatus,
    UpdateCheckStatus,
    VelopackUpdateCoordinator,
)


class FakeAsset:
    Version = "0.3.0"
    NotesMarkdown = "修复更新"


class FakeUpdateInfo:
    TargetFullRelease = FakeAsset()


class FakeManager:
    def __init__(
        self,
        *,
        update: object | None = None,
        error: Exception | None = None,
        portable: bool = False,
    ) -> None:
        self.update = update
        self.error = error
        self.portable = portable
        self.downloaded: object | None = None
        self.applied: object | None = None

    def get_is_portable(self) -> bool:
        return self.portable

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


def test_apply_requires_prior_available_check() -> None:
    coordinator = VelopackUpdateCoordinator(
        feed_candidates=("https://direct.invalid/",),
        manager_factory=lambda _source: FakeManager(),
    )

    result = coordinator.download_and_apply()

    assert result.status is UpdateApplyStatus.FAILED
    assert result.message == "请先检查更新"


def test_real_velopack_binding_construction_failure_is_observable() -> None:
    """开发态无 manifest 时 binding 异常只映射为失败。"""

    coordinator = VelopackUpdateCoordinator(feed_candidates=("http://127.0.0.1:1/",))

    assert coordinator.check().status is UpdateCheckStatus.FAILED


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
