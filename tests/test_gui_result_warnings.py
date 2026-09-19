"""#109:真实文件、worker.start() 和 Qt 投递中的附属保存失败。"""

from unittest.mock import Mock

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMessageBox

from file_toolbox.common import settings
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.gui.dialogs import excel_merge_tab, pdf_sort_tab
from file_toolbox.gui.workers.excel_merge_worker import ExcelMergeWorker
from file_toolbox.gui.workers.pdf_sort_worker import PdfSortWorker


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def messages(app, monkeypatch):
    received = []

    def capture(kind):
        def record(parent, title, text):
            assert QThread.currentThread() == app.thread()
            received.append((kind, title, text))

        return record

    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, kind, capture(kind))
    return received


def observe_start(monkeypatch, worker_type):
    results, failures = [], []
    start = worker_type.start

    def start_observed(worker):
        worker.finished_ok.connect(results.append)
        worker.failed.connect(failures.append)
        start(worker)  # 仍运行真实 QThread,观察者必须在线程启动前连接。

    monkeypatch.setattr(worker_type, "start", start_observed)
    return results, failures


def finish(worker, app):
    # 持有真实 worker 至 finished,不把 Tab 提前清空引用当作线程结束。
    assert worker is not None
    assert worker.wait(10000), "worker 未正常结束"
    app.processEvents()
    app.processEvents()


@pytest.mark.parametrize(
    "history_fails,preference_fails", [(True, False), (False, True), (True, True), (False, False)]
)
def test_excel_real_worker_keeps_result_and_independent_warnings(
    app, messages, make_xlsx, tmp_path, monkeypatch, history_fails, preference_fails
):
    history = JsonHistoryStore(tmp_path / "history")
    add_record = Mock(wraps=history.add_record)
    if history_fails:
        add_record.side_effect = PermissionError("history denied")
    monkeypatch.setattr(history, "add_record", add_record)
    monkeypatch.setattr(excel_merge_tab, "JsonHistoryStore", lambda: history)
    monkeypatch.setattr(settings, "_settings_path", lambda: tmp_path / "settings.json")
    save_preference = Mock(wraps=settings.set)
    if preference_fails:
        save_preference.side_effect = OSError("preference denied")
    monkeypatch.setattr(settings, "set", save_preference)
    source = make_xlsx("source.xlsx", {"Data": [["payload"]]})
    original = source.read_bytes()
    bad = tmp_path / "broken.xlsx"
    bad.write_bytes(b"not a workbook")
    tab = excel_merge_tab.ExcelMergeTab()
    tab._add_paths([source, bad])
    tab.ui.edit_outdir.setText(str(tmp_path / "outputs"))
    merge = Mock(wraps=tab._svc.merge)
    monkeypatch.setattr(tab._svc, "merge", merge)

    results, failures = observe_start(monkeypatch, ExcelMergeWorker)
    tab._merge()
    worker = tab._worker
    finish(worker, app)

    outputs = list((tmp_path / "outputs").glob("*.xlsx"))
    assert len(outputs) == 1
    assert len(results) == 1 and results[0].output == outputs[0]
    assert failures == []
    assert len(results[0].sheets) == 1 and len(results[0].failed) == 1
    workbook = load_workbook(outputs[0])
    try:
        assert workbook["source-Data"]["A1"].value == "payload"
    finally:
        workbook.close()
    assert source.read_bytes() == original
    assert tab.ui.table.rowCount() == 2
    assert str(outputs[0]) in tab.ui.lbl_status.text()
    assert tab.ui.btn_merge.isEnabled()
    assert [(kind, title) for kind, title, _ in messages] == [
        ("information", "合并完成"),
        *([("warning", "偏好保存失败")] if preference_fails else []),
        *([("warning", "历史保存失败")] if history_fails else []),
    ]
    assert ("history denied" in str(messages)) is history_fails
    assert ("preference denied" in str(messages)) is preference_fails
    assert merge.call_count == add_record.call_count == save_preference.call_count == 1
    assert len(history.get_records("excel_merge")) == (0 if history_fails else 1)
    tab.close()


