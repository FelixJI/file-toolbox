"""Microsoft Excel COM adapter 控制流测试，不启动真实 Excel。"""

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_toolbox.core.attendance.excel import (
    ExcelComAdapter,
    _copy_worksheet,
    _prepare_group_sheets,
)
from file_toolbox.core.attendance.types import (
    AttendancePlan,
    AttendancePreview,
    CellMapping,
    CellRef,
    EmployeeAttendance,
    PreparedAttendance,
    PreparedGroup,
    SourceAttendance,
    SourceLayout,
    TargetLayout,
)


def _plan() -> AttendancePlan:
    return AttendancePlan(
        name="市场部",
        template_path=Path("template.xlsx"),
        source=SourceLayout(
            "Sheet1", CellRef.parse("A2"), CellRef.parse("C2"), CellRef.parse("G2")
        ),
        target=TargetLayout(
            "出勤明细", CellRef.parse("C7"), CellRef.parse("D7"), "考勤汇总表", CellRef.parse("C8")
        ),
        mappings=(CellMapping("出勤明细", CellRef.parse("A3"), "x"),),
    )


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


def _prepared(
    source: SourceAttendance,
    symbols: tuple[tuple[str, ...], ...],
    day_count: int,
    mappings: tuple[tuple[str, CellRef, str], ...] = (),
) -> PreparedAttendance:
    return PreparedAttendance(
        groups=(
            PreparedGroup(
                "",
                source,
                symbols,
                "出勤明细",
                "考勤汇总表",
                mappings,
            ),
        ),
        preview=AttendancePreview(
            len(source.employees),
            day_count,
            max(0, len(source.employees) - 15),
            day_count - 30,
            {},
            (),
        ),
        global_mapping_values=(),
    )


def test_validate_template_checks_target_sheets_and_formula(monkeypatch, tmp_path):
    plan = _plan()
    detail = MagicMock()
    summary = MagicMock()
    detail.Cells.return_value = _cell(value=1)
    summary.Cells.return_value = _cell(formula='=COUNTIF(出勤明细!D7:AG7,"√")')
    workbook = MagicMock()
    sheets = {"出勤明细": detail, "考勤汇总表": summary, 1: detail, 2: summary}
    detail.Name = "出勤明细"
    summary.Name = "考勤汇总表"
    workbook.Worksheets.Count = 2
    workbook.Worksheets.side_effect = sheets.__getitem__
    app = _patch_excel(monkeypatch, workbook)

    ExcelComAdapter().validate_template(tmp_path / "template.xlsx", plan)

    app.Workbooks.Open.assert_called_once()
    workbook.Close.assert_called_once_with(SaveChanges=False)
    app.Quit.assert_called_once_with()


def test_validate_template_rejects_wrong_date_header(monkeypatch, tmp_path):
    plan = _plan()
    detail = MagicMock()
    summary = MagicMock()
    detail.Cells.return_value = _cell(value="日期")
    summary.Cells.return_value = _cell(formula="=COUNTIF(A1:A2,1)")
    workbook = MagicMock()
    workbook.Worksheets.side_effect = {"出勤明细": detail, "考勤汇总表": summary}.__getitem__
    _patch_excel(monkeypatch, workbook)

    with pytest.raises(ValueError, match="日期区域"):
        ExcelComAdapter().validate_template(tmp_path / "template.xlsx", plan)
    workbook.Close.assert_called_once_with(SaveChanges=False)


def test_read_source_uses_configured_offsets_and_stops_at_blank_name(monkeypatch, tmp_path):
    plan = replace(
        _plan(),
        source=replace(_plan().source, attendance_group_start=CellRef.parse("B2")),
    )
    values = {
        (2, 1): "张三",
        (2, 2): "售后组",
        (2, 3): "市场部",
        (2, 7): "正常",
        (2, 8): "出差",
        (3, 1): "",
    }
    sheet = MagicMock()
    sheet.Cells.side_effect = lambda row, col: _cell(value=values.get((row, col)))
    workbook = MagicMock()
    workbook.Worksheets.return_value = sheet
    app = _patch_excel(monkeypatch, workbook)

    source = ExcelComAdapter().read_source(tmp_path / "source.xlsx", plan.source, 2)

    assert source.department == "市场部"
    assert source.employees[0].records == ("正常", "出差")
    assert source.employees[0].attendance_group == "售后组"
    workbook.Worksheets.assert_called_once_with("Sheet1")
    workbook.Close.assert_called_once_with(SaveChanges=False)
    app.Quit.assert_called_once_with()


