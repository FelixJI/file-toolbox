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
