"""Qt worker 只消费 UpdateCoordinator 的公共行为。"""

from collections.abc import Callable

import pytest

from file_toolbox.updater.coordinator import UpdateRequest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from file_toolbox.gui.updater_widget import UpdateWorker
from file_toolbox.updater import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)


class FakeCoordinator:
    def __init__(self) -> None:
        self.checked = False
        self.applied = False

    def check(self) -> UpdateCheckResult:
        self.checked = True
        return UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version="0.3.0")

    def download_and_apply(
        self,
        progress: Callable[[int], None] | None = None,
        *,
        request: UpdateRequest | None = None,
        before_apply: Callable[[], None] | None = None,
    ) -> UpdateApplyResult:
        self.applied = True
        if progress is not None:
            progress(25)
            progress(100)
        return UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)


def test_worker_exposes_only_coordinator_result_models() -> None:
    coordinator = FakeCoordinator()
    worker = UpdateWorker(coordinator)
    checks: list[UpdateCheckResult] = []
    progress: list[int] = []
    applies: list[UpdateApplyResult] = []
    # 主线程直调方法验证信号载荷:worker 亲和性在自身线程,普通函数槽的
    # Auto 连接会被 Queued 到未启动的 worker 队列,须显式 DirectConnection。
    worker.checked.connect(checks.append, Qt.ConnectionType.DirectConnection)
    worker.progress.connect(
        lambda req, value: progress.append(value), Qt.ConnectionType.DirectConnection
    )
    worker.applied.connect(
        lambda req, result: applies.append(result), Qt.ConnectionType.DirectConnection
    )

    worker.do_check()
    worker.do_download_and_apply(worker.start_download())

    assert checks == [UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version="0.3.0")]
    assert progress == [25, 100]
    assert applies == [UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)]
    assert coordinator.checked is True
    assert coordinator.applied is True


def test_worker_rebuilds_coordinator_per_check_via_factory() -> None:
    """每轮检查经工厂取新 coordinator:保存代理设置后下一轮即生效(#128 AC3)。"""

    first, second = FakeCoordinator(), FakeCoordinator()
    created = iter([first, second])
    calls: list[int] = []

    def factory() -> FakeCoordinator:
        calls.append(1)
        return next(created)

    worker = UpdateWorker(first, coordinator_factory=factory)

    worker.do_check()
    worker.do_check()

    assert calls == [1, 1]
    assert first.checked is True
    assert second.checked is True
    # 下载绑定最近一轮检查的 coordinator
    assert worker._coordinator is second


def test_worker_default_factory_reuses_injected_coordinator() -> None:
    """注入 coordinator(测试缝隙)时工厂复用注入实例,不落到生产装配。"""

    coordinator = FakeCoordinator()
    worker = UpdateWorker(coordinator)

    worker.do_check()

    assert worker._coordinator is coordinator
    assert coordinator.checked is True


class ExpectedVersionRecorder(FakeCoordinator):
    """记录 download_and_apply 收到的 expected_version(不传时为哨兵)。"""

    def __init__(self) -> None:
        super().__init__()
        self.expected: list[str | None] = []

    def download_and_apply(
        self,
        progress: Callable[[int], None] | None = None,
        *,
        request: UpdateRequest | None = None,
        before_apply: Callable[[], None] | None = None,
        expected_version: str | None = None,
    ) -> UpdateApplyResult:
        self.expected.append(expected_version)
        return super().download_and_apply(progress, request=request, before_apply=before_apply)


def test_start_download_carries_expected_version_to_coordinator() -> None:
    """确认版本随下载请求传递:coordinator 据此校验候选绑定(#128 AC2)。"""

    coordinator = ExpectedVersionRecorder()
    worker = UpdateWorker(coordinator)
    worker.do_check()

    request = worker.start_download(expected_version="0.3.0")
    assert request is not None
    worker.do_download_and_apply(request)

    assert coordinator.expected == ["0.3.0"]
    assert coordinator.applied is True


def test_download_without_expected_version_keeps_legacy_call_shape() -> None:
    """未提供确认版本时保持旧调用形状(老 coordinator/fake 无该参数)。"""

    coordinator = ExpectedVersionRecorder()
    worker = UpdateWorker(coordinator)
    worker.do_check()

    request = worker.start_download()
    assert request is not None
    worker.do_download_and_apply(request)

    assert coordinator.expected == [None]
