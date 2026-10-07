"""#140:事件同步扫描/冻结预览/真实写入取消，不依赖吞吐时间猜测。"""

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from gui_model_helpers import cell, wait_page
from PySide6.QtCore import QEventLoop, QThread, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox, QTabWidget, QWidget

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.common.paths import GuiDataRootPolicy, use_data_root_policy
from file_toolbox.core import rename_execution
from file_toolbox.core.batch_rename import FileRenameService
from file_toolbox.gui.dialogs.excel_merge_tab import ExcelMergeTab
from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab
from file_toolbox.gui.dialogs.markdown_tab import MarkdownConvertTab
from file_toolbox.gui.dialogs.pdf_sort_tab import PdfSortTab
from file_toolbox.gui.dialogs.pdf_tab import PDFGeneratorDialog
from file_toolbox.gui.dialogs.rename_tab import FileRenamerDialog
from file_toolbox.gui.dialogs.replace_tab import ContentReplaceDialog
from file_toolbox.gui.main_window import MainWindow
from file_toolbox.gui.workers.file_scan_worker import FileScanWorker
from file_toolbox.gui.workers.rename_worker import RenameExecuteWorker, RenamePreviewWorker
from file_toolbox.updater import UpdateCheckResult, UpdateCheckStatus


def until(predicate):
    loop = QEventLoop()
    poll = QTimer()
    timeout = QTimer()
    timeout.setSingleShot(True)
    expired = []
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    timeout.timeout.connect(lambda: (expired.append(True), loop.quit()))
    poll.start(5)
    timeout.start(5000)
    loop.exec()
    assert not expired


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated(app, tmp_path, monkeypatch):
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.StandardButton.Ok)
    with use_data_root_policy(GuiDataRootPolicy(tmp_path / "data")):
        yield


@pytest.mark.parametrize(
    "page_type,suffix",
    [
        (FileRenamerDialog, ".txt"),
        (ContentReplaceDialog, ".txt"),
        (PDFGeneratorDialog, ".pdf"),
        (MarkdownConvertTab, ".md"),
        (InvoiceTab, ".xml"),
        (PdfSortTab, ".pdf"),
        (ExcelMergeTab, ".xlsx"),
    ],
)
def test_first_batch_can_switch_cancel_and_queue_new_directory(
    isolated, app, tmp_path, monkeypatch, page_type, suffix
):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    source = old / ("blocked" + suffix)
    source.write_text("synthetic")
    latest = new / ("latest" + suffix)
    latest.write_text("synthetic")
    entered = threading.Event()
    release = threading.Event()
    original_stat = Path.stat
    threads = []

    def held_stat(path, *args, **kwargs):
        if path == source:
            threads.append(QThread.currentThread())
            entered.set()
            assert release.wait(5)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", held_stat)
    page = page_type()
    if not isinstance(page, PDFGeneratorDialog):
        assert page.ui.list_files.uniformItemSizes()
    tabs = QTabWidget()
    tabs.addTab(page, "导入")
    tabs.addTab(QWidget(), "其他")
    if isinstance(page, (FileRenamerDialog, ContentReplaceDialog, PDFGeneratorDialog)):
        supported = page._is_file_supported
    else:
        supported = page._is_source
    inserted_threads = []
    page._file_model.rowsInserted.connect(
        lambda *_: inserted_threads.append(QThread.currentThread())
    )
    page._queue_import([], supported, old)
    worker = page._task.worker
    try:
        until(entered.is_set)
        assert isinstance(worker, FileScanWorker)
        assert worker.parent() is page and worker.isRunning()
        assert page._file_model.rowCount() == 0
        switched = []
        QTimer.singleShot(0, lambda: (tabs.setCurrentIndex(1), switched.append(True)))
        until(lambda: bool(switched))
        assert tabs.currentIndex() == 1
        page._invalidate_import()  # 清空发起取消，后台不可中断调用仍准确等待。
        assert page._task.worker is worker
        page._queue_import([], supported, new)
        assert page._task.worker is worker and bool(page._import_pending)
        release.set()
        wait_page(page)
        assert page._file_model.files == [latest]
        assert source not in page._file_model.files
        assert threads and all(t != app.thread() for t in threads)
        assert inserted_threads and all(t == app.thread() for t in inserted_threads)
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)
        tabs.close()


