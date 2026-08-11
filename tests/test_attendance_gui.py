"""考勤 Tab 的配置、方案、预览门禁与另存编排测试。"""

import time
from dataclasses import replace
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
    CellMapping,
    CellRef,
    EmployeeGroupOverride,
    EmployeeGroupPreview,
    GroupSheetConfig,
    UnmatchedAttendance,
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
    widget.ui.edit_output_dir.setText(str(tmp_path))
    widget.ui.edit_output_name.setText("out.xlsx")
    widget.ui.spin_year.setValue(2026)
    widget.ui.spin_month.setValue(7)
    return widget


def test_defaults_match_given_workbooks(tab):
    plan = tab._build_plan()
    assert plan.source.sheet_name == "Sheet1"
    assert plan.source.name_start.address == "A2"
    assert plan.source.department_start.address == "C2"
    assert plan.source.attendance_group_start is not None
    assert plan.source.attendance_group_start.address == "B2"
    assert plan.source.detail_start.address == "G2"
    assert plan.split_by_group is True
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


def test_group_preview_shows_sheet_pairs(tab):
    preview = AttendancePreview(
        3,
        31,
        0,
        1,
        {"√": 90},
        (),
        {"售后组": 2, "管理组": 1},
        {
            "售后组": ("出勤明细-售后组", "考勤汇总表-售后组"),
            "管理组": ("出勤明细-管理组", "考勤汇总表-管理组"),
        },
        (
            EmployeeGroupPreview("张三", "售后组", "售后组"),
            EmployeeGroupPreview("李四", "售后组", "售后组"),
            EmployeeGroupPreview("王五", "管理组", "管理组"),
        ),
    )

    tab._on_preview_ok(preview)

    assert "售后组 2 人→出勤明细-售后组/考勤汇总表-售后组" in tab.ui.lbl_preview.text()
    assert tab.ui.table_group_preview.rowCount() == 2
    assert tab.ui.table_group_preview.item(0, 2).text() == "出勤明细-售后组"
    assert tab.ui.table_employee_preview.rowCount() == 3
    assert tab.ui.table_employee_preview.item(0, 0).text() == "张三"


def test_unmatched_preview_blocks_generation(tab):
    preview = AttendancePreview(
        1,
        31,
        0,
        1,
        {},
        (UnmatchedAttendance("张三", 2, "特殊状态", "售后组"),),
        {"售后组": 1},
        {"售后组": ("售后明细", "售后汇总")},
        (EmployeeGroupPreview("张三", "售后组", "售后组"),),
    )

    tab._on_preview_ok(preview)

    assert tab.ui.btn_generate.isEnabled() is False
    assert tab.ui.table_employee_preview.item(0, 0).text() == "张三"
    assert tab.ui.table_employee_preview.item(0, 2).text() == "售后组"
    assert "2日: 特殊状态" in tab.ui.table_employee_preview.item(0, 3).text()


def test_unmatched_preview_shows_attendance_group(tab):
    preview = AttendancePreview(
        1,
        31,
        0,
        1,
        {},
        (UnmatchedAttendance("张三", 2, "特殊状态", "售后组"),),
        {"售后组": 1},
        {"售后组": ("售后明细", "售后汇总")},
        (EmployeeGroupPreview("张三", "原组", "售后组"),),
    )

    tab._on_preview_ok(preview)

    assert tab.ui.table_employee_preview.item(0, 1).text() == "原组"
    assert tab.ui.table_employee_preview.item(0, 2).text() == "售后组"


def test_unmatched_preview_keeps_same_name_moves_separate(tab):
    preview = AttendancePreview(
        2,
        31,
        0,
        1,
        {},
        (
            UnmatchedAttendance("张三", 2, "A组异常", "C组", "A组"),
            UnmatchedAttendance("张三", 3, "B组异常", "C组", "B组"),
        ),
        {"C组": 2},
        {"C组": ("C组明细", "C组汇总")},
        (
            EmployeeGroupPreview("张三", "A组", "C组"),
            EmployeeGroupPreview("张三", "B组", "C组"),
        ),
    )

    tab._on_preview_ok(preview)

    assert "A组异常" in tab.ui.table_employee_preview.item(0, 3).text()
    assert "B组异常" not in tab.ui.table_employee_preview.item(0, 3).text()
    assert "B组异常" in tab.ui.table_employee_preview.item(1, 3).text()
    assert "A组异常" not in tab.ui.table_employee_preview.item(1, 3).text()


