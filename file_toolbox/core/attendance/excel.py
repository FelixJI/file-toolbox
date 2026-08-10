"""考勤工作簿 seam 与 Microsoft Excel COM adapter。"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from file_toolbox.common.office_session import (
    ComSession,
    dispose_office_app,
    init_isolated_office_app,
)
from file_toolbox.core.attendance.types import (
    AttendancePlan,
    CellRef,
    EmployeeAttendance,
    SourceAttendance,
    SourceLayout,
    column_letters,
)

CancelCheck = Callable[[], bool]

BASE_EMPLOYEE_ROWS = 15
BASE_DATE_COLUMNS = 30
MAX_EMPLOYEES = 1000


class AttendanceExcelAdapter(Protocol):
    """AttendanceService 的内部 Excel seam。"""

    def validate_template(self, template_path: Path, plan: AttendancePlan) -> None: ...

    def read_source(
        self,
        source_path: Path,
        layout: SourceLayout,
        day_count: int,
        cancel_check: CancelCheck | None = None,
    ) -> SourceAttendance: ...

    def write_output(
        self,
        staging_path: Path,
        plan: AttendancePlan,
        source: SourceAttendance,
        symbols: tuple[tuple[str, ...], ...],
        mapping_values: tuple[tuple[str, CellRef, str], ...],
        day_count: int,
        cancel_check: CancelCheck | None = None,
    ) -> None: ...


class ExcelComAdapter:
    """通过隔离 Microsoft Excel COM 会话读源并写模板副本。"""

    def validate_template(self, template_path: Path, plan: AttendancePlan) -> None:
        app: Any | None = None
        workbook: Any | None = None
        with ComSession():
            try:
                app = init_isolated_office_app("Excel.Application")
                workbook = _open_workbook(app, template_path, read_only=True)
                detail = workbook.Worksheets(plan.target.detail_sheet)
                summary = workbook.Worksheets(plan.target.summary_sheet)
                header = detail.Cells(
                    plan.target.detail_matrix_start.row - 1,
                    plan.target.detail_matrix_start.column,
                ).Value
                if str(header).strip() != "1":
                    raise ValueError("模板日期区域结构不符: 明细矩阵上方首列必须为日期 1")
                formula = summary.Cells(
                    plan.target.summary_name_start.row,
                    plan.target.summary_name_start.column + 2,
                ).Formula
                if not isinstance(formula, str) or not formula.startswith("="):
                    raise ValueError("模板汇总区域结构不符: 姓名右侧第二列应包含汇总公式")
            finally:
                _close_workbook(workbook)
                dispose_office_app(app)

    def read_source(
        self,
        source_path: Path,
        layout: SourceLayout,
        day_count: int,
        cancel_check: CancelCheck | None = None,
    ) -> SourceAttendance:
        app: Any | None = None
        workbook: Any | None = None
        employees: list[EmployeeAttendance] = []
        with ComSession():
            try:
                app = init_isolated_office_app("Excel.Application")
                workbook = _open_workbook(app, source_path, read_only=True)
                sheet = workbook.Worksheets(layout.sheet_name)
                for offset in range(MAX_EMPLOYEES):
                    _raise_if_cancelled(cancel_check)
                    name = _cell_text(
                        sheet.Cells(layout.name_start.row + offset, layout.name_start.column).Value
                    )
                    if not name.strip():
                        break
                    department = _cell_text(
                        sheet.Cells(
                            layout.department_start.row + offset,
                            layout.department_start.column,
                        ).Value
                    )
                    records = tuple(
                        _cell_text(
                            sheet.Cells(
                                layout.detail_start.row + offset,
                                layout.detail_start.column + day,
                            ).Value
                        )
                        for day in range(day_count)
                    )
                    employees.append(EmployeeAttendance(name, department, records))
                else:
                    raise ValueError(f"员工数超过安全上限 {MAX_EMPLOYEES}")
            finally:
                _close_workbook(workbook)
                dispose_office_app(app)

        if not employees:
            raise ValueError("源工作表未读取到员工姓名")
        departments = {item.department.strip() for item in employees if item.department.strip()}
        if len(departments) > 1:
            raise ValueError("源考勤包含多个部门，首版不支持自动拆分")
        department = next(iter(departments), "")
        return SourceAttendance(tuple(employees), department)

    def write_output(
        self,
        staging_path: Path,
        plan: AttendancePlan,
        source: SourceAttendance,
        symbols: tuple[tuple[str, ...], ...],
        mapping_values: tuple[tuple[str, CellRef, str], ...],
        day_count: int,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        app: Any | None = None
        workbook: Any | None = None
        with ComSession():
            try:
                app = init_isolated_office_app("Excel.Application")
                app.ScreenUpdating = False
                workbook = _open_workbook(app, staging_path, read_only=False)
                if bool(workbook.ReadOnly):
                    raise ValueError("Excel 以只读方式打开了结果副本")
                detail = workbook.Worksheets(plan.target.detail_sheet)
                summary = workbook.Worksheets(plan.target.summary_sheet)

                _raise_if_cancelled(cancel_check)
                _adjust_date_columns(detail, plan.target.detail_matrix_start, day_count)
                extra_rows = max(0, len(source.employees) - BASE_EMPLOYEE_ROWS)
                _expand_employee_rows(detail, plan.target.detail_name_start.row, extra_rows)
                _expand_employee_rows(summary, plan.target.summary_name_start.row, extra_rows)

                _raise_if_cancelled(cancel_check)
                _write_names(detail, plan.target.detail_name_start, source)
                _write_names(summary, plan.target.summary_name_start, source)
                _write_symbols(detail, plan.target.detail_matrix_start, symbols)
                _write_day_labels(detail, plan.target.detail_matrix_start, day_count)
                for sheet_name, cell_ref, value in mapping_values:
                    sheet = workbook.Worksheets(sheet_name)
                    _write_mapping(sheet, cell_ref, value)

                _verify_summary_formula(summary, plan, day_count)
                _raise_if_cancelled(cancel_check)
                app.CalculateFullRebuild()
                workbook.Save()
            finally:
                _close_workbook(workbook)
                dispose_office_app(app)


def _open_workbook(app: Any, path: Path, *, read_only: bool) -> Any:
    return app.Workbooks.Open(
        str(path.resolve()),
        UpdateLinks=0,
        ReadOnly=read_only,
        AddToMru=False,
        IgnoreReadOnlyRecommended=True,
    )


def _close_workbook(workbook: Any | None) -> None:
    if workbook is not None:
        with contextlib.suppress(Exception):
            workbook.Close(SaveChanges=False)


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise InterruptedError("操作已取消")


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _adjust_date_columns(sheet: Any, matrix_start: CellRef, day_count: int) -> None:
    delta = day_count - BASE_DATE_COLUMNS
    if delta > 0:
        insertion_column = matrix_start.column + BASE_DATE_COLUMNS - 1
        for _ in range(delta):
            sheet.Columns(insertion_column).Insert(CopyOrigin=0)
    elif delta < 0:
        first_unwanted = matrix_start.column + day_count
        for _ in range(-delta):
            sheet.Columns(first_unwanted).Delete()


def _expand_employee_rows(sheet: Any, first_row: int, extra_rows: int) -> None:
    for offset in range(extra_rows):
        insert_row = first_row + BASE_EMPLOYEE_ROWS + offset
        sheet.Rows(insert_row).Insert(CopyOrigin=0)
        sheet.Rows(insert_row - 1).Copy(Destination=sheet.Rows(insert_row))


def _write_names(sheet: Any, start: CellRef, source: SourceAttendance) -> None:
    end = start.offset(rows=len(source.employees) - 1)
    sheet.Range(
        sheet.Cells(start.row, start.column), sheet.Cells(end.row, end.column)
    ).Value = tuple((employee.name,) for employee in source.employees)


def _write_symbols(sheet: Any, start: CellRef, symbols: tuple[tuple[str, ...], ...]) -> None:
    if not symbols:
        return
    end = start.offset(rows=len(symbols) - 1, columns=len(symbols[0]) - 1)
    sheet.Range(
        sheet.Cells(start.row, start.column), sheet.Cells(end.row, end.column)
    ).Value = symbols


def _write_day_labels(sheet: Any, matrix_start: CellRef, day_count: int) -> None:
    header = matrix_start.offset(rows=-1)
    end = header.offset(columns=day_count - 1)
    sheet.Range(sheet.Cells(header.row, header.column), sheet.Cells(end.row, end.column)).Value = (
        tuple(range(1, day_count + 1)),
    )


def _write_mapping(sheet: Any, cell_ref: CellRef, value: str) -> None:
    cell = sheet.Cells(cell_ref.row, cell_ref.column)
    if bool(cell.MergeCells):
        area = cell.MergeArea
        if int(area.Row) != cell_ref.row or int(area.Column) != cell_ref.column:
            raise ValueError(f"合并单元格只能配置左上角: {cell_ref.address}")
    cell.Value = value


def _verify_summary_formula(summary: Any, plan: AttendancePlan, day_count: int) -> None:
    formula = summary.Cells(
        plan.target.summary_name_start.row,
        plan.target.summary_name_start.column + 2,
    ).Formula
    last_column = column_letters(plan.target.detail_matrix_start.column + day_count - 1)
    if not isinstance(formula, str) or last_column not in formula.upper():
        raise ValueError(f"汇总公式未覆盖最终日期列 {last_column}")