def test_read_source_rejects_multiple_departments(monkeypatch, tmp_path):
    plan = _plan()
    values = {(2, 1): "张三", (2, 3): "A", (3, 1): "李四", (3, 3): "B", (4, 1): ""}
    sheet = MagicMock()
    sheet.Cells.side_effect = lambda row, col: _cell(value=values.get((row, col)))
    workbook = MagicMock()
    workbook.Worksheets.return_value = sheet
    _patch_excel(monkeypatch, workbook)

    with pytest.raises(ValueError, match="多个部门"):
        ExcelComAdapter().read_source(tmp_path / "source.xlsx", plan.source, 1)


@pytest.mark.parametrize(
    ("day_count", "column", "method", "calls"), [(31, 33, "Insert", 1), (28, 32, "Delete", 2)]
)
def test_write_output_adjusts_columns_rows_and_saves(
    monkeypatch, tmp_path, day_count, column, method, calls
):
    plan = _plan()
    detail = MagicMock()
    summary = MagicMock()
    detail_cells = {}
    summary_cells = {}
    detail.Cells.side_effect = lambda row, col: detail_cells.setdefault((row, col), _cell())

    def summary_cell(row, col):
        formula = f'=COUNTIF(出勤明细!D7:{"AH" if day_count == 31 else "AE"}7,"√")'
        return summary_cells.setdefault((row, col), _cell(formula=formula))

    summary.Cells.side_effect = summary_cell
    column_mocks = {}
    detail.Columns.side_effect = lambda index: column_mocks.setdefault(index, MagicMock())
    detail.Rows.side_effect = lambda index: MagicMock()
    summary.Rows.side_effect = lambda index: MagicMock()
    workbook = MagicMock()
    workbook.ReadOnly = False
    workbook.Worksheets.side_effect = {"出勤明细": detail, "考勤汇总表": summary}.__getitem__
    app = _patch_excel(monkeypatch, workbook)
    source = SourceAttendance(
        tuple(
            EmployeeAttendance(f"张三{i}", "市场部", tuple("正常" for _ in range(day_count)))
            for i in range(16)
        ),
        "市场部",
    )
    symbols = tuple(tuple("√" for _ in range(day_count)) for _ in range(16))

    prepared = _prepared(
        source,
        symbols,
        day_count,
        (("出勤明细", CellRef.parse("A3"), "标题"),),
    )
    ExcelComAdapter().write_output(tmp_path / "staging.xlsx", plan, prepared)

    target_method = getattr(column_mocks[column], method)
    assert target_method.call_count == calls
    detail.Rows.assert_any_call(22)
    summary.Rows.assert_any_call(23)
    assert detail_cells[(3, 1)].Value == "标题"
    app.CalculateFullRebuild.assert_called_once_with()
    workbook.Save.assert_called_once_with()
    workbook.Close.assert_called_once_with(SaveChanges=False)
    app.Quit.assert_called_once_with()


def test_write_output_save_failure_still_closes_excel(monkeypatch, tmp_path):
    plan = _plan()
    detail = MagicMock()
    summary = MagicMock()
    detail.Cells.side_effect = lambda row, col: _cell()
    summary.Cells.side_effect = lambda row, col: _cell(formula='=COUNTIF(出勤明细!D7:AG7,"√")')
    workbook = MagicMock()
    workbook.ReadOnly = False
    workbook.Worksheets.side_effect = {"出勤明细": detail, "考勤汇总表": summary}.__getitem__
    workbook.Save.side_effect = RuntimeError("save failed")
    app = _patch_excel(monkeypatch, workbook)
    source = SourceAttendance(
        (EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(30))),), "市场部"
    )

    with pytest.raises(RuntimeError, match="save failed"):
        ExcelComAdapter().write_output(
            tmp_path / "staging.xlsx",
            plan,
            _prepared(source, (tuple("√" for _ in range(30)),), 30),
        )

    workbook.Close.assert_called_once_with(SaveChanges=False)
    app.Quit.assert_called_once_with()