def test_preview_edits_apply_employee_move_and_sheet_names(tab, monkeypatch):
    preview = AttendancePreview(
        2,
        31,
        0,
        1,
        {"√": 62},
        (),
        {"售后组": 1, "管理组": 1},
        {
            "售后组": ("售后明细", "售后汇总"),
            "管理组": ("管理明细", "管理汇总"),
        },
        (
            EmployeeGroupPreview("张三", "售后组", "售后组"),
            EmployeeGroupPreview("李四", "管理组", "管理组"),
        ),
    )
    tab._on_preview_ok(preview)
    calls = []
    monkeypatch.setattr(tab, "_preview", lambda: calls.append(True))

    tab.ui.table_group_preview.item(0, 2).setText("自定义售后明细")
    tab.ui.table_employee_preview.item(0, 2).setText("管理组")

    assert tab.ui.btn_generate.isEnabled() is False
    assert "请应用" in tab.ui.lbl_status.text()
    tab._apply_preview_adjustments()

    plan = tab._build_plan()
    assert calls == [True]
    assert plan.employee_group_overrides == (EmployeeGroupOverride("张三", "售后组", "管理组"),)
    assert plan.group_sheet_configs[0] == GroupSheetConfig("售后组", "自定义售后明细", "售后汇总")


def test_plan_load_restores_saved_preview_adjustments(tab):
    original = replace(
        tab._build_plan(),
        employee_group_overrides=(EmployeeGroupOverride("张三", "售后组", "管理组"),),
        group_sheet_configs=(GroupSheetConfig("管理组", "管理明细", "管理汇总"),),
    )
    tab._plans.save(original)
    tab._refresh_plans(original.name)

    tab._load_plan()

    restored = tab._build_plan()
    assert restored.employee_group_overrides == original.employee_group_overrides
    assert restored.group_sheet_configs == original.group_sheet_configs
    assert tab.ui.table_employee_preview.rowCount() == 0


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


def test_output_picker_selects_directory_and_generates_editable_filename(
    tab, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.attendance_tab.QFileDialog.getExistingDirectory",
        lambda *args: str(tmp_path),
    )
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.attendance_tab.QFileDialog.getSaveFileName",
        lambda *args: (_ for _ in ()).throw(AssertionError("不应选择尚未生成的具体文件")),
    )
    tab.ui.edit_plan_name.setText("市场部")
    tab.ui.spin_year.setValue(2026)
    tab.ui.spin_month.setValue(7)
    tab.ui.edit_output_name.clear()

    tab._browse_output()

    assert tab.ui.edit_output_dir.text() == str(tmp_path)
    assert tab.ui.edit_output_name.text() == "市场部-2026年07月考勤汇总.xlsx"
    assert tab._build_request().output_path == tmp_path / "市场部-2026年07月考勤汇总.xlsx"


def test_output_picker_preserves_custom_filename(tab, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.attendance_tab.QFileDialog.getExistingDirectory",
        lambda *args: str(tmp_path),
    )
    tab.ui.edit_output_name.setText("自定义名称.xlsx")

    tab._browse_output()

    assert tab.ui.edit_output_name.text() == "自定义名称.xlsx"


def test_custom_output_filename_is_normalized_and_rejects_paths(tab, tmp_path):
    tab.ui.edit_output_dir.setText(str(tmp_path))
    tab.ui.edit_output_name.setText("自定义结果.xls")

    assert tab._build_request().output_path == tmp_path / "自定义结果.xlsx"

    tab.ui.edit_output_name.setText("子目录/结果.xlsx")
    with pytest.raises(ValueError, match="不能包含路径"):
        tab._build_request()


def test_fixed_mapping_sheet_uses_controlled_target_selector(tab):
    tab._add_mapping()

    selector = tab.ui.table_mappings.cellWidget(0, 0)

    assert selector is not None
    assert [selector.itemText(index) for index in range(selector.count())] == [
        "出勤明细",
        "考勤汇总表",
    ]


def test_fixed_mapping_selector_follows_target_sheet_rename(tab):
    tab._add_mapping()
    selector = tab.ui.table_mappings.cellWidget(0, 0)
    selector.setCurrentIndex(1)
    tab.ui.table_mappings.item(0, 1).setText("A1")
    tab.ui.table_mappings.item(0, 2).setText("{{month}}月")

    tab.ui.edit_summary_sheet.setText("自定义汇总基准")

    assert selector.currentText() == "自定义汇总基准"
    assert tab._build_plan().mappings == (
        CellMapping("自定义汇总基准", CellRef.parse("A1"), "{{month}}月"),
    )


def test_fixed_mapping_selector_preserves_legacy_sheet_from_saved_plan(tab):
    tab._set_mappings((CellMapping("封面", CellRef.parse("B2"), "{{month_start}}"),))

    selector = tab.ui.table_mappings.cellWidget(0, 0)

    assert [selector.itemText(index) for index in range(selector.count())] == [
        "出勤明细",
        "考勤汇总表",
        "封面",
    ]
    assert selector.currentText() == "封面"
    assert tab._build_plan().mappings[0].sheet_name == "封面"
