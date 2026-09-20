"""#80:用受控 Event 与真实 Qt 队列验证取消/apply 提交边界。"""

from threading import Barrier, Event, Thread

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from file_toolbox.gui.main_window import MainWindow
from file_toolbox.gui.updater_widget import UpdateWorker
from file_toolbox.updater.coordinator import UpdateCancelled, UpdateRequest
from file_toolbox.updater.models import UpdateApplyResult, UpdateApplyStatus, UpdateCheckStatus
from file_toolbox.updater.velopack_adapter import VelopackUpdateCoordinator


class Asset:
    Version = "9.0.0"
    NotesMarkdown = "test"


class Update:
    TargetFullRelease = Asset()


class Manager:
    def __init__(self):
        self.downloads = 0
        self.applies = 0
        self.after_progress = lambda: None
        self.at_apply = lambda: None

    def check_for_updates(self):
        return Update()

    def download_updates(self, update, progress_callback=None):
        self.downloads += 1
        if progress_callback:
            progress_callback(50)
            progress_callback(100)
        self.after_progress()

    def wait_exit_then_apply_updates(self, update, *, silent, restart):
        self.applies += 1
        self.at_apply()


def coordinator(manager):
    result = VelopackUpdateCoordinator(
        feed_candidates=("https://unused.invalid",), manager_factory=lambda _: manager
    )
    assert result.check().status is UpdateCheckStatus.AVAILABLE
    return result


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_queued_cancel_survives_slot_start_and_next_request_runs(app):
    manager = Manager()
    worker = UpdateWorker(coordinator(manager))
    done = Event()
    results = []
    worker.applied.connect(
        lambda request, result: (results.append((request, result)), done.set()),
        Qt.ConnectionType.DirectConnection,
    )
    first = worker.start_download()  # 真实 queued signal;线程尚未运行,槽不可能抢先执行。
    assert first is not None and worker.cancel_download(first)
    assert worker.start_download() is None
    worker.start()
    try:
        assert done.wait(5)
        assert results[0][0] is first
        assert results[0][1].status is UpdateApplyStatus.CANCELLED
        assert manager.downloads == manager.applies == 0
        done.clear()
        second = worker.start_download()
        assert second is not None and second is not first
        assert done.wait(5)
        assert results[1][0] is second
        assert results[1][1].status is UpdateApplyStatus.APPLY_STARTED
        assert manager.downloads == manager.applies == 1
        # 重复/旧槽直接调用也不能重复下载或 apply。
        worker.do_download_and_apply(first)
        worker.do_download_and_apply(second)
        assert worker.start_download() is None
        assert len(results) == 2 and manager.applies == 1
    finally:
        worker.quit()
        assert worker.wait(5000)


@pytest.mark.parametrize("stage", ["before_download", "progress", "after_last_progress"])
def test_accepted_cancel_never_calls_fake_sdk_apply(stage):
    manager = Manager()
    service = coordinator(manager)
    request = UpdateRequest()
    if stage == "before_download":
        assert request.cancel()
    elif stage == "after_last_progress":
        manager.after_progress = lambda: request.cancel()

    def progress(value):
        if stage == "progress":
            assert request.cancel()

    result = service.download_and_apply(progress, request=request)
    assert result.status is UpdateApplyStatus.CANCELLED
    assert manager.applies == 0
    assert manager.downloads == (0 if stage == "before_download" else 1)


def test_cancel_between_final_progress_and_return_is_synchronized():
    manager = Manager()
    service = coordinator(manager)
    request = UpdateRequest()
    reached, release = Event(), Event()
    results = []

    def wait_after_progress():
        reached.set()
        assert release.wait(5)

    manager.after_progress = wait_after_progress
    thread = Thread(target=lambda: results.append(service.download_and_apply(request=request)))
    thread.start()
    try:
        assert reached.wait(5)
        assert request.cancel()
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert results[0].status is UpdateApplyStatus.CANCELLED
    assert manager.applies == 0


