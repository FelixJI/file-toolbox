"""考勤工作簿 seam 与 Microsoft Excel COM adapter。"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Protocol

from file_toolbox.common.office_session import (
    ComSession,
    dispose_office_app,
    init_isolated_office_app,
    open_office_document,
    retry_com_call,
)
from file_toolbox.core.attendance.types import (
    AttendancePlan,
    CellRef,
    EmployeeAttendance,
    PreparedAttendance,
    PreparedGroup,
    RosterData,
    RosterEmployee,
    RosterLayout,
    SourceAttendance,
    SourceLayout,
)
from file_toolbox.core.office_capability import record_office_session_success

CancelCheck = Callable[[], bool]
_cancel_check: ContextVar[CancelCheck | None] = ContextVar("attendance_cancel_check", default=None)


def _excel_call[**P, T](operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    return retry_com_call(lambda: operation(*args, **kwargs), _cancel_check.get())


BASE_EMPLOYEE_ROWS = 15
BASE_DATE_COLUMNS = 30
OVERTIME_COLUMN_COUNT = 3
SUMMARY_OVERTIME_COLUMN_OFFSET = 15
MAX_EMPLOYEES = 1000


class AttendanceExcelAdapter(Protocol):
    """AttendanceService 的内部 Excel seam。"""

    def validate_template(self, template_path: Path, plan: AttendancePlan) -> tuple[str, ...]: ...

    def read_source(
        self,
        source_path: Path,
        layout: SourceLayout,
        day_count: int,
        cancel_check: CancelCheck | None = None,
    ) -> SourceAttendance: ...

    def read_roster(
        self,
        roster_path: Path,
        layout: RosterLayout,
        cancel_check: CancelCheck | None = None,
    ) -> RosterData: ...

    def write_output(
        self,
        staging_path: Path,
        plan: AttendancePlan,
        prepared: PreparedAttendance,
        cancel_check: CancelCheck | None = None,
    ) -> None: ...


class _DeletableWorksheet(Protocol):
    def Delete(self) -> object: ...


class _WorksheetCollection(Protocol):
    def __call__(self, name: str) -> _DeletableWorksheet: ...


class _WorkbookWithWorksheets(Protocol):
    Worksheets: _WorksheetCollection


class _MovableWorksheet(Protocol):
    @property
    def Index(self) -> int: ...

    def Move(self, before: object) -> object: ...


class _WritableRange(Protocol):
    NumberFormat: object
    Value: object


class _WritableWorksheet(Protocol):
    def Cells(self, row: int, column: int) -> object: ...

    def Range(self, start: object, end: object) -> _WritableRange: ...


class ExcelComAdapter:
    """通过隔离 Microsoft Excel COM 会话读源并写模板副本。"""

    def validate_template(self, template_path: Path, plan: AttendancePlan) -> tuple[str, ...]:
        with _excel_workbook(template_path, read_only=True) as (_, workbook):
            sheet_names = _worksheet_names(workbook)
            available_sheets = {name.casefold(): name for name in sheet_names}
            pairs = [(plan.target.detail_sheet, plan.target.summary_sheet)]
            missing_names: list[str] = []
            if plan.roster is not None:
                for config in plan.group_sheet_configs:
                    detail_exists = config.detail_sheet.casefold() in available_sheets
                    summary_exists = config.summary_sheet.casefold() in available_sheets
                    if detail_exists and summary_exists:
                        pairs.append((config.detail_sheet, config.summary_sheet))
                    elif detail_exists != summary_exists:
                        missing_names.append(
                            config.summary_sheet if detail_exists else config.detail_sheet
                        )
            required_names = [name for pair in pairs for name in pair]
            required_names.extend(mapping.sheet_name for mapping in plan.mappings)
            missing_names.extend(
                name for name in required_names if name.casefold() not in available_sheets
            )
            if missing_names:
                unique_missing = tuple(dict.fromkeys(missing_names))
                raise ValueError(f"模板缺少工作表: {', '.join(unique_missing)}")
            checked: set[tuple[str, str]] = set()
            for detail_name, summary_name in pairs:
                key = (detail_name.casefold(), summary_name.casefold())
                if key in checked:
                    continue
                checked.add(key)
                detail = _excel_call(
                    lambda detail_name: workbook.Worksheets(
                        available_sheets[detail_name.casefold()]
                    ),
                    detail_name,
                )
                summary = _excel_call(
                    lambda summary_name: workbook.Worksheets(
                        available_sheets[summary_name.casefold()]
                    ),
                    summary_name,
                )
                header = _excel_call(
                    lambda detail: (
                        detail.Cells(
                            plan.target.detail_matrix_start.row - 1,
                            plan.target.detail_matrix_start.column,
                        ).Value
                    ),
                    detail,
                )
                if str(header).strip() != "1":
                    raise ValueError(
                        f"模板日期区域结构不符: {detail_name} 明细矩阵上方首列必须为日期 1"
                    )
                formula = _excel_call(
                    lambda summary: (
                        summary.Cells(
                            plan.target.summary_name_start.row,
                            plan.target.summary_name_start.column + 2,
                        ).Formula
                    ),
                    summary,
                )
                if not isinstance(formula, str) or not formula.startswith("="):
                    raise ValueError(
                        f"模板汇总区域结构不符: {summary_name} 姓名右侧第二列应包含汇总公式"
                    )
            return sheet_names

    def read_source(
        self,
        source_path: Path,
        layout: SourceLayout,
        day_count: int,
        cancel_check: CancelCheck | None = None,
    ) -> SourceAttendance:
        employees: list[EmployeeAttendance] = []
        with _excel_workbook(source_path, read_only=True, cancel_check=cancel_check) as (
            _,
            workbook,
        ):
            sheet = _excel_call(lambda: workbook.Worksheets(layout.sheet_name))
            group_start = layout.attendance_group_start
            for offset in range(MAX_EMPLOYEES):
                _raise_if_cancelled(cancel_check)
                name = _cell_text(
                    _excel_call(
                        lambda offset: (
                            sheet.Cells(
                                layout.name_start.row + offset, layout.name_start.column
                            ).Value
                        ),
                        offset,
                    )
                )
                if not name.strip():
                    break
                department = _cell_text(
                    _excel_call(
                        lambda offset: (
                            sheet.Cells(
                                layout.department_start.row + offset, layout.department_start.column
                            ).Value
                        ),
                        offset,
                    )
                )
                records = tuple(
                    _cell_text(
                        _excel_call(
                            lambda day, offset: (
                                sheet.Cells(
                                    layout.detail_start.row + offset,
                                    layout.detail_start.column + day,
                                ).Value
                            ),
                            day,
                            offset,
                        )
                    )
                    for day in range(day_count)
                )
                overtime_start_column = layout.detail_start.column - OVERTIME_COLUMN_COUNT
                if overtime_start_column < 1:
                    raise ValueError("源明细起始列前必须保留工作日、休息日、节假日加班三列")
                overtime_hours = (
                    _overtime_value(
                        _excel_call(
                            lambda offset, overtime_start_column: (
                                sheet.Cells(
                                    layout.detail_start.row + offset, overtime_start_column
                                ).Value
                            ),
                            offset,
                            overtime_start_column,
                        )
                    ),
                    _overtime_value(
                        _excel_call(
                            lambda offset, overtime_start_column: (
                                sheet.Cells(
                                    layout.detail_start.row + offset, overtime_start_column + 1
                                ).Value
                            ),
                            offset,
                            overtime_start_column,
                        )
                    ),
                    _overtime_value(
                        _excel_call(
                            lambda offset, overtime_start_column: (
                                sheet.Cells(
                                    layout.detail_start.row + offset, overtime_start_column + 2
                                ).Value
                            ),
                            offset,
                            overtime_start_column,
                        )
                    ),
                )
                attendance_group = ""
                if group_start is not None:
                    attendance_group = _cell_text(
                        _excel_call(
                            lambda offset: (
                                sheet.Cells(
                                    group_start.row + offset,
                                    group_start.column,
                                ).Value
                            ),
                            offset,
                        )
                    )
                employees.append(
                    EmployeeAttendance(
                        name,
                        department,
                        records,
                        attendance_group,
                        overtime_hours=overtime_hours,
                    )
                )
            else:
                raise ValueError(f"员工数超过安全上限 {MAX_EMPLOYEES}")

        if not employees:
            raise ValueError("源工作表未读取到员工姓名")
        departments = {item.department.strip() for item in employees if item.department.strip()}
        department = next(iter(departments), "")
        return SourceAttendance(tuple(employees), department)

    def read_roster(
        self,
        roster_path: Path,
        layout: RosterLayout,
        cancel_check: CancelCheck | None = None,
    ) -> RosterData:
        employees: list[RosterEmployee] = []
        starts = (
            layout.group_start,
            layout.department_start,
            layout.name_start,
            layout.employee_id_start,
        )
        with _excel_workbook(roster_path, read_only=True, cancel_check=cancel_check) as (
            _,
            workbook,
        ):
            sheet = _excel_call(lambda: workbook.Worksheets(layout.sheet_name))
            used = _excel_call(lambda: sheet.UsedRange)
            last_row = (
                int(_excel_call(lambda: used.Row)) + int(_excel_call(lambda: used.Rows.Count)) - 1
            )
            logical_row_count = max(max(0, last_row - cell.row + 1) for cell in starts)
            for offset in range(logical_row_count):
                _raise_if_cancelled(cancel_check)
                source_row = layout.name_start.row + offset
                group = _cell_text(
                    _excel_call(
                        lambda offset: (
                            sheet.Cells(
                                layout.group_start.row + offset, layout.group_start.column
                            ).Value
                        ),
                        offset,
                    )
                ).strip()
                department = _cell_text(
                    _excel_call(
                        lambda offset: (
                            sheet.Cells(
                                layout.department_start.row + offset, layout.department_start.column
                            ).Value
                        ),
                        offset,
                    )
                ).strip()
                name = _cell_text(
                    _excel_call(
                        lambda offset: (
                            sheet.Cells(
                                layout.name_start.row + offset, layout.name_start.column
                            ).Value
                        ),
                        offset,
                    )
                ).strip()
                employee_id = _cell_text(
                    _excel_call(
                        lambda offset: (
                            sheet.Cells(
                                layout.employee_id_start.row + offset,
                                layout.employee_id_start.column,
                            ).Value
                        ),
                        offset,
                    )
                ).strip()
                values = (group, department, name, employee_id)
                if not any(values):
                    continue
                labels = ("分组", "部门", "姓名", "工号")
                missing = [label for label, value in zip(labels, values, strict=True) if not value]
                if missing:
                    raise ValueError(f"人员名单第 {source_row} 行缺少字段: {', '.join(missing)}")
                employees.append(RosterEmployee(employee_id, name, department, group, source_row))
                if len(employees) > MAX_EMPLOYEES:
                    raise ValueError(f"名单员工数超过安全上限 {MAX_EMPLOYEES}")
        if not employees:
            raise ValueError("人员名单未读取到有效人员")
        if len(employees) > MAX_EMPLOYEES:
            raise ValueError(f"名单员工数超过安全上限 {MAX_EMPLOYEES}")
        return RosterData(tuple(employees))

    def write_output(
        self,
        staging_path: Path,
        plan: AttendancePlan,
        prepared: PreparedAttendance,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        with _excel_workbook(staging_path, read_only=False, cancel_check=cancel_check) as (
            app,
            workbook,
        ):
            _excel_call(lambda: setattr(app, "ScreenUpdating", False))
            if bool(_excel_call(lambda: workbook.ReadOnly)):
                raise ValueError("Excel 以只读方式打开了结果副本")
            _raise_if_cancelled(cancel_check)
            if prepared.roster_mode:
                _remove_roster_sheets(workbook, prepared.remove_sheet_pairs)
            sheets = _prepare_group_sheets(workbook, plan, prepared.groups)
            if prepared.roster_mode:
                _order_roster_group_sheets(sheets)
            for group, detail, summary in sheets:
                _raise_if_cancelled(cancel_check)
                _write_group(detail, summary, plan, group, prepared.preview.day_count)
            for sheet_name, cell_ref, value in prepared.global_mapping_values:
                sheet = _excel_call(lambda sheet_name: workbook.Worksheets(sheet_name), sheet_name)
                _write_mapping(sheet, cell_ref, value)
            _raise_if_cancelled(cancel_check)
            _excel_call(lambda: app.CalculateFullRebuild())
            _excel_call(lambda: workbook.Save())


def _prepare_group_sheets(
    workbook: Any,
    plan: AttendancePlan,
    groups: tuple[PreparedGroup, ...],
) -> tuple[tuple[PreparedGroup, Any, Any], ...]:
    if plan.roster is not None:
        base_detail = _excel_call(lambda: workbook.Worksheets(plan.target.detail_sheet))
        base_summary = _excel_call(lambda: workbook.Worksheets(plan.target.summary_sheet))
        available_sheets = {name.casefold(): name for name in _worksheet_names(workbook)}
        roster_result: list[tuple[PreparedGroup, Any, Any]] = []
        used_detail_sheets: set[str] = set()
        used_summary_sheets: set[str] = set()
        for group in groups:
            detail_key = group.detail_sheet.casefold()
            summary_key = group.summary_sheet.casefold()
            detail_name = available_sheets.get(detail_key)
            summary_name = available_sheets.get(summary_key)
            if (detail_name is None) != (summary_name is None):
                missing_name = group.detail_sheet if detail_name is None else group.summary_sheet
                raise ValueError(f"模板分组工作表不完整，缺少: {missing_name}")
            if detail_name is not None and summary_name is not None:
                detail = _excel_call(
                    lambda detail_name: workbook.Worksheets(detail_name), detail_name
                )
                summary = _excel_call(
                    lambda summary_name: workbook.Worksheets(summary_name), summary_name
                )
            else:
                detail = _copy_worksheet(workbook, base_detail, group.detail_sheet)
                summary = _copy_worksheet(workbook, base_summary, group.summary_sheet)
                _replace_sheet_references(summary, plan.target.detail_sheet, group.detail_sheet)
                available_sheets[detail_key] = group.detail_sheet
                available_sheets[summary_key] = group.summary_sheet
            used_detail_sheets.add(detail_key)
            used_summary_sheets.add(summary_key)
            roster_result.append((group, detail, summary))
        if plan.target.summary_sheet.casefold() not in used_summary_sheets:
            _excel_call(lambda: base_summary.Delete())
        if plan.target.detail_sheet.casefold() not in used_detail_sheets:
            _excel_call(lambda: base_detail.Delete())
        return tuple(roster_result)
    base_detail = _excel_call(lambda: workbook.Worksheets(plan.target.detail_sheet))
    base_summary = _excel_call(lambda: workbook.Worksheets(plan.target.summary_sheet))
    if (
        len(groups) == 1
        and groups[0].detail_sheet == plan.target.detail_sheet
        and groups[0].summary_sheet == plan.target.summary_sheet
    ):
        return ((groups[0], base_detail, base_summary),)

    result: list[tuple[PreparedGroup, Any, Any]] = []
    for group in groups:
        detail = _copy_worksheet(workbook, base_detail, group.detail_sheet)
        summary = _copy_worksheet(workbook, base_summary, group.summary_sheet)
        _replace_sheet_references(summary, plan.target.detail_sheet, group.detail_sheet)
        result.append((group, detail, summary))
    _excel_call(lambda: base_summary.Delete())
    _excel_call(lambda: base_detail.Delete())
    return tuple(result)


def _remove_roster_sheets(
    workbook: _WorkbookWithWorksheets, sheet_pairs: tuple[tuple[str, str], ...]
) -> None:
    for detail_name, summary_name in sheet_pairs:
        _excel_call(lambda summary_name: workbook.Worksheets(summary_name).Delete(), summary_name)
        _excel_call(lambda detail_name: workbook.Worksheets(detail_name).Delete(), detail_name)


def _order_roster_group_sheets(
    sheets: tuple[tuple[PreparedGroup, _MovableWorksheet, _MovableWorksheet], ...],
) -> None:
    if len(sheets) < 2:
        return
    anchor = min(
        (sheet for _, detail, summary in sheets for sheet in (detail, summary)),
        key=lambda sheet: int(_excel_call(lambda: sheet.Index)),
    )
    for _, detail, summary in reversed(sheets):
        _excel_call(lambda anchor, summary: summary.Move(anchor), anchor, summary)
        _excel_call(lambda detail, summary: detail.Move(summary), detail, summary)
        anchor = detail


def _copy_worksheet(workbook: Any, source: Any, name: str) -> Any:
    _excel_call(lambda: source.Copy(None, workbook.Sheets(workbook.Sheets.Count)))
    copied = _excel_call(lambda: workbook.Sheets(workbook.Sheets.Count))
    _excel_call(lambda: setattr(copied, "Name", name))
    return copied


def _worksheet_names(workbook: Any) -> tuple[str, ...]:
    return tuple(
        str(_excel_call(lambda index: workbook.Worksheets(index).Name, index))
        for index in range(1, int(_excel_call(lambda: workbook.Worksheets.Count)) + 1)
    )


def _replace_sheet_references(sheet: Any, old_name: str, new_name: str) -> None:
    quoted_old = f"'{old_name.replace(chr(39), chr(39) * 2)}'!"
    quoted_new = f"'{new_name.replace(chr(39), chr(39) * 2)}'!"
    for old_reference in (quoted_old, f"{old_name}!"):
        _excel_call(
            lambda old_reference: sheet.Cells.Replace(
                What=old_reference, Replacement=quoted_new, LookAt=2, SearchOrder=1, MatchCase=False
            ),
            old_reference,
        )


def _write_group(
    detail: Any,
    summary: Any,
    plan: AttendancePlan,
    group: PreparedGroup,
    day_count: int,
) -> None:
    _adjust_date_columns(detail, plan.target.detail_matrix_start, day_count)
    employee_count = len(group.source.employees)
    _adjust_employee_rows(detail, plan.target.detail_name_start.row, employee_count)
    _adjust_employee_rows(summary, plan.target.summary_name_start.row, employee_count)
    _write_names(detail, plan.target.detail_name_start, group.source)
    _write_names(summary, plan.target.summary_name_start, group.source)
    _write_overtime_hours(
        summary,
        plan.target.summary_name_start.offset(columns=SUMMARY_OVERTIME_COLUMN_OFFSET),
        group.source,
    )
    if plan.roster is not None:
        if plan.roster.fill_serial_numbers:
            serials = tuple(range(1, len(group.source.employees) + 1))
            _write_column(detail, plan.roster.detail_serial_start, serials)
            _write_column(summary, plan.roster.summary_serial_start, serials)
        if plan.roster.fill_employee_ids:
            employee_ids = tuple(employee.employee_id for employee in group.source.employees)
            _write_column(detail, plan.roster.detail_employee_id_start, employee_ids, as_text=True)
            _write_column(
                summary, plan.roster.summary_employee_id_start, employee_ids, as_text=True
            )
    _write_symbols(detail, plan.target.detail_matrix_start, group.symbols)
    _write_day_labels(detail, plan.target.detail_matrix_start, day_count)
    for sheet_name, cell_ref, value in group.mapping_values:
        target = detail if sheet_name == group.detail_sheet else summary
        if sheet_name not in {group.detail_sheet, group.summary_sheet}:
            raise ValueError(f"分组映射目标工作表无效: {sheet_name}")
        _write_mapping(target, cell_ref, value)
    _verify_summary_formula(
        summary,
        group.detail_sheet,
        plan.target.detail_matrix_start,
        plan.target.summary_name_start,
        day_count,
    )


def _open_workbook(app: Any, path: Path, *, read_only: bool) -> Any:
    return _excel_call(
        lambda: open_office_document(
            app,
            "Workbooks",
            path,
            UpdateLinks=0,
            ReadOnly=read_only,
            AddToMru=False,
            IgnoreReadOnlyRecommended=True,
        )
    )


@contextlib.contextmanager
def _excel_workbook(
    path: Path, *, read_only: bool, cancel_check: CancelCheck | None = None
) -> Iterator[tuple[Any, Any]]:
    """创建隔离会话，并把 Close/Quit 失败作为真实操作失败传播。"""
    app: Any | None = None
    workbook: Any | None = None
    with ComSession():
        cancel_token = _cancel_check.set(cancel_check)
        try:
            operation_error: Exception | None = None
            try:
                app = init_isolated_office_app("Excel.Application")
                # Dispatch 成功即最强证据:登记到能力层(与 PDF 转换链同一进程内
                # 存储),页面能力提示/自测前置据此展示"已验证"。
                record_office_session_success("excel", "office")
                workbook = _open_workbook(app, path, read_only=read_only)
                yield app, workbook
            except Exception as exc:  # 保留业务错误，同时继续完整释放 COM
                operation_error = exc

            cleanup_error = _release_excel(workbook, app)
            workbook = None
            app = None
            if operation_error is not None:
                if cleanup_error is not None:
                    raise RuntimeError(f"{operation_error}；{cleanup_error}") from operation_error
                raise operation_error
            if cleanup_error is not None:
                raise cleanup_error
        finally:
            _cancel_check.reset(cancel_token)


def _release_excel(workbook: Any | None, app: Any | None) -> RuntimeError | None:
    errors: list[str] = []
    if workbook is not None:
        try:
            retry_com_call(lambda: workbook.Close(SaveChanges=False))
        except Exception as exc:
            errors.append(f"关闭工作簿失败: {exc}")
    try:
        dispose_office_app(app, "Excel.Application", raise_on_error=True)
    except RuntimeError as exc:
        errors.append(str(exc))
    if errors:
        return RuntimeError("；".join(errors))
    return None


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise InterruptedError("操作已取消")


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _overtime_value(value: object) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (str, int, float)):
        return value
    return str(value)


def _adjust_date_columns(sheet: Any, matrix_start: CellRef, day_count: int) -> None:
    delta = day_count - BASE_DATE_COLUMNS
    if delta > 0:
        insertion_column = matrix_start.column + BASE_DATE_COLUMNS - 1
        for _ in range(delta):
            _excel_call(lambda: sheet.Columns(insertion_column).Insert(CopyOrigin=0))
    elif delta < 0:
        first_unwanted = matrix_start.column + day_count
        for _ in range(-delta):
            _excel_call(lambda: sheet.Columns(first_unwanted).Delete())


def _adjust_employee_rows(sheet: Any, first_row: int, employee_count: int) -> None:
    extra_rows = employee_count - BASE_EMPLOYEE_ROWS
    for offset in range(max(0, extra_rows)):
        insert_row = first_row + BASE_EMPLOYEE_ROWS + offset
        _excel_call(lambda insert_row: sheet.Rows(insert_row).Insert(CopyOrigin=0), insert_row)
        _excel_call(
            lambda insert_row: sheet.Rows(insert_row - 1).Copy(Destination=sheet.Rows(insert_row)),
            insert_row,
        )
    for row in range(
        first_row + BASE_EMPLOYEE_ROWS - 1,
        first_row + employee_count - 1,
        -1,
    ):
        _excel_call(lambda row: sheet.Rows(row).Delete(), row)


def _write_names(sheet: Any, start: CellRef, source: SourceAttendance) -> None:
    end = start.offset(rows=len(source.employees) - 1)
    _excel_call(
        lambda: setattr(
            sheet.Range(sheet.Cells(start.row, start.column), sheet.Cells(end.row, end.column)),
            "Value",
            tuple((employee.name,) for employee in source.employees),
        )
    )


def _write_overtime_hours(sheet: Any, start: CellRef, source: SourceAttendance) -> None:
    if not source.employees:
        return
    end = start.offset(
        rows=len(source.employees) - 1,
        columns=OVERTIME_COLUMN_COUNT - 1,
    )
    _excel_call(
        lambda: setattr(
            sheet.Range(sheet.Cells(start.row, start.column), sheet.Cells(end.row, end.column)),
            "Value",
            tuple(employee.overtime_hours for employee in source.employees),
        )
    )


def _write_column(
    sheet: _WritableWorksheet,
    start: CellRef,
    values: tuple[int, ...] | tuple[str, ...],
    *,
    as_text: bool = False,
) -> None:
    if not values:
        return
    end = start.offset(rows=len(values) - 1)
    target = _excel_call(
        lambda: sheet.Range(sheet.Cells(start.row, start.column), sheet.Cells(end.row, end.column))
    )
    if as_text:
        _excel_call(lambda: setattr(target, "NumberFormat", "@"))
    _excel_call(lambda: setattr(target, "Value", tuple((value,) for value in values)))


def _write_symbols(sheet: Any, start: CellRef, symbols: tuple[tuple[str, ...], ...]) -> None:
    if not symbols:
        return
    end = start.offset(rows=len(symbols) - 1, columns=len(symbols[0]) - 1)
    _excel_call(
        lambda: setattr(
            sheet.Range(sheet.Cells(start.row, start.column), sheet.Cells(end.row, end.column)),
            "Value",
            symbols,
        )
    )


def _write_day_labels(sheet: Any, matrix_start: CellRef, day_count: int) -> None:
    header = matrix_start.offset(rows=-1)
    end = header.offset(columns=day_count - 1)
    _excel_call(
        lambda: setattr(
            sheet.Range(sheet.Cells(header.row, header.column), sheet.Cells(end.row, end.column)),
            "Value",
            (tuple(range(1, day_count + 1)),),
        )
    )


def _write_mapping(sheet: Any, cell_ref: CellRef, value: str) -> None:
    cell = _excel_call(lambda: sheet.Cells(cell_ref.row, cell_ref.column))
    if bool(_excel_call(lambda: cell.MergeCells)):
        area = _excel_call(lambda: cell.MergeArea)
        if (
            int(_excel_call(lambda: area.Row)) != cell_ref.row
            or int(_excel_call(lambda: area.Column)) != cell_ref.column
        ):
            raise ValueError(f"合并单元格只能配置左上角: {cell_ref.address}")
    _excel_call(lambda: setattr(cell, "Value", value))


def _verify_summary_formula(
    summary: Any,
    detail_sheet_name: str,
    detail_matrix_start: CellRef,
    summary_name_start: CellRef,
    day_count: int,
) -> None:
    formula = _excel_call(
        lambda: (
            summary.Cells(
                summary_name_start.row,
                summary_name_start.column + 2,
            ).Formula
        )
    )
    start = detail_matrix_start
    end = start.offset(columns=day_count - 1)
    if not isinstance(formula, str) or not _formula_contains_range(
        formula,
        detail_sheet_name,
        start.address,
        end.address,
    ):
        raise ValueError(f"汇总公式未覆盖目标范围 {start.address}:{end.address}")


_FORMULA_RANGE_RE = re.compile(
    r"(?:'((?:''|[^'])+)'|([^\s'!(),=+\-*/]+))!"
    r"\$?([A-Z]{1,3})\$?([1-9]\d*):\$?([A-Z]{1,3})\$?([1-9]\d*)",
    re.IGNORECASE,
)


def _formula_contains_range(formula: str, sheet_name: str, start: str, end: str) -> bool:
    expected_sheet = sheet_name.casefold()
    expected_start = start.upper()
    expected_end = end.upper()
    for match in _FORMULA_RANGE_RE.finditer(formula):
        quoted_sheet, plain_sheet, start_column, start_row, end_column, end_row = match.groups()
        actual_sheet = (quoted_sheet or plain_sheet).replace("''", "'").casefold()
        actual_start = f"{start_column.upper()}{start_row}"
        actual_end = f"{end_column.upper()}{end_row}"
        if (
            actual_sheet == expected_sheet
            and actual_start == expected_start
            and actual_end == expected_end
        ):
            return True
    return False
