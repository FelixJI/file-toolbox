"""考勤 Tab 的配置、方案、预览门禁与另存编排测试。"""

import time
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QThread  # noqa: E402
from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from file_toolbox.core.attendance import (  # noqa: E402
    AttendancePlanStore,
    AttendancePreview,
    AttendanceResult,
)
from file_toolbox.gui.dialogs.attendance_tab import AttendanceTab  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(app, tmp_path):
    service = MagicMock()
    widget = AttendanceTab(
        service=service,
        plan_store=AttendancePlanStore(tmp_path / "plans.json"),
    )
    source = tmp_path / "source.xlsx"
    template = tmp_path / "template.xlsx"
    source.write_bytes(b"source")
    template.write_bytes(b"template")
    widget.ui.edit_source.setText(str(source))
    widget.ui.edit_template.setText(str(template))
    widget.ui.edit_output.setText(str(tmp_path / "out.xlsx"))
    widget.ui.spin_year.setValue(2026)
    widget.ui.spin_month.setValue(7)
    return widget


def test_defaults_match_given_workbooks(tab):
    plan = tab._build_plan()
    assert plan.source.sheet_name == "Sheet1"
    assert plan.source.name_start.address == "A2"
    assert plan.source.department_start.address == "C2"
    assert plan.source.detail_start.address == "G2"
    assert plan.target.detail_sheet == "出勤明细"
    assert plan.target.detail_matrix_start.address == "D7"
    assert plan.target.summary_sheet == "考勤汇总表"
    assert len(plan.rules) == 8


def test_plan_round_trip(tab):
    original = tab._build_plan()
    tab._plans.save(original)
    tab._refresh_plans(original.name)
    tab.ui.edit_source_sheet.setText("变更")

    tab._load_plan()

    assert tab._build_plan() == original
    assert tab.ui.btn_generate.isEnabled() is False


def test_preview_success_enables_generation(tab):
    preview = AttendancePreview(3, 31, 0, 1, {"√": 90, "空白": 3}, ())

    tab._on_preview_ok(preview)

    assert tab.ui.btn_generate.isEnabled() is True
    assert tab._preview_request == tab._build_request()
    assert "员工 3 人" in tab.ui.lbl_preview.text()
    assert "增加日期列 1" in tab.ui.lbl_preview.text()


def test_unmatched_preview_blocks_generation(tab):
    from file_toolbox.core.attendance import UnmatchedAttendance

    preview = AttendancePreview(
        1,
        31,
        0,
        1,
        {},
        (UnmatchedAttendance("张三", 2, "特殊状态"),),
    )

    tab._on_preview_ok(preview)

    assert tab.ui.btn_generate.isEnabled() is False
    assert tab.ui.table_unmatched.item(0, 0).text() == "张三"
    assert tab.ui.table_unmatched.item(0, 2).text() == "特殊状态"


def test_edit_after_preview_invalidates_generation(tab):
    tab._on_preview_ok(AttendancePreview(1, 31, 0, 1, {"√": 31}, ()))

    tab.ui.edit_source_sheet.setText("其他")

    assert tab._preview_request is None
    assert tab.ui.btn_generate.isEnabled() is False


def test_generate_uses_previewed_request(tab, monkeypatch):
    tab._on_preview_ok(AttendancePreview(1, 31, 0, 1, {"√": 31}, ()))
    calls = []
    monkeypatch.setattr(tab, "_start_worker", lambda request, mode: calls.append((request, mode)))

    tab._generate()

    assert len(calls) == 1
    assert calls[0][1] == "generate"
    assert calls[0][0].allow_overwrite is False


def test_generate_result_requires_new_preview(tab, monkeypatch):
    messages = []
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.attendance_tab.QMessageBox.information",
        lambda *args: messages.append(args),
    )
    result = AttendanceResult(
        tab._build_request().output_path,
        2,
        31,
        {"√": 62},
        ("结果已生成，但历史记录保存失败",),
    )

    tab._on_generate_ok(result)

    assert tab.ui.btn_generate.isEnabled() is False
    assert tab.ui.lbl_status.text() == "生成完成"
    assert messages
    assert "历史记录保存失败" in messages[0][2]


def test_delete_plan_write_failure_is_reported(tab, monkeypatch):
    tab.ui.cmb_plan.addItem("只读方案")
    tab.ui.cmb_plan.setCurrentText("只读方案")
    monkeypatch.setattr(tab._plans, "delete", MagicMock(side_effect=OSError("readonly")))
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.attendance_tab.QMessageBox.question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    errors = []
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.attendance_tab.QMessageBox.critical",
        lambda *args: errors.append(args),
    )

    tab._delete_plan()

    assert errors and "readonly" in errors[0][2]


def test_close_timeout_keeps_running_worker_until_finished(tab, monkeypatch):
    worker = MagicMock()
    worker.isRunning.return_value = True
    worker.wait.return_value = False
    tab._worker = worker
    event = QCloseEvent()

    tab.closeEvent(event)

    assert event.isAccepted() is False
    assert tab._worker is worker
    assert tab._close_pending is True
    worker.cancel.assert_called_once_with()
    worker.quit.assert_called_once_with()
    worker.wait.assert_called_once()

    owner = MagicMock()
    monkeypatch.setattr(tab, "window", lambda: owner)
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.attendance_tab.QTimer.singleShot",
        lambda _delay, callback: callback(),
    )
    tab._on_worker_finished()

    assert tab._worker is None
    owner.close.assert_called_once_with()


def test_worker_finished_cleanup_runs_on_gui_thread(tab, app, monkeypatch):
    """真实 QThread.finished 必须投递到 AttendanceTab 所在的 GUI 线程。"""
    tab._service.preview.return_value = AttendancePreview(1, 31, 0, 1, {"√": 31}, ())
    callback_threads = []
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.attendance_tab.QTimer.singleShot",
        lambda _delay, _callback: callback_threads.append(QThread.currentThread()),
    )
    tab._close_pending = True

    tab._start_worker(tab._build_request(), "preview")
    deadline = time.monotonic() + 3
    while tab._worker is not None and time.monotonic() < deadline:
        app.processEvents()

    assert tab._worker is None
    assert callback_threads == [app.thread()]
    tab._close_pending = False