@pytest.mark.parametrize(
    ("failure_target", "message"), [("close", "关闭工作簿"), ("quit", "关闭 Office")]
)
def test_write_output_cleanup_failure_is_propagated(monkeypatch, tmp_path, failure_target, message):
    plan = _plan()
    detail = MagicMock()
    summary = MagicMock()
    detail.Cells.side_effect = lambda row, col: _cell()
    summary.Cells.side_effect = lambda row, col: _cell(formula='=COUNTIF(出勤明细!$D$7:$AG$7,"√")')
    workbook = MagicMock()
    workbook.ReadOnly = False
    workbook.Worksheets.side_effect = {"出勤明细": detail, "考勤汇总表": summary}.__getitem__
    app = _patch_excel(monkeypatch, workbook)
    if failure_target == "close":
        workbook.Close.side_effect = RuntimeError("close failed")
    else:
        app.Quit.side_effect = RuntimeError("quit failed")
    source = SourceAttendance(
        (EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(30))),), "市场部"
    )

    with pytest.raises(RuntimeError, match=message):
        ExcelComAdapter().write_output(
            tmp_path / "staging.xlsx",
            plan,
            _prepared(source, (tuple("√" for _ in range(30)),), 30),
        )

    workbook.Save.assert_called_once_with()
    workbook.Close.assert_called_once_with(SaveChanges=False)
    app.Quit.assert_called_once_with()


def test_write_output_rejects_final_column_only_in_unrelated_formula_position(
    monkeypatch, tmp_path
):
    plan = _plan()
    detail = MagicMock()
    summary = MagicMock()
    detail.Cells.side_effect = lambda row, col: _cell()
    summary.Cells.side_effect = lambda row, col: _cell(
        formula='=COUNTIF(出勤明细!D7:AG7,"√")+IF(AH1>0,0,0)'
    )
    workbook = MagicMock()
    workbook.ReadOnly = False
    workbook.Worksheets.side_effect = {"出勤明细": detail, "考勤汇总表": summary}.__getitem__
    _patch_excel(monkeypatch, workbook)
    source = SourceAttendance(
        (EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(31))),), "市场部"
    )

    with pytest.raises(ValueError, match="D7:AH7"):
        ExcelComAdapter().write_output(
            tmp_path / "staging.xlsx",
            plan,
            _prepared(source, (tuple("√" for _ in range(31)),), 31),
        )


def test_prepare_group_sheets_copies_pairs_rebinds_formulas_and_deletes_bases(monkeypatch):
    plan = _plan()
    base_detail = MagicMock(name="base_detail")
    base_summary = MagicMock(name="base_summary")
    group_detail_a = MagicMock(name="group_detail_a")
    group_summary_a = MagicMock(name="group_summary_a")
    group_detail_b = MagicMock(name="group_detail_b")
    group_summary_b = MagicMock(name="group_summary_b")
    workbook = MagicMock()
    workbook.Worksheets.side_effect = {
        "出勤明细": base_detail,
        "考勤汇总表": base_summary,
    }.__getitem__
    copied = {
        "出勤明细-A": group_detail_a,
        "考勤汇总表-A": group_summary_a,
        "出勤明细-B": group_detail_b,
        "考勤汇总表-B": group_summary_b,
    }
    copy_calls = []

    def fake_copy(_workbook, source, name):
        copy_calls.append((source, name))
        return copied[name]

    monkeypatch.setattr("file_toolbox.core.attendance.excel._copy_worksheet", fake_copy)
    source = SourceAttendance((EmployeeAttendance("张三", "市场部", ("正常",), "A"),), "市场部")
    groups = (
        PreparedGroup("A", source, (("√",),), "出勤明细-A", "考勤汇总表-A", ()),
        PreparedGroup("B", source, (("√",),), "出勤明细-B", "考勤汇总表-B", ()),
    )

    result = _prepare_group_sheets(workbook, plan, groups)

    assert [name for _, name in copy_calls] == [
        "出勤明细-A",
        "考勤汇总表-A",
        "出勤明细-B",
        "考勤汇总表-B",
    ]
    assert result[0] == (groups[0], group_detail_a, group_summary_a)
    assert group_summary_a.Cells.Replace.call_count == 2
    assert group_summary_b.Cells.Replace.call_count == 2
    base_summary.Delete.assert_called_once_with()
    base_detail.Delete.assert_called_once_with()


def test_copy_worksheet_uses_positional_after_argument_for_dynamic_com():
    workbook = MagicMock()
    workbook.Sheets.Count = 4
    last_sheet = MagicMock(name="last_sheet")
    copied = MagicMock(name="copied")
    workbook.Sheets.side_effect = {4: last_sheet, 5: copied}.__getitem__
    source = MagicMock()
    source.Copy.side_effect = lambda *_args: setattr(workbook.Sheets, "Count", 5)

    result = _copy_worksheet(workbook, source, "分组明细")

    source.Copy.assert_called_once_with(None, last_sheet)
    assert result is copied
    assert copied.Name == "分组明细"
