"""Updater GUI 通过 UpdateCoordinator seam 的行为测试。"""

import os
from collections.abc import Callable

from file_toolbox.updater.coordinator import UpdateRequest

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
        self,
        progress: Callable[[int], None] | None = None,
        *,
        request: UpdateRequest | None = None,
        before_apply: Callable[[], None] | None = None,
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

    def test_click_emits_signal(self, app):
        banner = UpdateBanner()
        banner.show_result(_available())
        clicked: list[int] = []
        banner.clicked.connect(lambda: clicked.append(1))
        QTest.mouseClick(banner, Qt.MouseButton.LeftButton)
        assert clicked == [1]

    def test_banner_is_focusable_button(self, app):
        """回归:横幅曾是 QLabel+mousePressEvent,键盘与 UIA 均无法触发。

        必须是可聚焦的按钮类控件(QPushButton 暴露 UIA Invoke 模式)。
        """
        from PySide6.QtWidgets import QPushButton

        assert isinstance(UpdateBanner(), QPushButton)
        assert UpdateBanner().focusPolicy() != Qt.FocusPolicy.NoFocus

    def test_keyboard_space_triggers_clicked(self, app):
        """Space 键触发 clicked(标准按钮键盘语义;Enter 仅对话框默认按钮场景)。"""
        banner = UpdateBanner()
        banner.show_result(_available())
        clicked: list[int] = []
        banner.clicked.connect(lambda: clicked.append(1))
        QTest.keyClick(banner, Qt.Key.Key_Space)
        assert clicked == [1]

    def test_programmatic_click_triggers_clicked(self, app):
        """click() 触发信号 —— UIA Invoke 模式的等价调用路径(自动化可点击)。"""
        banner = UpdateBanner()
        banner.show_result(_available())
        clicked: list[int] = []
        banner.clicked.connect(lambda: clicked.append(1))
        banner.click()
        assert clicked == [1]


