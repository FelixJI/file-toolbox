"""UpdateWorker 的 Coordinator 下载/apply 结果分支补充测试。"""

from collections.abc import Callable

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from file_toolbox.gui.updater_widget import UpdateWorker
from file_toolbox.updater import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class ResultCoordinator:
    def __init__(self, result: UpdateApplyResult) -> None:
        self.result = result

    def check(self) -> UpdateCheckResult:
        return UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version="1.0.0")

    def download_and_apply(
        self, progress: Callable[[int], None] | None = None
    ) -> UpdateApplyResult:
        if progress is not None:
            progress(40)
            progress(100)
        return self.result


# 本文件在主线程直调 worker 方法验证信号载荷:worker 亲和性在自身线程,
# 普通函数槽的 Auto 连接会被 Queued 到未启动的 worker 队列,须显式直连。
_DIRECT = Qt.ConnectionType.DirectConnection


def test_download_and_apply_success_emits_progress_and_result(app):
    result = UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)
    worker = UpdateWorker(ResultCoordinator(result))
    progress: list[int] = []
    applied: list[UpdateApplyResult] = []
    worker.progress.connect(progress.append, _DIRECT)
    worker.applied.connect(applied.append, _DIRECT)
    worker.do_download_and_apply()
    assert progress == [40, 100]
    assert applied == [result]


def test_download_and_apply_failure_is_forwarded_as_project_result(app):
    result = UpdateApplyResult(UpdateApplyStatus.FAILED, "完整性校验失败")
    worker = UpdateWorker(ResultCoordinator(result))
    applied: list[UpdateApplyResult] = []
    worker.applied.connect(applied.append, _DIRECT)
    worker.do_download_and_apply()
    assert applied == [result]


def test_unexpected_coordinator_exception_is_mapped_without_leaking(app):
    class BrokenCoordinator(ResultCoordinator):
        def download_and_apply(
            self, progress: Callable[[int], None] | None = None
        ) -> UpdateApplyResult:
            raise ConnectionError("网络断开")

    worker = UpdateWorker(BrokenCoordinator(UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)))
    applied: list[UpdateApplyResult] = []
    worker.applied.connect(applied.append, _DIRECT)
    worker.do_download_and_apply()
    assert applied[0].status is UpdateApplyStatus.FAILED
    assert "网络断开" in applied[0].message
