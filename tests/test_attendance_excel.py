"""Microsoft Excel COM adapter 控制流测试，不启动真实 Excel。"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_toolbox.core.attendance.excel import ExcelComAdapter
from file_toolbox.core.attendance.types import (
    AttendancePlan,
    CellMapping,
    CellRef,
    EmployeeAttendance,
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


def test_validate_template_checks_target_sheets_and_formula(monkeypatch, tmp_path):
    plan = _plan()
    detail = MagicMock()
    summary = MagicMock()
    detail.Cells.return_value = _cell(value=1)
    summary.Cells.return_value = _cell(formula='=COUNTIF(出勤明细!D7:AG7,"√")')
    workbook = MagicMock()
    workbook.Worksheets.side_effect = {"出勤明细": detail, "考勤汇总表": summary}.__getitem__
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
    plan = _plan()
    values = {
        (2, 1): "张三",
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

    ExcelComAdapter().write_output(
        tmp_path / "staging.xlsx",
        plan,
        source,
        symbols,
        (("出勤明细", CellRef.parse("A3"), "标题"),),
        day_count,
    )

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
            source,
            (tuple("√" for _ in range(30)),),
            (),
            30,
        )

    workbook.Close.assert_called_once_with(SaveChanges=False)
    app.Quit.assert_called_once_with()