def test_scan_error_is_diagnosable_and_close_rejects_late_batch(isolated, tmp_path, monkeypatch):
    page = MarkdownConvertTab()
    source = tmp_path / "blocked.md"
    source.write_text("synthetic")
    entered, release = threading.Event(), threading.Event()
    original_stat = Path.stat

    def denied(path, *args, **kwargs):
        if path == source:
            entered.set()
            assert release.wait(5)
            raise PermissionError("controlled denied")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", denied)
    page._add_paths([source])
    try:
        until(entered.is_set)
        release.set()
        wait_page(page)
        assert page._import_errors and "controlled denied" in page._import_errors[-1]
        assert "controlled denied" in page.ui.lbl_status.text()
        entered.clear()
        release.clear()
        page._add_paths([source])
        until(entered.is_set)
        event = QCloseEvent()
        page.closeEvent(event)
        assert not event.isAccepted() and page._task.close_pending
        release.set()
        until(lambda: page._task.worker is None)
        assert page._file_model.files == []
    finally:
        release.set()
        page._task.cancel()
        until(lambda: page._task.worker is None)


def test_rename_preview_freezes_nested_params_and_rejects_stale_input(
    isolated, tmp_path, monkeypatch
):
    page = FileRenamerDialog()
    source = tmp_path / "abc.txt"
    source.write_text("payload")
    page.selected_files = [source]
    page.operations = [{"type": "delete_chars", "params": {"value": 1}}]
    entered, release = threading.Event(), threading.Event()
    original_validate = page._svc.validate_operations
    observed = []

    def held_validate(operations):
        observed.append(operations)
        entered.set()
        assert release.wait(5)
        return original_validate(operations)

    monkeypatch.setattr(page._svc, "validate_operations", held_validate)
    page._do_refresh_preview()
    worker = page.worker
    try:
        until(entered.is_set)
        assert isinstance(worker, RenamePreviewWorker)
        page.operations[0]["params"]["value"] = 2
        assert worker.operations[0]["params"]["value"] == 1
        release.set()
        wait_page(page)
        assert page.operations[0]["params"]["value"] == 2
        assert observed[0][0]["params"]["value"] == "1"  # 校验只规范化worker快照。
        assert cell(page.ui.table_preview, 0, 1) == "c.txt"
        assert page._preview_snapshot == (page.selected_files, page.operations)

        # 确认框内输入被修改，已展示映射不能被提交。
        def change_during_confirmation(*args, **kwargs):
            page.operations[0]["params"]["value"] = 1
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr(QMessageBox, "question", change_during_confirmation)
        page._execute()
        assert page.worker is None and source.read_text() == "payload"
        assert not (tmp_path / "c.txt").exists()
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)


def test_rename_cancel_keeps_success_history_and_safe_undo(isolated, tmp_path, monkeypatch):
    page = FileRenamerDialog()
    source = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    source.write_text("first")
    second.write_text("second")
    page.selected_files = [source, second]
    page.operations = [{"type": "add_prefix", "params": {"text": "done_"}}]
    page._history = JsonHistoryStore(tmp_path / "history")
    page._svc = FileRenameService(page._history)
    page._do_refresh_preview()
    wait_page(page)
    entered, release = threading.Event(), threading.Event()
    original_rename = rename_execution.rename_no_replace
    calls = []

    def held_rename(old, new):
        calls.append(QThread.currentThread())
        original_rename(old, new)
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(rename_execution, "rename_no_replace", held_rename)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    preview_starts = []
    original_preview = RenamePreviewWorker.run

    def record_preview(worker):
        preview_starts.append(worker)
        original_preview(worker)

    monkeypatch.setattr(RenamePreviewWorker, "run", record_preview)
    page._execute()
    worker = page.worker
    results = []
    assert isinstance(worker, RenameExecuteWorker)
    worker.execute_ok.connect(results.append)
    try:
        until(entered.is_set)
        assert worker.isRunning()
        page._on_cancel()
        assert page.worker is worker and not page.ui.btn_execute.isEnabled()
        page._execute()
        assert page.worker is worker
        release.set()
        wait_page(page)
        settled = []
        QTimer.singleShot(250, lambda: settled.append(True))
        until(lambda: bool(settled))
        assert not preview_starts
        assert page._preview_snapshot is None
        assert results[0].cancelled and results[0].successful == {
            source: source.with_name("done_a.txt")
        }
        assert page.selected_files == [source.with_name("done_a.txt"), second]
        assert second.read_text() == "second"
        assert calls and all(t != QApplication.instance().thread() for t in calls)
        records = page._history.get_records("rename")
        assert len(records) == 1 and len(records[0]["data"]["rename_map"]) == 1
        monkeypatch.setattr(rename_execution, "rename_no_replace", original_rename)
        undo = page._svc.undo_record(records[0]["id"])
        assert undo.count == 1 and not undo.messages
        assert source.read_text() == "first" and second.read_text() == "second"
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)


