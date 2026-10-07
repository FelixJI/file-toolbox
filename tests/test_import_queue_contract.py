"""PR149:追加队列、业务成果、扫描取消与PDF预览交接。"""

import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from gui_model_helpers import cell, wait_page
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from test_file_import_contract import until

from file_toolbox.common.paths import GuiDataRootPolicy, use_data_root_policy
from file_toolbox.core.excel_merge import MergedSheet, MergeResult
from file_toolbox.core.invoice.types import ParseResult
from file_toolbox.core.pdf_sort import PagePlan, SortedFile, SortResult
from file_toolbox.gui.dialogs.excel_merge_tab import ExcelMergeTab
from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab
from file_toolbox.gui.dialogs.markdown_tab import MarkdownConvertTab
from file_toolbox.gui.dialogs.pdf_sort_tab import PdfSortTab
from file_toolbox.gui.dialogs.pdf_tab import PDFGeneratorDialog
from file_toolbox.gui.dialogs.rename_tab import FileRenamerDialog
from file_toolbox.gui.dialogs.replace_tab import ContentReplaceDialog
from file_toolbox.gui.workers.excel_merge_worker import ExcelMergeWorker
from file_toolbox.gui.workers.file_scan_worker import ScannedFile
from file_toolbox.gui.workers.invoice_worker import InvoiceParseWorker
from file_toolbox.gui.workers.pdf_sort_worker import PdfSortWorker

PAGES = [
    (FileRenamerDialog, ".txt"),
    (ContentReplaceDialog, ".txt"),
    (PDFGeneratorDialog, ".pdf"),
    (MarkdownConvertTab, ".md"),
    (InvoiceTab, ".xml"),
    (PdfSortTab, ".pdf"),
    (ExcelMergeTab, ".xlsx"),
]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated(app, tmp_path, monkeypatch):
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.StandardButton.Ok)
    with use_data_root_policy(GuiDataRootPolicy(tmp_path / "data")):
        yield


def supported(page):
    return page._is_file_supported if hasattr(page, "selected_files") else page._is_source


def settle():
    done = []
    QTimer.singleShot(250, lambda: done.append(True))
    until(lambda: bool(done))


@pytest.mark.parametrize("page_type,suffix", PAGES)
def test_append_requests_preserve_all_candidates_in_fifo(
    isolated, tmp_path, monkeypatch, page_type, suffix
):
    files = [tmp_path / f"file{i}{suffix}" for i in range(4)]
    for path in files:
        path.write_text("synthetic")
    entered, release = threading.Event(), threading.Event()
    original = Path.stat

    def held(path, *args, **kwargs):
        if path == files[0]:
            entered.set()
            assert release.wait(5)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", held)
    page = page_type()
    page._queue_import(files[:2], supported(page))
    first = page._task.worker
    try:
        until(entered.is_set)
        page._queue_import([files[2], files[0]], supported(page))
        page._queue_import([files[3]], supported(page))
        assert page._task.worker is first and not first.isInterruptionRequested()
        release.set()
        wait_page(page)
        assert page._file_model.files == files
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)
        page.close()


@pytest.mark.parametrize("page_type,suffix", PAGES)
def test_scan_button_cancel_discards_queue_and_never_restarts_preview(
    isolated, tmp_path, monkeypatch, page_type, suffix
):
    files = [tmp_path / f"file{i}{suffix}" for i in range(66)]
    for path in files:
        path.write_text("synthetic")
    entered, release = threading.Event(), threading.Event()
    original = Path.stat
    previews = []
    if hasattr(page_type, "_do_refresh_preview"):
        monkeypatch.setattr(page_type, "_do_refresh_preview", lambda self: previews.append(True))

    def held(path, *args, **kwargs):
        if path == files[64]:
            entered.set()
            assert release.wait(5)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", held)
    page = page_type()
    page._queue_import(files[:65], supported(page))
    try:
        until(lambda: entered.is_set() and page._file_model.rowCount() == 64)
        page._queue_import([files[65]], supported(page))
        if isinstance(page, MarkdownConvertTab):
            page.ui.btn_cancel.click()
        elif hasattr(page, "_scan_cancel"):
            page._scan_cancel.click()
        else:
            page.ui.btn_cancel.click()
        release.set()
        wait_page(page)
        settle()
        assert page._file_model.files == files[:64]
        assert not previews and not page._import_pending
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)
        page.close()