def test_cancel_after_commit_is_refused_and_apply_happens_once():
    manager = Manager()
    service = coordinator(manager)
    request = UpdateRequest()
    committed = []

    def at_boundary():
        committed.append(request.applying)
        assert not request.cancel()

    result = service.download_and_apply(request=request, before_apply=at_boundary)
    assert committed == [True]
    assert result.status is UpdateApplyStatus.APPLY_STARTED
    assert manager.applies == 1
    assert service.download_and_apply().status is UpdateApplyStatus.FAILED
    assert manager.applies == 1


def test_cancel_and_apply_racing_have_only_one_winner():
    request = UpdateRequest()
    ready = Barrier(3)
    cancelled, committed = [], []

    def cancel():
        ready.wait()
        cancelled.append(request.cancel())

    def commit():
        ready.wait()
        try:
            request.begin_apply()
        except UpdateCancelled:
            committed.append(False)
        else:
            committed.append(True)

    threads = [Thread(target=cancel), Thread(target=commit)]
    for thread in threads:
        thread.start()
    ready.wait()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    assert cancelled[0] != committed[0]


def test_worker_failure_then_new_request_keeps_results_bound(app):
    manager = Manager()
    service = coordinator(manager)
    worker = UpdateWorker(service)
    results = []
    worker.applied.connect(
        lambda req, result: results.append((req, result)), Qt.ConnectionType.DirectConnection
    )
    manager.after_progress = lambda: (_ for _ in ()).throw(OSError("disk"))
    first = worker.start_download()
    worker.do_download_and_apply(first)
    assert results[0][0] is first and results[0][1].status is UpdateApplyStatus.FAILED
    manager.after_progress = lambda: None
    second = worker.start_download()
    assert second is not None and second is not first
    worker.do_download_and_apply(first)
    worker.do_download_and_apply(second)
    assert len(results) == 2 and results[1][0] is second
    assert manager.applies == 1


@pytest.fixture
def win(app, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    manager = Manager()
    window = MainWindow(coordinator(manager))
    window._pending_update = window._update_worker._coordinator.check()
    return window


def test_old_gui_signals_do_not_mutate_current_request(win, monkeypatch):
    current, old = UpdateRequest(), UpdateRequest()
    win._download_request = current
    dialog = QProgressDialog("current", "取消", 0, 100, win)
    dialog.setValue(15)
    win._update_dialog = dialog
    quits = []
    monkeypatch.setattr(win, "_shutdown_for_restart", lambda: quits.append(1))
    win._on_update_progress(old, 100)
    win._on_update_applying(old)
    win._on_update_applied(old, UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED))
    assert dialog.value() == 15 and dialog.labelText() == "current"
    assert win._download_request is current and win._update_dialog is dialog and not quits
    dialog.close()


def test_gui_accepted_cancel_keeps_retry_disabled_until_result(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Apply)
    win._start_download()
    request = win._download_request
    assert request is not None
    win._on_download_cancel()
    assert win._download_request is request and win._update_banner.isHidden()
    win._start_download()
    assert win._download_request is request
    win._update_worker.do_download_and_apply(request)
    # worker signals delivered to GUI by the real Qt event loop.
    QApplication.processEvents()
    assert win._download_request is None
    assert not win._update_banner.isHidden()
    assert "已取消" in win.statusBar().currentMessage()


def test_gui_late_cancel_announces_non_cancelable_apply(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Apply)
    win._start_download()
    request = win._download_request
    request.begin_apply()
    win._on_download_cancel()
    assert win._download_request is request
    assert win._update_dialog is not None
    assert "已无法取消" in win._update_dialog.labelText()
    assert win._update_banner.isHidden()
    win._update_dialog.close()


def test_cancel_accepted_before_failed_result_is_reported_as_cancelled(app):
    manager = Manager()
    worker = UpdateWorker(coordinator(manager))
    result = []
    worker.applied.connect(
        lambda req, value: result.append(value), Qt.ConnectionType.DirectConnection
    )
    request = worker.start_download()

    def fail_after_cancel():
        assert worker.cancel_download(request)
        raise OSError("download failed while cancellation was pending")

    manager.after_progress = fail_after_cancel
    worker.do_download_and_apply(request)
    assert result[0].status is UpdateApplyStatus.CANCELLED
    assert not worker.cancel_download(request)
    assert not request.cancel()
    assert manager.applies == 0