class TestUpdateWorker:
    # 前 4 个用例在主线程直调 worker 方法验证信号载荷:worker 亲和性在自身
    # 线程,普通函数槽的 Auto 连接会被 Queued 到未启动的 worker 队列,须显式
    # 直连;真实跨线程投递由 test_check_works_via_real_queued_invocation 覆盖。
    _DIRECT = Qt.ConnectionType.DirectConnection

    def test_check_emits_project_result(self, app):
        worker = UpdateWorker(FakeCoordinator(_available()))
        checked: list[UpdateCheckResult] = []
        ready: list[UpdateCheckResult] = []
        worker.checked.connect(checked.append, self._DIRECT)
        worker.ready.connect(ready.append, self._DIRECT)
        worker.do_check()
        assert checked == [_available()]
        assert ready == [_available()]

    def test_latest_does_not_emit_ready(self, app):
        result = UpdateCheckResult(UpdateCheckStatus.LATEST)
        worker = UpdateWorker(FakeCoordinator(result))
        ready: list[UpdateCheckResult] = []
        worker.ready.connect(ready.append, self._DIRECT)
        worker.do_check()
        assert ready == []

    def test_coordinator_exception_maps_to_failed_result(self, app):
        class BrokenCoordinator(FakeCoordinator):
            def check(self) -> UpdateCheckResult:
                raise RuntimeError("network down")

        worker = UpdateWorker(BrokenCoordinator(_available()))
        checked: list[UpdateCheckResult] = []
        worker.checked.connect(checked.append, self._DIRECT)
        worker.do_check()
        assert checked[0].status is UpdateCheckStatus.FAILED

    def test_apply_emits_progress_and_result(self, app):
        worker = UpdateWorker(FakeCoordinator(_available()))
        progress: list[int] = []
        applied: list[UpdateApplyResult] = []
        worker.progress.connect(lambda req, value: progress.append(value), self._DIRECT)
        worker.applied.connect(lambda req, result: applied.append(result), self._DIRECT)
        worker.do_download_and_apply(worker.start_download())
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
    def test_available_check_updates_page_and_banner(self, app):
        win = MainWindow(FakeCoordinator(_available("8.0.0")))
        win._tabs.setCurrentIndex(9)  # 独立更新页(懒构造 Tab)
        win._update_worker.do_check()
        app.processEvents()
        assert "8.0.0" in win._update_tab._status_lbl.text()
        assert win._update_banner.isHidden() is False
        assert win._update_tab.btn_download_update.isHidden() is False

    def test_latest_check_updates_page_without_banner(self, app):
        win = MainWindow(FakeCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))
        win._tabs.setCurrentIndex(9)
        win._update_worker.do_check()
        app.processEvents()
        assert "最新" in win._update_tab._status_lbl.text()
        assert win._update_banner.isHidden() is True

    def test_later_check_clears_stale_pending_and_banner(self, app):
        """AVAILABLE → 再查 LATEST:过期 banner 与候选必须清除(#128 AC2)。

        旧实现 LATEST/FAILED 不清 _pending_update/横幅,而 coordinator 已重置
        绑定候选,用户点击过期横幅只会得到"请先检查更新"失败。
        """
        win = MainWindow(FakeCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))
        win._on_update_checked(_available("8.0.0"))
        assert win._update_banner.isHidden() is False
        assert win._pending_update is not None

        win._on_update_checked(UpdateCheckResult(UpdateCheckStatus.LATEST))

        assert win._update_banner.isHidden() is True
        assert win._pending_update is None

    def test_failed_check_clears_stale_pending_and_banner(self, app):
        win = MainWindow(FakeCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))
        win._on_update_checked(_available("8.0.0"))

        win._on_update_checked(
            UpdateCheckResult(UpdateCheckStatus.FAILED, message="无法连接更新源")
        )

        assert win._update_banner.isHidden() is True
        assert win._pending_update is None

    def test_auto_result_reaches_already_open_update_page(self, app):
        """自动检查结果到达时,已打开的更新页实时回放(不再只服务手动检查)。"""
        win = MainWindow(FakeCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))
        win._tabs.setCurrentIndex(9)  # 更新页已构造
        assert win._update_tab is not None

        win._on_update_checked(_available("8.0.0"))

        assert "8.0.0" in win._update_tab._status_lbl.text()
        assert win._update_tab.btn_download_update.isHidden() is False

    def test_update_page_lazy_construction_replays_latest_state(self, app):
        """自动检查先于页面构造:任何最终状态(含 LATEST/FAILED)都可回放。"""
        win = MainWindow(FakeCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))
        win._on_update_checked(UpdateCheckResult(UpdateCheckStatus.LATEST))

        win._tabs.setCurrentIndex(9)  # 懒构造更新页

        assert "最新" in win._update_tab._status_lbl.text()

    def test_unsupported_check_result_shown_on_update_page(self, app):
        """UNSUPPORTED 形态(源码/开发运行)在更新页给出准确原因与横幅隐藏。"""
        win = MainWindow(FakeCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))
        win._tabs.setCurrentIndex(9)
        win._on_update_checked(_available("8.0.0"))

        win._on_update_checked(
            UpdateCheckResult(
                UpdateCheckStatus.UNSUPPORTED,
                message="当前运行形态未检测到有效的 Velopack 安装布局",
            )
        )

        assert "安装布局" in win._update_tab._status_lbl.text()
        assert win._update_banner.isHidden() is True
        assert win._pending_update is None

    def test_cancelled_apply_does_not_quit(self, app, monkeypatch):
        win = MainWindow(
            FakeCoordinator(_available(), UpdateApplyResult(UpdateApplyStatus.CANCELLED))
        )
        quit_calls: list[int] = []
        monkeypatch.setattr(QApplication, "quit", lambda: quit_calls.append(1))
        win._download_request = UpdateRequest()
        win._on_update_applied(
            win._download_request, UpdateApplyResult(UpdateApplyStatus.CANCELLED)
        )
        assert quit_calls == []

    def test_failed_apply_warns_and_keeps_current_process(self, app, monkeypatch):
        win = MainWindow(FakeCoordinator(_available()))
        warnings: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda _parent, _title, message: warnings.append(message),
        )
        win._download_request = UpdateRequest()
        win._on_update_applied(
            win._download_request, UpdateApplyResult(UpdateApplyStatus.FAILED, "损坏包")
        )
        assert "原程序未受影响" in warnings[0]


