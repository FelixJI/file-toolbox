"""Updater GUI 通过 UpdateCoordinator seam 的行为测试。"""

import os
from collections.abc import Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEventLoop, QMetaObject, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from file_toolbox.gui.main_window import MainWindow  # noqa: E402
from file_toolbox.gui.updater_widget import UpdateBanner, UpdateWorker  # noqa: E402
from file_toolbox.updater import (  # noqa: E402
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeCoordinator:
    def __init__(
        self,
        check_result: UpdateCheckResult,
        apply_result: UpdateApplyResult | None = None,
    ) -> None:
        self.check_result = check_result
        self.apply_result = apply_result or UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)

    def check(self) -> UpdateCheckResult:
        return self.check_result

    def download_and_apply(
        self, progress: Callable[[int], None] | None = None
    ) -> UpdateApplyResult:
        if progress is not None:
            progress(50)
            progress(100)
        return self.apply_result


def _available(version: str = "9.9.9") -> UpdateCheckResult:
    return UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version=version)


class TestUpdateBanner:
    def test_available_result_shows_version(self, app):
        banner = UpdateBanner()
        banner.show_result(_available("1.2.0"))
        assert banner.isHidden() is False
        assert "1.2.0" in banner.text()

    def test_installer_bridge_has_distinct_copy(self, app):
        banner = UpdateBanner()
        banner.show_result(UpdateCheckResult(UpdateCheckStatus.INSTALLER_REQUIRED))
        assert "安装" in banner.text()

    def test_click_emits_signal(self, app):
        banner = UpdateBanner()
        banner.show_result(_available())
        clicked: list[int] = []
        banner.clicked.connect(lambda: clicked.append(1))
        QTest.mouseClick(banner, Qt.MouseButton.LeftButton)
        assert clicked == [1]


class TestUpdateWorker:
    def test_check_emits_project_result(self, app):
        worker = UpdateWorker(FakeCoordinator(_available()))
        checked: list[UpdateCheckResult] = []
        ready: list[UpdateCheckResult] = []
        worker.checked.connect(checked.append)
        worker.ready.connect(ready.append)
        worker.do_check()
        assert checked == [_available()]
        assert ready == [_available()]

    def test_latest_does_not_emit_ready(self, app):
        result = UpdateCheckResult(UpdateCheckStatus.LATEST)
        worker = UpdateWorker(FakeCoordinator(result))
        ready: list[UpdateCheckResult] = []
        worker.ready.connect(ready.append)
        worker.do_check()
        assert ready == []

    def test_coordinator_exception_maps_to_failed_result(self, app):
        class BrokenCoordinator(FakeCoordinator):
            def check(self) -> UpdateCheckResult:
                raise RuntimeError("network down")

        worker = UpdateWorker(BrokenCoordinator(_available()))
        checked: list[UpdateCheckResult] = []
        worker.checked.connect(checked.append)
        worker.do_check()
        assert checked[0].status is UpdateCheckStatus.FAILED

    def test_apply_emits_progress_and_result(self, app):
        worker = UpdateWorker(FakeCoordinator(_available()))
        progress: list[int] = []
        applied: list[UpdateApplyResult] = []
        worker.progress.connect(progress.append)
        worker.applied.connect(applied.append)
        worker.do_download_and_apply()
        assert progress == [50, 100]
        assert applied == [UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)]

    def test_worker_methods_are_registered_slots(self, app):
        meta = UpdateWorker.staticMetaObject
        names = {bytes(meta.method(i).name()).decode() for i in range(meta.methodCount())}
        assert {"do_check", "do_download_and_apply"} <= names

    def test_check_works_via_real_queued_invocation(self, app):
        worker = UpdateWorker(FakeCoordinator(_available()))
        checked: list[UpdateCheckResult] = []
        worker.checked.connect(checked.append)
        worker.start()
        try:
            loop = QEventLoop()
            worker.checked.connect(loop.quit)
            QTimer.singleShot(3000, loop.quit)
            assert QMetaObject.invokeMethod(worker, "do_check", Qt.ConnectionType.QueuedConnection)
            loop.exec()
            assert checked == [_available()]
        finally:
            worker.quit()
            worker.wait(2000)


class TestMainWindowIntegration:
    def test_available_check_updates_about_and_banner(self, app):
        win = MainWindow(FakeCoordinator(_available("8.0.0")))
        win._manual_check_pending = True
        win._update_worker.do_check()
        app.processEvents()
        assert "8.0.0" in win._about_tab._check_result_lbl.text()
        assert win._update_banner.isHidden() is False

    def test_latest_check_updates_about_without_banner(self, app):
        win = MainWindow(FakeCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))
        win._manual_check_pending = True
        win._update_worker.do_check()
        app.processEvents()
        assert "最新" in win._about_tab._check_result_lbl.text()
        assert win._update_banner.isHidden() is True

    def test_bridge_check_explains_installer_migration(self, app):
        result = UpdateCheckResult(UpdateCheckStatus.INSTALLER_REQUIRED)
        win = MainWindow(FakeCoordinator(result))
        win._manual_check_pending = True
        win._update_worker.do_check()
        app.processEvents()
        assert "安装器" in win._about_tab._check_result_lbl.text()
        assert win._update_banner.isHidden() is False

    def test_cancelled_apply_does_not_quit(self, app, monkeypatch):
        win = MainWindow(
            FakeCoordinator(_available(), UpdateApplyResult(UpdateApplyStatus.CANCELLED))
        )
        quit_calls: list[int] = []
        monkeypatch.setattr(QApplication, "quit", lambda: quit_calls.append(1))
        win._on_update_applied(UpdateApplyResult(UpdateApplyStatus.CANCELLED))
        assert quit_calls == []

    def test_failed_apply_warns_and_keeps_current_process(self, app, monkeypatch):
        win = MainWindow(FakeCoordinator(_available()))
        warnings: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda _parent, _title, message: warnings.append(message),
        )
        win._on_update_applied(UpdateApplyResult(UpdateApplyStatus.FAILED, "损坏包"))
        assert "原程序未受影响" in warnings[0]