def test_cancel_interrupts_rename_preflight_before_all_stats(tmp_path, monkeypatch):
    files = [tmp_path / f"a{i}.txt" for i in range(20)]
    for path in files:
        path.write_text("synthetic")
    cancelled = threading.Event()
    visited = []
    original_file = Path.is_file

    def stop_after_first_stat(path):
        visited.append(path)
        cancelled.set()
        return original_file(path)

    monkeypatch.setattr(Path, "is_file", stop_after_first_stat)
    result = FileRenameService().execute_rename_result(
        {path: path.with_name("done_" + path.name) for path in files}, cancelled.is_set
    )
    assert result.cancelled and not result.successful
    assert len(visited) == 1 and all(path.exists() for path in files)


def test_scan_parent_and_finished_queue_block_update(isolated, tmp_path, monkeypatch):
    page = FileRenamerDialog()
    source = tmp_path / "a.txt"
    source.write_text("synthetic")
    entered, release = threading.Event(), threading.Event()
    original_stat = Path.stat

    def held(path, *args, **kwargs):
        if path == source:
            entered.set()
            assert release.wait(5)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", held)
    page._queue_import([source], page._is_file_supported)
    owner = SimpleNamespace(
        _tab_attrs=("page",),
        page=page,
        _pending_update=UpdateCheckResult(UpdateCheckStatus.AVAILABLE, "9.9.9"),
        _download_request=None,
        _close_requested=False,
    )
    owner._running_business_workers = lambda: MainWindow._running_business_workers(owner)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    worker = page.worker
    try:
        until(entered.is_set)
        assert owner._running_business_workers() == [worker]
        MainWindow._start_download(owner)
        assert warnings and owner._download_request is None
        release.set()
        assert worker.wait(5000)
        # OS线程已退出但finished尚未消费时仍禁止更新/下一轮。
        assert page.worker is worker and worker in owner._running_business_workers()
        MainWindow._start_download(owner)
        assert len(warnings) == 2
        wait_page(page)
        assert page.worker is None and not owner._running_business_workers()
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)


def test_pdf_parameter_edit_reuses_metadata_and_model(isolated, tmp_path, monkeypatch):
    page = PDFGeneratorDialog()
    source = tmp_path / "a.pdf"
    source.write_text("synthetic")
    page.selected_files = [source]
    page._do_refresh_preview()
    wait_page(page)
    before = cell(page.ui.table_files, 0, 2)
    resets = []
    page.ui.table_files.model().modelReset.connect(lambda: resets.append(True))

    def unexpected_stat(*args, **kwargs):
        raise AssertionError("参数变更不得重新stat源文件")

    monkeypatch.setattr(Path, "stat", unexpected_stat)
    page.ui.radio_merge.setChecked(True)
    page.ui.edit_merge_filename.setText("new.pdf")
    page._do_refresh_preview()
    assert page.worker is None and not resets
    assert cell(page.ui.table_files, 0, 1) == "new.pdf"
    assert cell(page.ui.table_files, 0, 2) == before and before


def test_rename_close_waits_for_actual_write_and_preserves_success(isolated, tmp_path, monkeypatch):
    page = FileRenamerDialog()
    source = tmp_path / "a.txt"
    source.write_text("synthetic")
    page.selected_files = [source]
    page.operations = [{"type": "add_prefix", "params": {"text": "done_"}}]
    page._do_refresh_preview()
    wait_page(page)
    entered, release = threading.Event(), threading.Event()
    original = rename_execution.rename_no_replace

    def held(old, new):
        original(old, new)
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(rename_execution, "rename_no_replace", held)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args))
    page._execute()
    worker = page.worker
    try:
        until(entered.is_set)
        event = QCloseEvent()
        page.closeEvent(event)
        assert not event.isAccepted() and page._task.close_pending
        assert page.worker is worker and worker.isRunning()
        release.set()
        until(lambda: page.worker is None)
        assert source.with_name("done_a.txt").read_text() == "synthetic"
        assert not source.exists() and not messages
        assert len(page._history.get_records("rename")) == 1
        assert not page._import_pending
    finally:
        release.set()
        page._task.cancel()
        until(lambda: page.worker is None)


def test_scan_applies_one_model_notification_per_batch(isolated, tmp_path, monkeypatch, app):
    page = FileRenamerDialog()
    files = [tmp_path / f"a{i}.txt" for i in range(130)]
    for path in files:
        path.write_text("synthetic")
    entered, release = threading.Event(), threading.Event()
    original = Path.stat

    def held(path, *args, **kwargs):
        if path == files[64]:
            entered.set()
            assert release.wait(5)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", held)
    notifications = []
    page._file_model.rowsInserted.connect(
        lambda parent, first, last: notifications.append((first, last, QThread.currentThread()))
    )
    page._queue_import(files, page._is_file_supported)
    try:
        until(lambda: entered.is_set() and page._file_model.rowCount() == 64)
        assert notifications == [(0, 63, app.thread())]
        assert page._task.busy
        page._task.cancel()
        release.set()
        wait_page(page)
        assert page.selected_files == files[:64]
        assert notifications == [(0, 63, app.thread())]
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)