@pytest.mark.parametrize(
    "page_type,worker_type,suffix,start",
    [
        (ExcelMergeTab, ExcelMergeWorker, ".xlsx", "_merge"),
        (PdfSortTab, PdfSortWorker, ".pdf", "_sort"),
        (InvoiceTab, InvoiceParseWorker, ".xml", "_parse"),
    ],
)
@pytest.mark.parametrize("failure", [False, True])
def test_queued_empty_and_valid_import_preserve_running_business_results(
    isolated, tmp_path, monkeypatch, page_type, worker_type, suffix, start, failure
):
    source, added = [tmp_path / f"{name}{suffix}" for name in ("source", "added")]
    for path in (source, added):
        path.write_text("synthetic")
    empty = tmp_path / "empty"
    empty.mkdir()
    entered, deliver, finish = threading.Event(), threading.Event(), threading.Event()
    page = page_type()
    page._file_model.replace_paths([source])
    if isinstance(page, PdfSortTab):
        page.ui.edit_pattern.setText(r"(\d+)")
    page.ui.edit_outdir.setText(str(tmp_path / "output"))
    if isinstance(page, ExcelMergeTab):
        result = MergeResult(sheets=[MergedSheet(source.name, "sheet", "merged")], cancelled=True)
    elif isinstance(page, PdfSortTab):
        result = SortResult(
            sorted_files=[SortedFile(source.name, None, [PagePlan(0, "1", True, 0)])],
            cancelled=True,
        )
    else:
        result = ParseResult(invoices=[])
    seen = []

    def held(worker):
        entered.set()
        assert deliver.wait(5)
        if failure:
            worker.failed.emit("synthetic failure")
        else:
            worker.finished_ok.emit(result)
        assert finish.wait(5)

    monkeypatch.setattr(worker_type, "run", held)
    getattr(page, start)()
    worker = page._task.worker
    worker.failed.connect(lambda *_: seen.append(True))
    worker.finished_ok.connect(lambda *_: seen.append(True))
    try:
        until(entered.is_set)
        page._queue_import([], supported(page), empty)
        page._queue_import([added], supported(page))
        # 取消业务仍必须接收已完成的部分成果；扫描只能在真实finished后开始。
        page._task.cancel()
        deliver.set()
        until(lambda: bool(seen))
        assert page._task.worker is worker and page._file_model.files == [source]
        if failure:
            assert "失败" in page.ui.lbl_status.text()
        elif isinstance(page, InvoiceTab):
            assert page._result is result and "解析中" not in page.ui.lbl_status.text()
        else:
            assert page.ui.table.model().rowCount() == 1
        finish.set()
        wait_page(page)
        assert page._file_model.files == [source, added]
    finally:
        deliver.set()
        finish.set()
        page._task.cancel()
        wait_page(page)
        page.close()


@pytest.mark.parametrize("request_refresh", [False, True])
def test_pdf_slow_append_resets_old_results_with_or_without_pending_refresh(
    isolated, tmp_path, monkeypatch, request_refresh
):
    old, failed, added = [tmp_path / f"{name}.pdf" for name in ("old", "failed", "added")]
    for path in (old, failed, added):
        path.write_text("synthetic")
    page = PDFGeneratorDialog()
    page.selected_files = [old, failed]
    page._file_metadata.update({path: ScannedFile(path, "9 B") for path in (old, failed)})
    page._do_refresh_preview()
    page._render_results(
        [
            {"source": old, "output": old, "success": True, "error": ""},
            {"source": failed, "output": failed, "success": False, "error": "synthetic"},
        ]
    )
    entered, release = threading.Event(), threading.Event()
    original = Path.stat
    stats = []

    def held(path, *args, **kwargs):
        stats.append(path)
        if path == added:
            entered.set()
            assert release.wait(5)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", held)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(added)], ""))
    page._on_select_files()
    try:
        until(entered.is_set)
        page.ui.radio_merge.setChecked(True)
        page.ui.edit_merge_filename.setText("latest.pdf")
        # 这些配置控件原本没有自动刷新连接；另一分支验证实际用户刷新按钮。
        if request_refresh:
            page.ui.btn_refresh.click()
            assert page._pdf_preview_pending
        settle()
        assert page._task.busy
        release.set()
        wait_page(page)
        assert [cell(page.ui.table_files, row, 3) for row in range(3)] == ["待转换"] * 3
        assert [cell(page.ui.table_files, row, 1) for row in range(3)] == ["latest.pdf"] * 3
        assert stats == [added]
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)
        page.close()


def test_append_cohort_keeps_first_auto_preview_request(isolated, tmp_path, monkeypatch):
    files = [tmp_path / f"file{i}.txt" for i in range(2)]
    for path in files:
        path.write_text("synthetic")
    entered, release = threading.Event(), threading.Event()
    original = Path.stat
    previews = []
    monkeypatch.setattr(
        FileRenamerDialog, "_do_refresh_preview", lambda self: previews.append(True)
    )

    def held(path, *args, **kwargs):
        if path == files[0]:
            entered.set()
            assert release.wait(5)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", held)
    page = FileRenamerDialog()
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(files[0])], ""))
    page._select_files(auto_preview=True)
    try:
        until(entered.is_set)
        monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(files[1])], ""))
        page._select_files(auto_preview=False)
        release.set()
        wait_page(page)
        assert page.selected_files == files and previews == [True]
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)
        page.close()


def test_scan_cancel_survives_native_interrupt_flag_reset(isolated, tmp_path, monkeypatch):
    files = [tmp_path / f"file{i}.txt" for i in range(65)]
    for path in files:
        path.write_text("synthetic")
    entered, release = threading.Event(), threading.Event()
    original = Path.stat
    previews = []
    monkeypatch.setattr(
        FileRenamerDialog, "_do_refresh_preview", lambda self: previews.append(True)
    )

    def held(path, *args, **kwargs):
        if path == files[64]:
            entered.set()
            assert release.wait(5)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", held)
    page = FileRenamerDialog()
    page._queue_import(files, page._is_file_supported)
    worker = page.worker
    try:
        until(lambda: entered.is_set() and page._file_model.rowCount() == 64)
        page._task.cancel()
        assert worker.isInterruptionRequested()
        release.set()
        assert worker.wait(5000)
        # OS线程已结束、GUI尚未消费finished时，Qt原生中断标志已复位。
        assert not worker.isInterruptionRequested()
        assert worker.cancel_requested and page.worker is worker
        wait_page(page)
        settle()
        assert page.selected_files == files[:64] and not previews
    finally:
        release.set()
        page._task.cancel()
        wait_page(page)
        page.close()
