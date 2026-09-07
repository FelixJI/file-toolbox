"""Excel COM adapter 的错误路径与名单模式写出编排测试，不启动真实 Excel。"""

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_toolbox.core.attendance.excel import (
    BASE_DATE_COLUMNS,
    MAX_EMPLOYEES,
    ExcelComAdapter,
    _cell_text,
    _overtime_value,
    _prepare_group_sheets,
    _release_excel,
    _write_column,
    _write_mapping,
    _write_overtime_hours,
    _write_symbols,
)
from file_toolbox.core.attendance.types import (
    AttendancePlan,
    AttendancePreview,
    CellRef,
    EmployeeAttendance,
    GroupSheetConfig,
    PreparedAttendance,
    PreparedGroup,
    RosterConfig,
    RosterLayout,
    SourceAttendance,
    SourceLayout,
    TargetLayout,
)


def _plan(**overrides) -> AttendancePlan:
    base = AttendancePlan(
        name="市场部",
        template_path=Path("template.xlsx"),
        source=SourceLayout(
            "Sheet1", CellRef.parse("A2"), CellRef.parse("C2"), CellRef.parse("G2")
        ),
        target=TargetLayout(
            "出勤明细", CellRef.parse("C7"), CellRef.parse("D7"), "考勤汇总表", CellRef.parse("C8")
        ),
    )
    return replace(base, **overrides)


def _cell(*, value=None, formula="", merged=False):
    cell = MagicMock()
    cell.Value = value
    cell.Formula = formula
    cell.MergeCells = merged
    cell.MergeArea.Row = 1
    cell.MergeArea.Column = 1
    return cell


def _patch_excel(monkeypatch, workbook):
    app = MagicMock()
    app.Workbooks.Open.return_value = workbook
    monkeypatch.setattr(
        "file_toolbox.core.attendance.excel.init_isolated_office_app", lambda prog_id: app
    )
    return app


def _sheet_with_values(values: dict) -> MagicMock:
    sheet = MagicMock()
    sheet.Cells.side_effect = lambda row, col: _cell(value=values.get((row, col)))
    return sheet


def _roster_plan(configs: tuple[GroupSheetConfig, ...], **overrides) -> AttendancePlan:
    return _plan(
        split_by_group=True,
        roster=RosterConfig(
            Path("roster.xlsx"),
            RosterLayout(
                "Sheet1",
                CellRef.parse("A1"),
                CellRef.parse("B1"),
                CellRef.parse("C1"),
                CellRef.parse("D1"),
            ),
            **overrides,
        ),
        group_sheet_configs=configs,
    )


# --- validate_template ---


def test_validate_template_reports_half_missing_roster_pair(monkeypatch, tmp_path):
    detail = MagicMock()
    detail.Name = "出勤明细"
    detail.Cells.return_value = _cell(value=1)
    summary = MagicMock()
    summary.Name = "考勤汇总表"
    summary.Cells.return_value = _cell(formula='=COUNTIF(出勤明细!D7:AG7,"√")')
    workbook = MagicMock()
    workbook.Worksheets.Count = 2
    workbook.Worksheets.side_effect = {
        1: detail,
        2: summary,
        "出勤明细": detail,
        "考勤汇总表": summary,
    }.__getitem__
    _patch_excel(monkeypatch, workbook)
    plan = _roster_plan((GroupSheetConfig("徐州中车", "出勤明细-劳务", "考勤汇总表", "正式"),))

    with pytest.raises(ValueError, match="模板缺少工作表: 出勤明细-劳务"):
        ExcelComAdapter().validate_template(tmp_path / "template.xlsx", plan)