def test_invoice_explicit_paths_keep_duplicates_without_file_checks(
    isolated, tmp_path, monkeypatch
):
    page = InvoiceTab()
    path = tmp_path / "missing.unsupported"
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(path)] * 2, ""))

    def forbidden(*args, **kwargs):
        raise AssertionError("发票显式选择原本不查存在")

    monkeypatch.setattr(Path, "stat", forbidden)
    page._add_files()
    wait_page(page)
    assert page._files == [path, path]
    assert not page._import_errors


def test_plan_same_parent_avoids_resolve_but_alias_still_resolves(tmp_path, monkeypatch):
    source = tmp_path / "a.txt"
    source.write_text("synthetic")
    original = Path.resolve
    calls = []

    def record(path, *args, **kwargs):
        calls.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", record)
    target = tmp_path / "done.txt"
    assert rename_execution.plan_mapping({source: target})[source].state.value.startswith("✓")
    assert not calls
    alias = tmp_path / "nested"
    alias.mkdir()
    target_alias = alias / ".." / "done.txt"
    assert rename_execution.plan_mapping({source: target_alias})[source].state.value.startswith("✓")
    assert calls == [source.parent, target_alias.parent]


def test_rename_fallback_metadata_uses_one_stat_and_survives_refresh(
    isolated, tmp_path, monkeypatch
):
    source = tmp_path / "a.txt"
    source.write_text("synthetic")
    page = FileRenamerDialog()
    page.selected_files = [source]
    page.operations = [{"type": "add_prefix", "params": {"text": "done_"}}]
    original_stat = Path.stat
    original_plan = page._svc.plan_operations
    metadata_stats = []
    in_plan = threading.Event()

    def plan(*args, **kwargs):
        in_plan.set()
        try:
            return original_plan(*args, **kwargs)
        finally:
            in_plan.clear()

    def record(path, *args, **kwargs):
        if path == source and not in_plan.is_set():
            metadata_stats.append(QThread.currentThread())
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(page._svc, "plan_operations", plan)
    monkeypatch.setattr(Path, "stat", record)
    try:
        page._do_refresh_preview()
        wait_page(page)
        assert len(metadata_stats) == 1
        assert metadata_stats[0] != QApplication.instance().thread()
        assert cell(page.ui.table_preview, 0, 2) == "9 B"
        assert page._file_metadata[source].size == "9 B"
        page._do_refresh_preview()
        wait_page(page)
        assert len(metadata_stats) == 1
        assert cell(page.ui.table_preview, 0, 2) == "9 B"
    finally:
        page._task.cancel()
        wait_page(page)
        page.close()


def test_rename_preflight_cancel_does_not_start_another_preview(isolated, tmp_path, monkeypatch):
    source = tmp_path / "a.txt"
    source.write_text("synthetic")
    page = FileRenamerDialog()
    page.selected_files = [source]
    page.operations = [{"type": "add_prefix", "params": {"text": "done_"}}]
    page._do_refresh_preview()
    wait_page(page)
    entered, release = threading.Event(), threading.Event()
    original_plan = rename_execution.plan_mapping
    original_preview = RenamePreviewWorker.run
    preview_starts = []

    def held_plan(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original_plan(*args, **kwargs)

    def record_preview(worker):
        preview_starts.append(worker)
        original_preview(worker)

    monkeypatch.setattr(rename_execution, "plan_mapping", held_plan)
    monkeypatch.setattr(RenamePreviewWorker, "run", record_preview)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    try:
        page._execute()
        worker = page.worker
        assert isinstance(worker, RenameExecuteWorker)
        results = []
        worker.execute_ok.connect(results.append)
        until(entered.is_set)
        page._on_cancel()
        assert page.worker is worker and worker.isRunning()
        release.set()
        wait_page(page)
        settled = []
        QTimer.singleShot(250, lambda: settled.append(True))
        until(lambda: bool(settled))
        assert results[0].cancelled and not results[0].successful
        assert not preview_starts and page.worker is None
        assert page._preview_snapshot is None
        assert not page._preview_timer.isActive()
        assert page.selected_files == [source] and source.read_text() == "synthetic"
        assert not page._history.get_records("rename")
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)
        page.close()
