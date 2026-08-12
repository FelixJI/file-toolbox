"""Qt worker 只消费 UpdateCoordinator 的公共行为。"""

from collections.abc import Callable

import pytest

from file_toolbox.gui.updater_widget import UpdateWorker
from file_toolbox.updater import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)

pytest.importorskip("PySide6")


class FakeCoordinator:
    def __init__(self) -> None:
        self.checked = False
        self.applied = False

    def check(self) -> UpdateCheckResult:
        self.checked = True
        return UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version="0.3.0")

    def download_and_apply(
        self, progress: Callable[[int], None] | None = None
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
    worker.checked.connect(checks.append)
    worker.progress.connect(progress.append)
    worker.applied.connect(applies.append)

    worker.do_check()
    worker.do_download_and_apply()

    assert checks == [UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version="0.3.0")]
    assert progress == [25, 100]
    assert applies == [UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)]
    assert coordinator.checked is True
    assert coordinator.applied is True