def test_validate_template_repeats_pair_only_once_and_rejects_non_formula(monkeypatch, tmp_path):
    detail = MagicMock()
    detail.Name = "出勤明细"
    detail.Cells.return_value = _cell(value=1)
    summary = MagicMock()
    summary.Name = "考勤汇总表"
    summary.Cells.return_value = _cell(formula=42)
    workbook = MagicMock()
    workbook.Worksheets.Count = 2
    workbook.Worksheets.side_effect = {
        1: detail,
        2: summary,
        "出勤明细": detail,
        "考勤汇总表": summary,
    }.__getitem__
    _patch_excel(monkeypatch, workbook)
    # 配置与基准目标同名(仅大小写不同):重复 pair 去重,不会重复访问结构单元格。
    plan = _roster_plan((GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表", "正式"),))

    with pytest.raises(ValueError, match="汇总区域结构不符"):
        ExcelComAdapter().validate_template(tmp_path / "template.xlsx", plan)

    assert summary.Cells.call_count == 1


# --- read_source / read_roster 错误与边界 ---


def test_read_source_requires_three_overtime_columns_before_detail(monkeypatch, tmp_path):
    plan = _plan(
        source=SourceLayout("Sheet1", CellRef.parse("A2"), CellRef.parse("C2"), CellRef.parse("C2"))
    )
    workbook = MagicMock()
    workbook.Worksheets.return_value = _sheet_with_values({(2, 1): "张三"})
    _patch_excel(monkeypatch, workbook)

    with pytest.raises(ValueError, match="三列"):
        ExcelComAdapter().read_source(tmp_path / "source.xlsx", plan.source, 1)


def test_read_source_rejects_employee_overflow(monkeypatch, tmp_path):
    workbook = MagicMock()
    workbook.Worksheets.return_value = _sheet_with_values(
        {(row, 1): f"员工{row}" for row in range(2, MAX_EMPLOYEES + 3)}
    )
    _patch_excel(monkeypatch, workbook)

    with pytest.raises(ValueError, match=f"安全上限 {MAX_EMPLOYEES}"):
        ExcelComAdapter().read_source(tmp_path / "source.xlsx", _plan().source, 1)


def test_read_source_rejects_empty_name_column(monkeypatch, tmp_path):
    workbook = MagicMock()
    workbook.Worksheets.return_value = _sheet_with_values({})
    _patch_excel(monkeypatch, workbook)

    with pytest.raises(ValueError, match="未读取到员工姓名"):
        ExcelComAdapter().read_source(tmp_path / "source.xlsx", _plan().source, 1)


def test_read_source_cancel_check_interrupts(monkeypatch, tmp_path):
    workbook = MagicMock()
    workbook.Worksheets.return_value = _sheet_with_values({(2, 1): "张三", (2, 7): "正常"})
    _patch_excel(monkeypatch, workbook)

    with pytest.raises(InterruptedError, match="操作已取消"):
        ExcelComAdapter().read_source(
            tmp_path / "source.xlsx", _plan().source, 1, cancel_check=lambda: True
        )


def test_read_source_overtime_normalizes_bool_and_unknown_values(monkeypatch, tmp_path):
    unknown = MagicMock(name="非基础类型值")
    values = {
        (2, 1): "张三",
        (2, 4): True,
        (2, 5): unknown,
        (2, 6): 1.5,
        (2, 7): "正常",
        (3, 1): "",
    }
    workbook = MagicMock()
    workbook.Worksheets.return_value = _sheet_with_values(values)
    _patch_excel(monkeypatch, workbook)

    source = ExcelComAdapter().read_source(tmp_path / "source.xlsx", _plan().source, 1)

    assert source.employees[0].overtime_hours == ("True", str(unknown), 1.5)


def test_read_roster_rejects_overflow(monkeypatch, tmp_path):
    layout = RosterLayout(
        "Sheet1",
        CellRef.parse("A1"),
        CellRef.parse("B1"),
        CellRef.parse("C1"),
        CellRef.parse("D1"),
    )
    rows = MAX_EMPLOYEES + 2
    values = {
        (row, col): {1: "徐州中车", 2: "市场部", 3: f"员工{row}", 4: f"{row:04d}"}[col]
        for row in range(1, rows + 1)
        for col in (1, 2, 3, 4)
    }
    sheet = _sheet_with_values(values)
    sheet.UsedRange.Row = 1
    sheet.UsedRange.Rows.Count = rows
    workbook = MagicMock()
    workbook.Worksheets.return_value = sheet
    _patch_excel(monkeypatch, workbook)

    with pytest.raises(ValueError, match=f"安全上限 {MAX_EMPLOYEES}"):
        ExcelComAdapter().read_roster(tmp_path / "roster.xlsx", layout)


def test_read_roster_rejects_empty_roster(monkeypatch, tmp_path):
    layout = RosterLayout(
        "Sheet1",
        CellRef.parse("A1"),
        CellRef.parse("B1"),
        CellRef.parse("C1"),
        CellRef.parse("D1"),
    )
    sheet = _sheet_with_values({})
    sheet.UsedRange.Row = 1
    sheet.UsedRange.Rows.Count = 2
    workbook = MagicMock()
    workbook.Worksheets.return_value = sheet
    _patch_excel(monkeypatch, workbook)

    with pytest.raises(ValueError, match="未读取到有效人员"):
        ExcelComAdapter().read_roster(tmp_path / "roster.xlsx", layout)


# --- write_output ---


def test_write_output_rejects_readonly_staging(monkeypatch, tmp_path):
    workbook = MagicMock()
    workbook.ReadOnly = True
    _patch_excel(monkeypatch, workbook)
    source = SourceAttendance((EmployeeAttendance("张三", "市场部", ("正常",) * 30),), "市场部")
    prepared = PreparedAttendance(
        groups=(PreparedGroup("", source, (("√",) * 30,), "出勤明细", "考勤汇总表", ()),),
        preview=AttendancePreview(1, 30, 0, 0, {}, ()),
        global_mapping_values=(),
    )

    with pytest.raises(ValueError, match="只读"):
        ExcelComAdapter().write_output(tmp_path / "staging.xlsx", _plan(), prepared)


def test_write_output_roster_mode_removes_stale_pairs_orders_and_fills_ids(monkeypatch, tmp_path):
    """名单模式写出编排:删除空分组 Sheet、按名单序排布、序号/工号以文本写入。"""
    plan = _roster_plan(
        (
            GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表"),
            GroupSheetConfig("盛世金源", "出勤明细-劳务", "考勤汇总表-劳务"),
        ),
        fill_serial_numbers=True,
        fill_employee_ids=True,
        detail_serial_start=CellRef.parse("B7"),
        summary_serial_start=CellRef.parse("B8"),
        detail_employee_id_start=CellRef.parse("A7"),
        summary_employee_id_start=CellRef.parse("A8"),
    )
    detail = MagicMock()
    detail.Name = "出勤明细"
    detail.Index = 5
    detail.Cells.side_effect = lambda row, col: _cell()
    summary = MagicMock()
    summary.Name = "考勤汇总表"
    summary.Index = 6
    summary.Cells.side_effect = lambda row, col: _cell(formula='=COUNTIF(出勤明细!$D$7:$AG$7,"√")')
    labor_detail = MagicMock()
    labor_detail.Name = "出勤明细-劳务"
    labor_detail.Index = 1
    labor_detail.Cells.side_effect = lambda row, col: _cell()
    labor_summary = MagicMock()
    labor_summary.Name = "考勤汇总表-劳务"
    labor_summary.Index = 2
    labor_summary.Cells.side_effect = lambda row, col: _cell(
        formula="=COUNTIF('出勤明细-劳务'!$D$7:$AG$7,\"√\")"
    )
    stale_detail = MagicMock()
    stale_detail.Name = "出勤明细-外包"
    stale_summary = MagicMock()
    stale_summary.Name = "考勤汇总表-外包"
    workbook = MagicMock()
    workbook.ReadOnly = False
    workbook.Worksheets.Count = 6
    workbook.Worksheets.side_effect = {
        1: labor_detail,
        2: labor_summary,
        3: stale_detail,
        4: stale_summary,
        5: detail,
        6: summary,
        "出勤明细": detail,
        "考勤汇总表": summary,
        "出勤明细-劳务": labor_detail,
        "考勤汇总表-劳务": labor_summary,
        "出勤明细-外包": stale_detail,
        "考勤汇总表-外包": stale_summary,
    }.__getitem__
    app = _patch_excel(monkeypatch, workbook)
    employees = (
        EmployeeAttendance("张三", "市场部", ("正常",) * 30, "徐州中车", employee_id="001"),
        EmployeeAttendance("李四", "市场部", ("正常",) * 30, "盛世金源", employee_id="wb002"),
    )
    prepared = PreparedAttendance(
        groups=(
            PreparedGroup(
                "徐州中车",
                SourceAttendance(employees[:1], "市场部"),
                (("√",) * 30,),
                "出勤明细",
                "考勤汇总表",
                (),
            ),
            PreparedGroup(
                "盛世金源",
                SourceAttendance(employees[1:], "市场部"),
                (("√",) * 30,),
                "出勤明细-劳务",
                "考勤汇总表-劳务",
                (),
            ),
        ),
        preview=AttendancePreview(2, BASE_DATE_COLUMNS, 0, 0, {}, ()),
        global_mapping_values=(("考勤汇总表", CellRef.parse("A2"), "2026年7月"),),
        remove_sheet_pairs=(("出勤明细-外包", "考勤汇总表-外包"),),
        roster_mode=True,
    )

    ExcelComAdapter().write_output(tmp_path / "staging.xlsx", plan, prepared)

    stale_summary.Delete.assert_called_once_with()
    stale_detail.Delete.assert_called_once_with()
    for sheet in (detail, summary, labor_detail, labor_summary):
        sheet.Move.assert_called_once()
    app.CalculateFullRebuild.assert_called_once_with()
    workbook.Save.assert_called_once_with()
    # 每张分组表都写入了文本格式的工号列(序号列为数值,工号列随后覆盖为 "@")。
    for sheet in (detail, summary, labor_detail, labor_summary):
        assert sheet.Range.return_value.NumberFormat == "@"


def test_prepare_group_sheets_rejects_half_existing_pair_in_roster_mode():
    plan = _roster_plan(())
    detail = MagicMock()
    detail.Name = "出勤明细"
    summary = MagicMock()
    summary.Name = "考勤汇总表"
    workbook = MagicMock()
    workbook.Worksheets.Count = 2
    workbook.Worksheets.side_effect = {
        1: detail,
        2: summary,
        "出勤明细": detail,
        "考勤汇总表": summary,
    }.__getitem__
    source = SourceAttendance((EmployeeAttendance("张三", "市场部", ("正常",)),), "市场部")
    group = PreparedGroup("售后组", source, (("√",),), "出勤明细", "考勤汇总表-售后组", ())

    with pytest.raises(ValueError, match="模板分组工作表不完整，缺少: 考勤汇总表-售后组"):
        _prepare_group_sheets(workbook, plan, (group,))


def test_write_group_rejects_mapping_target_outside_group_sheets(monkeypatch, tmp_path):
    plan = _plan()
    detail = MagicMock()
    detail.Cells.side_effect = lambda row, col: _cell()
    summary = MagicMock()
    summary.Cells.side_effect = lambda row, col: _cell(formula='=COUNTIF(出勤明细!$D$7:$AG$7,"√")')
    workbook = MagicMock()
    workbook.ReadOnly = False
    workbook.Worksheets.side_effect = {
        "出勤明细": detail,
        "考勤汇总表": summary,
        "封面": MagicMock(),
    }.__getitem__
    _patch_excel(monkeypatch, workbook)
    source = SourceAttendance((EmployeeAttendance("张三", "市场部", ("正常",) * 30),), "市场部")
    prepared = PreparedAttendance(
        groups=(
            PreparedGroup(
                "",
                source,
                (("√",) * 30,),
                "出勤明细",
                "考勤汇总表",
                (("封面", CellRef.parse("A1"), "标题"),),
            ),
        ),
        preview=AttendancePreview(1, 30, 0, 0, {}, ()),
        global_mapping_values=(),
    )

    with pytest.raises(ValueError, match="分组映射目标工作表无效: 封面"):
        ExcelComAdapter().write_output(tmp_path / "staging.xlsx", plan, prepared)


def test_write_output_operation_and_cleanup_failure_combine(monkeypatch, tmp_path):
    workbook = MagicMock()
    workbook.Worksheets.side_effect = KeyError("出勤明细")
    workbook.Close.side_effect = RuntimeError("close failed")
    _patch_excel(monkeypatch, workbook)
    source = SourceAttendance((EmployeeAttendance("张三", "市场部", ("正常",) * 30),), "市场部")
    prepared = PreparedAttendance(
        groups=(PreparedGroup("", source, (("√",) * 30,), "出勤明细", "考勤汇总表", ()),),
        preview=AttendancePreview(1, 30, 0, 0, {}, ()),
        global_mapping_values=(),
    )

    with pytest.raises(RuntimeError, match="close failed"):
        ExcelComAdapter().write_output(tmp_path / "staging.xlsx", _plan(), prepared)


# --- 写入 helper 的防御分支 ---


def test_write_mapping_rejects_merged_cell_without_topleft():
    sheet = MagicMock()
    cell = _cell(merged=True)
    cell.MergeArea.Row = 8
    cell.MergeArea.Column = 4
    sheet.Cells.return_value = cell

    with pytest.raises(ValueError, match="合并单元格只能配置左上角"):
        _write_mapping(sheet, CellRef.parse("C7"), "值")


def test_release_excel_reports_workbook_close_failure_without_app():
    workbook = MagicMock()
    workbook.Close.side_effect = RuntimeError("close failed")

    error = _release_excel(workbook, None)

    assert isinstance(error, RuntimeError)
    assert "关闭工作簿失败" in str(error)


def test_empty_inputs_skip_range_writes():
    sheet = MagicMock()

    _write_overtime_hours(sheet, CellRef.parse("P8"), SourceAttendance((), ""))
    _write_column(sheet, CellRef.parse("B7"), ())
    _write_symbols(sheet, CellRef.parse("D7"), ())

    sheet.Range.assert_not_called()


def test_cell_text_and_overtime_value_normalization():
    assert _cell_text(None) == ""
    assert _cell_text(3.5) == "3.5"
    assert _overtime_value(None) == ""
    assert _overtime_value(True) == "True"
    assert _overtime_value(1.5) == 1.5
    sentinel = object()
    assert _overtime_value(sentinel) == str(sentinel)