@pytest.mark.parametrize("cancelled", [False, True])
def test_pdf_real_worker_keeps_outputs_when_preference_fails(
    app, messages, make_text_pdf, tmp_path, monkeypatch, cancelled
):
    history = JsonHistoryStore(tmp_path / "history")
    monkeypatch.setattr(pdf_sort_tab, "JsonHistoryStore", lambda: history)
    monkeypatch.setattr(settings, "_settings_path", lambda: tmp_path / "settings.json")
    save_preference = Mock(side_effect=OSError("preference denied"))
    monkeypatch.setattr(settings, "set", save_preference)
    source = make_text_pdf("source.pdf", ["NO.2", "NO.1"])
    second = make_text_pdf("second.pdf", ["NO.4", "NO.3"])
    original = source.read_bytes()
    tab = pdf_sort_tab.PdfSortTab()
    tab._add_paths([source, second])
    tab.ui.edit_pattern.setText(r"NO\.(\d+)")
    tab.ui.edit_outdir.setText(str(tmp_path / "outputs"))
    sort = tab._svc.sort

    def run(*args, **kwargs):
        if cancelled:
            checks = iter([False, True])
            kwargs["cancel_check"] = lambda: next(checks)
        return sort(*args, **kwargs)

    execute = Mock(side_effect=run)
    monkeypatch.setattr(tab._svc, "sort", execute)
    results, failures = observe_start(monkeypatch, PdfSortWorker)
    tab._sort()
    worker = tab._worker
    finish(worker, app)

    assert failures == []
    assert len(results) == 1 and results[0].cancelled is cancelled
    outputs = [item.output for item in results[0].sorted_files]
    assert len(outputs) == (1 if cancelled else 2)
    with outputs[0].open("rb") as stream:
        assert "NO.1" in PdfReader(stream).pages[0].extract_text()
    assert source.read_bytes() == original
    assert tab.ui.table.rowCount() == (2 if cancelled else 4)
    assert [(kind, title) for kind, title, _ in messages] == [
        ("warning", "排序已取消") if cancelled else ("information", "排序完成"),
        ("warning", "偏好保存失败"),
    ]
    if cancelled:
        assert str(outputs[0]) in messages[0][2]
        assert not (tmp_path / "outputs" / "second_排序.pdf").exists()
    assert "preference denied" in messages[1][2]
    assert execute.call_count == save_preference.call_count == 1
    assert tab.ui.btn_sort.isEnabled()
    assert history.get_records("pdf_sort")[0]["data"]["outputs"] == [str(p) for p in outputs]
    tab.close()


@pytest.mark.parametrize("unexpected_error", [False, True])
def test_excel_real_worker_business_failure_is_not_reported_as_saved(
    app, messages, tmp_path, monkeypatch, unexpected_error
):
    history = JsonHistoryStore(tmp_path / "history")
    monkeypatch.setattr(excel_merge_tab, "JsonHistoryStore", lambda: history)
    monkeypatch.setattr(settings, "_settings_path", lambda: tmp_path / "settings.json")
    save_preference = Mock()
    monkeypatch.setattr(settings, "set", save_preference)
    source = tmp_path / "broken.xlsx"
    source.write_bytes(b"broken workbook")
    tab = excel_merge_tab.ExcelMergeTab()
    tab._add_paths([source])
    tab.ui.edit_outdir.setText(str(tmp_path / "outputs"))
    if unexpected_error:
        merge = Mock(side_effect=RuntimeError("business failed"))
    else:
        merge = Mock(wraps=tab._svc.merge)
    monkeypatch.setattr(tab._svc, "merge", merge)
    results, failures = observe_start(monkeypatch, ExcelMergeWorker)

    tab._merge()
    finish(tab._worker, app)

    assert merge.call_count == 1
    assert save_preference.call_count == 0
    assert history.get_records("excel_merge") == []
    assert not (tmp_path / "outputs").exists()
    assert tab.ui.btn_merge.isEnabled()
    if unexpected_error:
        assert results == [] and failures == ["business failed"]
        assert messages == [("critical", "合并失败", "business failed")]
    else:
        assert failures == [] and len(results) == 1 and not results[0].success
        assert tab.ui.table.rowCount() == 1
        assert [(kind, title) for kind, title, _ in messages] == [("warning", "未生成输出")]
    tab.close()