class TestUpdateOutcomeReconciliation:
    """跨启动更新对账(#128 AC5):APPLY_STARTED/窗口重现不等于成功,须对账真实版本。"""

    def _confirmed_window(self, app, monkeypatch, tmp_path, apply_result=None):
        monkeypatch.chdir(tmp_path)
        coordinator = FakeCoordinator(
            _available("8.0.0"), apply_result or UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)
        )
        win = MainWindow(coordinator)
        win._tabs.setCurrentIndex(9)  # 下载只能从更新页发起
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Apply,
        )
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
        win._on_update_checked(_available("8.0.0"))
        win._start_download()
        return win

    def test_download_confirmation_records_target(self, app, monkeypatch, tmp_path):
        from file_toolbox.common import settings

        win = self._confirmed_window(app, monkeypatch, tmp_path)

        assert win._download_request is not None
        record = settings.get("update/pending_apply")
        assert isinstance(record, dict)
        assert record["target_version"] == "8.0.0"
        assert record["written_at"]

    def test_cancelled_apply_clears_record(self, app, monkeypatch, tmp_path):
        from file_toolbox.common import settings

        win = self._confirmed_window(app, monkeypatch, tmp_path)
        assert win._download_request is not None

        win._on_update_applied(
            win._download_request, UpdateApplyResult(UpdateApplyStatus.CANCELLED)
        )

        assert settings.get("update/pending_apply") is None

    def test_pre_apply_failure_clears_record(self, app, monkeypatch, tmp_path):
        from file_toolbox.common import settings

        win = self._confirmed_window(app, monkeypatch, tmp_path)
        win._on_update_applied(
            win._download_request, UpdateApplyResult(UpdateApplyStatus.FAILED, "下载失败")
        )

        assert settings.get("update/pending_apply") is None

    def test_apply_stage_failure_keeps_record_for_next_start(self, app, monkeypatch, tmp_path):
        from file_toolbox.common import settings

        win = self._confirmed_window(app, monkeypatch, tmp_path)
        assert win._download_request is not None
        win._download_request.begin_apply()  # 已跨过不可取消边界 → 结果不确定

        win._on_update_applied(
            win._download_request, UpdateApplyResult(UpdateApplyStatus.FAILED, "接管结果未知")
        )

        assert isinstance(settings.get("update/pending_apply"), dict)

    def test_startup_reconciles_successful_update(self, app, monkeypatch, tmp_path):
        from file_toolbox.common import settings
        from file_toolbox.common.metadata import VERSION

        monkeypatch.chdir(tmp_path)
        settings.set("update/pending_apply", {"target_version": VERSION, "written_at": "t"})
        win = MainWindow(FakeCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))

        assert "已成功更新到" in win.statusBar().currentMessage()
        assert settings.get("update/pending_apply") is None

    def test_startup_reports_unconfirmed_update(self, app, monkeypatch, tmp_path):
        from file_toolbox.common import settings

        monkeypatch.chdir(tmp_path)
        settings.set("update/pending_apply", {"target_version": "0.0.1", "written_at": "t"})
        win = MainWindow(FakeCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))

        assert "未确认完成" in win.statusBar().currentMessage()
        assert settings.get("update/pending_apply") is None

    def test_startup_without_record_is_silent(self, app, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        win = MainWindow(FakeCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))

        assert win.statusBar().currentMessage() in ("", "就绪")