def test_apply_exception_does_not_allow_duplicate_request_or_claim_original_unchanged(
    win, monkeypatch
):
    manager = Manager()
    worker = UpdateWorker(coordinator(manager))
    manager.at_apply = lambda: (_ for _ in ()).throw(OSError("SDK apply outcome unknown"))
    results = []
    worker.applied.connect(
        lambda req, value: results.append(value), Qt.ConnectionType.DirectConnection
    )
    request = worker.start_download()
    worker.do_download_and_apply(request)
    assert results[0].status is UpdateApplyStatus.FAILED and request.applying
    assert not worker.cancel_download(request)
    assert worker.start_download() is None and manager.applies == 1
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    win._download_request = request
    win._on_update_applied(request, results[0])
    assert "无法确认" in warnings[0] and "原程序未受影响" not in warnings[0]
    assert win._download_request is request and win._update_banner.isHidden()


@pytest.mark.parametrize("start_during_confirmation", [False, True])
def test_gui_refuses_update_while_business_thread_runs(
    app, monkeypatch, tmp_path, start_during_confirmation
):
    from PySide6.QtCore import QThread

    monkeypatch.chdir(tmp_path)
    manager = Manager()
    window = MainWindow(coordinator(manager))
    window._ensure_tab(7)
    window._pending_update = window._update_worker._coordinator.check()
    release, entered = Event(), Event()

    class Business(QThread):
        def run(self):
            entered.set()
            assert release.wait(10)

    business = Business(window._pdf_sort_tab)
    update = window._update_worker
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, _text: warnings.append(title))
    monkeypatch.setattr(QApplication, "quit", lambda: None)

    def begin():
        business.start()
        assert entered.wait(5)

    def confirm(*args):
        if start_during_confirmation:
            begin()
        return QMessageBox.StandardButton.Apply

    monkeypatch.setattr(QMessageBox, "question", confirm)
    if not start_during_confirmation:
        begin()
    update.start()
    try:
        window._start_download()
        assert window._download_request is None, "运行中业务不能进入 SDK 更新提交链"
        assert manager.downloads == manager.applies == 0
        assert warnings == ["后台任务尚未结束"]
        assert window._tabs.isEnabled()
    finally:
        release.set()
        assert business.wait(5000)
        update.quit()
        assert update.wait(5000)
        app.processEvents()
        window.close()


@pytest.mark.parametrize("outcome", ["cancel", "failure", "apply", "closing-cancel"])
def test_gui_update_excludes_new_business_until_result(app, monkeypatch, tmp_path, outcome):
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtTest import QTest

    monkeypatch.chdir(tmp_path)
    manager = Manager()
    window = MainWindow(coordinator(manager))
    window._tabs.setCurrentIndex(6)
    window._pending_update = window._update_worker._coordinator.check()
    entered, release = Event(), Event()

    def download_boundary():
        entered.set()
        assert release.wait(10)
        if outcome == "failure":
            raise OSError("fake download failed")

    manager.after_progress = download_boundary
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Apply)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: None)
    monkeypatch.setattr(QApplication, "quit", lambda: None)
    update = window._update_worker
    update.start()
    try:
        window._start_download()
        assert entered.wait(5)
        assert not window._tabs.isEnabled() and not window.btn_history.isEnabled()
        clicked = []
        window._excel_merge_tab.ui.btn_merge.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(window._excel_merge_tab.ui.btn_merge, Qt.MouseButton.LeftButton)
        assert clicked == []
        if outcome in {"cancel", "closing-cancel"}:
            window._on_download_cancel()
            assert not window._tabs.isEnabled(), "仅提出取消不能提前恢复业务入口"
        if outcome == "closing-cancel":
            assert not window.close()
        release.set()
        loop = QEventLoop()
        timer = QTimer()
        timer.timeout.connect(lambda: loop.quit() if window._download_request is None else None)
        timer.start(2)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        assert window._download_request is None
        if outcome in {"apply", "closing-cancel"}:
            assert not window._tabs.isEnabled() and not window.btn_history.isEnabled()
        else:
            assert window._tabs.isEnabled() and window.btn_history.isEnabled()
        assert manager.downloads == 1
        assert manager.applies == (1 if outcome == "apply" else 0)
    finally:
        release.set()
        update.quit()
        assert update.wait(5000)
        app.processEvents()
        window.close()
