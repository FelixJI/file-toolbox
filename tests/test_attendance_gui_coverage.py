"""考勤 Tab 的方案保存/删除、输入校验、生成门禁与预览渲染边界测试。"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QMessageBox,
    QTableWidgetItem,
)

from file_toolbox.core.attendance import (  # noqa: E402
    AttendancePlanStore,
    AttendancePreview,
    CellMapping,
    CellRef,
    EmployeeGroupPreview,
    UnmatchedAttendance,
)
from file_toolbox.gui.dialogs.attendance_tab import AttendanceTab  # noqa: E402

_MODULE = "file_toolbox.gui.dialogs.attendance_tab"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(app, tmp_path):
    widget = AttendanceTab(
        service=MagicMock(),
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


@pytest.fixture
def warnings(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(f"{_MODULE}.QMessageBox.warning", lambda *args: calls.append(args))
    return calls


@pytest.fixture
def criticals(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(f"{_MODULE}.QMessageBox.critical", lambda *args: calls.append(args))
    return calls


# --- 文件浏览与模式切换 ---


def test_browse_source_template_and_roster_fill_edits(tab, monkeypatch, tmp_path):
    picked = iter(
        [
            (str(tmp_path / "考勤源.xlsx"), ""),
            (str(tmp_path / "模板.xlsx"), ""),
            (str(tmp_path / "名单.xlsx"), ""),
        ]
    )
    monkeypatch.setattr(f"{_MODULE}.QFileDialog.getOpenFileName", lambda *args: next(picked))

    tab._browse_source()
    tab._browse_template()
    tab.ui.chk_roster_enabled.setChecked(True)
    tab._browse_roster()

    assert tab.ui.edit_source.text().endswith("考勤源.xlsx")
    assert tab.ui.edit_template.text().endswith("模板.xlsx")
    assert tab.ui.edit_roster.text().endswith("名单.xlsx")


def test_browse_output_cancelled_keeps_state(tab, monkeypatch):
    monkeypatch.setattr(f"{_MODULE}.QFileDialog.getExistingDirectory", lambda *args: "")
    tab.ui.edit_output_dir.setText("旧目录")

    tab._browse_output()

    assert tab.ui.edit_output_dir.text() == "旧目录"


def test_roster_toggle_off_reenables_group_controls(tab):
    tab.ui.chk_roster_enabled.setChecked(True)
    assert tab.ui.edit_roster.isEnabled() is True

    tab.ui.chk_roster_enabled.setChecked(False)

    assert tab.ui.chk_roster_enabled.isChecked() is False
    assert tab.ui.edit_roster.isEnabled() is False
    assert tab.ui.chk_split_groups.isEnabled() is True


def test_roster_mode_forces_split_groups(tab):
    tab.ui.chk_split_groups.setChecked(False)
    tab.ui.chk_roster_enabled.setChecked(True)

    assert tab.ui.chk_split_groups.isChecked() is True


# --- 方案加载/保存/删除 ---


def test_load_plan_without_selection_warns(tab, warnings):
    tab._load_plan()

    assert any("请选择已保存的方案" in call[2] for call in warnings)


def test_save_plan_persists_and_selects(tab):
    tab._save_plan()

    plan = tab._build_plan()
    assert [item.name for item in tab._plans.list()] == [plan.name]
    assert tab.ui.cmb_plan.currentText() == plan.name
    assert "已保存方案" in tab.ui.lbl_status.text()


def test_save_plan_invalid_input_warns_without_saving(tab, warnings):
    tab.ui.edit_plan_name.clear()

    tab._save_plan()

    assert any("方案名称不能为空" in call[2] for call in warnings)
    assert tab._plans.list() == []


def test_save_plan_overwrite_declined_keeps_original(tab, monkeypatch):
    original = tab._build_plan()
    tab._plans.save(original)
    tab.ui.edit_detail_sheet.setText("改名后明细")
    monkeypatch.setattr(
        f"{_MODULE}.QMessageBox.question",
        lambda *args: QMessageBox.StandardButton.No,
    )

    tab._save_plan()

    assert [item.name for item in tab._plans.list()] == [original.name]
    assert tab._plans.get(original.name) == original


def test_save_plan_overwrite_confirmed_replaces(tab, monkeypatch):
    original = tab._build_plan()
    tab._plans.save(original)
    tab.ui.edit_detail_sheet.setText("改名后明细")
    monkeypatch.setattr(
        f"{_MODULE}.QMessageBox.question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )

    tab._save_plan()

    assert tab._plans.get(original.name).target.detail_sheet == "改名后明细"


def test_save_plan_store_failure_is_critical(tab, monkeypatch, criticals):
    monkeypatch.setattr(tab._plans, "save", MagicMock(side_effect=OSError("readonly 文件")))

    tab._save_plan()

    assert any("保存方案失败" in call[1] and "readonly 文件" in call[2] for call in criticals)


def test_delete_plan_without_selection_is_noop(tab, monkeypatch):
    tab.ui.cmb_plan.clear()
    monkeypatch.setattr(
        f"{_MODULE}.QMessageBox.question",
        lambda *args: (_ for _ in ()).throw(AssertionError("不应弹出删除确认")),
    )
    status_before = tab.ui.lbl_status.text()

    tab._delete_plan()

    assert tab.ui.lbl_status.text() == status_before


def test_delete_plan_declined_keeps_plan(tab, monkeypatch):
    plan = tab._build_plan()
    tab._plans.save(plan)
    tab._refresh_plans(plan.name)
    monkeypatch.setattr(
        f"{_MODULE}.QMessageBox.question",
        lambda *args: QMessageBox.StandardButton.No,
    )

    tab._delete_plan()

    assert [item.name for item in tab._plans.list()] == [plan.name]


def test_delete_plan_confirmed_removes_and_refreshes(tab, monkeypatch):
    plan = tab._build_plan()
    tab._plans.save(plan)
    tab._refresh_plans(plan.name)
    monkeypatch.setattr(
        f"{_MODULE}.QMessageBox.question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )

    tab._delete_plan()

    assert tab._plans.list() == []
    assert "已删除方案" in tab.ui.lbl_status.text()


# --- 构建 plan/request 的输入校验 ---


def test_build_plan_requires_template(tab):
    tab.ui.edit_template.clear()

    with pytest.raises(ValueError, match="请选择汇总模板"):
        tab._build_plan()


def test_build_request_requires_source_dir_and_name(tab):
    source = tab.ui.edit_source.text()
    tab.ui.edit_source.clear()
    with pytest.raises(ValueError, match="请选择原始考勤"):
        tab._build_request()
    tab.ui.edit_source.setText(source)

    tab.ui.edit_output_dir.clear()
    with pytest.raises(ValueError, match="请选择结果保存目录"):
        tab._build_request()
    tab.ui.edit_output_dir.setText(source and str(Path(source).parent))

    tab.ui.edit_output_name.clear()
    with pytest.raises(ValueError, match="请指定结果文件名"):
        tab._build_request()


def test_roster_fields_are_required_in_build(tab, tmp_path):
    tab.ui.chk_roster_enabled.setChecked(True)
    tab.ui.edit_roster.clear()

    with pytest.raises(ValueError, match="人员名单不能为空"):
        tab._build_plan()


def test_mappings_skip_fully_blank_rows(tab):
    tab._add_mapping()
    tab.ui.table_mappings.item(0, 1).setText("")

    assert tab._build_plan().mappings == ()


def test_rules_reject_blank_pattern_and_empty_table(tab):
    tab.ui.table_rules.setRowCount(0)
    tab._add_rule()

    with pytest.raises(ValueError, match="正则不能为空"):
        tab._build_plan()

    tab.ui.table_rules.setRowCount(0)

    with pytest.raises(ValueError, match="至少需要一条判定规则"):
        tab._build_plan()


# --- 映射表选择器 ---


def test_mapping_selector_resolves_summary_and_detail_roles(tab):
    tab._set_mappings(
        (
            CellMapping("考勤汇总表", CellRef.parse("A1"), "汇总标题"),
            CellMapping("出勤明细", CellRef.parse("B2"), "明细标题"),
        )
    )

    assert tab._mapping_sheet_name(0) == "考勤汇总表"
    assert tab._mapping_sheet_name(1) == "出勤明细"
    assert [mapping.sheet_name for mapping in tab._build_plan().mappings] == [
        "考勤汇总表",
        "出勤明细",
    ]


def test_mapping_sheet_name_falls_back_to_plain_text_widget(tab):
    tab._add_mapping()
    tab.ui.table_mappings.setCellWidget(0, 0, QLabel("遗留 Sheet"))
    tab.ui.table_mappings.setItem(0, 0, QTableWidgetItem("遗留 Sheet"))
    tab.ui.table_mappings.item(0, 1).setText("C3")
    tab.ui.table_mappings.item(0, 2).setText("内容")
    tab.ui.edit_detail_sheet.setText("改名明细")

    assert tab._mapping_sheet_name(0) == "遗留 Sheet"
    assert tab._build_plan().mappings[0].sheet_name == "遗留 Sheet"


# --- 规则表编辑操作 ---


def test_add_and_remove_selected_rule_rows(tab):
    before = tab.ui.table_rules.rowCount()

    tab.ui.table_rules.selectRow(0)
    tab._remove_selected(tab.ui.table_rules)

    assert tab.ui.table_rules.rowCount() == before - 1
    assert tab.ui.btn_generate.isEnabled() is False


def test_move_rule_swaps_adjacent_rows(tab):
    first_pattern = tab.ui.table_rules.item(0, 1).text()
    second_pattern = tab.ui.table_rules.item(1, 1).text()

    tab.ui.table_rules.setCurrentCell(0, 1)
    tab._move_rule(1)

    assert tab.ui.table_rules.item(0, 1).text() == second_pattern
    assert tab.ui.table_rules.item(1, 1).text() == first_pattern

    tab.ui.table_rules.setCurrentCell(0, 1)
    tab._move_rule(-1)  # 已在首行,越界不动
    last = tab.ui.table_rules.rowCount() - 1
    tab.ui.table_rules.setCurrentCell(last, 1)
    tab._move_rule(1)  # 已在末行,越界不动

    assert tab.ui.table_rules.item(0, 1).text() == second_pattern
    assert tab.ui.table_rules.item(1, 1).text() == first_pattern


# --- 预览调整捕获 ---


def test_same_name_same_group_conflicting_targets_are_rejected(tab, warnings):
    preview = AttendancePreview(
        2,
        31,
        0,
        1,
        {"√": 62},
        (),
        {"C组": 2},
        {"C组": ("C组明细", "C组汇总")},
        (
            EmployeeGroupPreview("张三", "A组", "B组"),
            EmployeeGroupPreview("张三", "A组", "C组"),
        ),
    )
    tab._on_preview_ok(preview)
    tab.ui.table_employee_preview.item(0, 2).setText("B组")
    tab.ui.table_employee_preview.item(1, 2).setText("C组")

    tab._apply_preview_adjustments()

    assert any("存在不同调整" in call[2] for call in warnings)


def test_roster_capture_exclusions_without_group_rows(tab, tmp_path):
    tab.ui.chk_roster_enabled.setChecked(True)
    tab.ui.edit_roster.setText(str(tmp_path / "roster.xlsx"))
    tab._configure_preview_tables(True)
    tab.ui.table_employee_preview.setRowCount(1)
    export_item = QTableWidgetItem()
    export_item.setFlags(
        Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
    )
    export_item.setCheckState(Qt.CheckState.Unchecked)
    tab.ui.table_employee_preview.setItem(0, 0, export_item)
    for column, value in enumerate(("wb001", "张三", "市场部", "徐州中车", "正式"), start=1):
        tab.ui.table_employee_preview.setItem(0, column, QTableWidgetItem(value))

    tab._capture_preview_adjustments()

    plan = tab._build_plan()
    assert plan.roster is not None
    assert plan.roster.excluded_employee_ids == ("wb001",)
    assert plan.group_sheet_configs == ()


def test_apply_adjustments_without_preview_rows_is_noop(tab, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_preview", lambda: calls.append(True))
    tab.ui.chk_split_groups.setChecked(False)

    tab._apply_preview_adjustments()

    assert calls == []


# --- 预览/生成门禁 ---


def test_preview_with_invalid_config_warns_without_worker(tab, warnings, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_start_worker", lambda *args: calls.append(args))
    tab.ui.edit_source.clear()

    tab._preview()

    assert any("请选择原始考勤" in call[2] for call in warnings)
    assert calls == []


def test_preview_valid_config_starts_worker(tab, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_start_worker", lambda request, mode: calls.append((request, mode)))

    tab._preview()

    assert len(calls) == 1 and calls[0][1] == "preview"


def test_generate_with_invalid_config_warns(tab, warnings, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_start_worker", lambda *args: calls.append(args))
    tab.ui.edit_output_name.clear()

    tab._generate()

    assert any("请指定结果文件名" in call[2] for call in warnings)
    assert calls == []


def test_generate_requires_fresh_preview(tab, warnings, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_start_worker", lambda *args: calls.append(args))
    tab._on_preview_ok(AttendancePreview(1, 31, 0, 1, {"√": 31}, ()))
    tab.ui.edit_source_sheet.setText("变更后的源 Sheet")

    tab._generate()

    assert any("配置已变化" in call[2] for call in warnings)
    assert calls == []


def test_generate_existing_output_declined_keeps_file(tab, monkeypatch):
    output = tab._build_request().output_path
    output.write_bytes(b"existing")
    tab._on_preview_ok(AttendancePreview(1, 31, 0, 1, {"√": 31}, ()))
    calls = []
    monkeypatch.setattr(tab, "_start_worker", lambda *args: calls.append(args))
    monkeypatch.setattr(
        f"{_MODULE}.QMessageBox.question",
        lambda *args: QMessageBox.StandardButton.No,
    )

    tab._generate()

    assert calls == []
    assert output.read_bytes() == b"existing"


def test_generate_existing_output_confirmed_requests_overwrite(tab, monkeypatch):
    output = tab._build_request().output_path
    output.write_bytes(b"existing")
    tab._on_preview_ok(AttendancePreview(1, 31, 0, 1, {"√": 31}, ()))
    calls = []
    monkeypatch.setattr(tab, "_start_worker", lambda request, mode: calls.append((request, mode)))
    monkeypatch.setattr(
        f"{_MODULE}.QMessageBox.question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )

    tab._generate()

    assert len(calls) == 1
    assert calls[0][0].allow_overwrite is True


def test_start_worker_ignores_second_request_while_busy(tab):
    tab._worker = MagicMock(name="运行中 worker")

    tab._start_worker(tab._build_request(), "preview")

    assert tab.ui.btn_preview.isEnabled() is True  # 未进入 busy 态
    assert tab._preview_request is None


def test_on_preview_ok_rejects_non_preview_payload(tab, criticals):
    tab._on_preview_ok({"不是": "预览结果"})

    assert any("预览返回了无效结果" in call[2] for call in criticals)


def test_on_preview_ok_rebuild_failure_fails_gracefully(tab, criticals):
    tab._on_preview_ok(AttendancePreview(1, 31, 0, 1, {"√": 31}, ()))
    tab.ui.edit_source.clear()

    tab._on_preview_ok(AttendancePreview(1, 31, 0, 1, {"√": 31}, ()))

    assert any("请选择原始考勤" in call[2] for call in criticals)


def test_on_generate_ok_rejects_non_result_payload(tab, criticals):
    tab._on_generate_ok("bad")

    assert any("生成返回了无效结果" in call[2] for call in criticals)


def test_on_failed_disables_generation_and_reports(tab, criticals):
    tab.ui.btn_generate.setEnabled(True)

    tab._on_failed("Excel 崩溃")

    assert tab.ui.btn_generate.isEnabled() is False
    assert tab.ui.lbl_status.text() == "操作失败"
    assert any("Excel 崩溃" in call[2] for call in criticals)


def test_on_worker_finished_without_worker_is_noop(tab):
    tab._worker = None

    tab._on_worker_finished()  # 不应抛异常


# --- 预览渲染边界 ---


def test_preview_label_truncates_long_error_and_warning_lists(tab):
    preview = AttendancePreview(
        1,
        31,
        0,
        1,
        {},
        (),
        errors=("错误一", "错误二", "错误三", "错误四"),
        warnings=("警告一", "警告二", "警告三", "警告四"),
    )

    tab._on_preview_ok(preview)

    text = tab.ui.lbl_preview.text()
    assert "错误一" in text and "另 1 项" in text
    assert "警告一" in text and text.count("另 1 项") == 2


def test_preview_status_appends_overflow_unmatched_entries(tab):
    unmatched = tuple(
        UnmatchedAttendance("张三", day, f"异常{day}", "售后组") for day in range(1, 5)
    )
    preview = AttendancePreview(
        1,
        31,
        0,
        1,
        {},
        unmatched,
        {"售后组": 1},
        {"售后组": ("售后明细", "售后汇总")},
        (EmployeeGroupPreview("张三", "售后组", "售后组"),),
    )

    tab._on_preview_ok(preview)

    status = tab.ui.table_employee_preview.item(0, 3).text()
    assert "1日: 异常1" in status and "另 1 条" in status


def test_roster_preview_employee_status_includes_unmatched(tab, tmp_path):
    roster_path = tmp_path / "roster.xlsx"
    roster_path.write_bytes(b"roster")
    preview = AttendancePreview(
        1,
        31,
        0,
        1,
        {},
        (UnmatchedAttendance("张三", 2, "特殊状态", "徐州中车", "徐州中车"),),
        {"徐州中车": 1},
        {"徐州中车": ("出勤明细", "考勤汇总表")},
        (
            EmployeeGroupPreview(
                "张三", "徐州中车", "徐州中车", "001", "市场部", "正式", True, "已匹配"
            ),
        ),
        roster_path=roster_path,
    )

    tab._on_preview_ok(preview)

    status = tab.ui.table_employee_preview.item(0, 6).text()
    assert "未识别：2日: 特殊状态" in status


# --- 关闭路径 ---


def test_close_event_with_finished_worker_proceeds(tab):
    from PySide6.QtGui import QCloseEvent

    worker = MagicMock()
    worker.isRunning.return_value = False
    tab._worker = worker
    event = QCloseEvent()

    tab.closeEvent(event)

    assert event.isAccepted() is True
