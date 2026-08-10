"""考勤汇总深 module：预览与安全生成。"""

from __future__ import annotations

import calendar
import os
import re
import shutil
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.attendance.excel import (
    BASE_DATE_COLUMNS,
    BASE_EMPLOYEE_ROWS,
    AttendanceExcelAdapter,
    ExcelComAdapter,
)
from file_toolbox.core.attendance.rules import classify, compile_rules, render_content
from file_toolbox.core.attendance.types import (
    AttendancePreview,
    AttendanceRequest,
    AttendanceResult,
    CellMapping,
    CellRef,
    EmployeeAttendance,
    PreparedAttendance,
    PreparedGroup,
    SourceAttendance,
    UnmatchedAttendance,
)

CancelCheck = Callable[[], bool]
_INVALID_SHEET_CHARS_RE = re.compile(r"[\\/*?:\[\]]")


class AttendanceError(RuntimeError):
    """可向 GUI 展示的考勤处理错误。"""


class AttendanceCancelled(AttendanceError):
    """用户在安全检查点取消操作。"""


@dataclass(frozen=True)
class _RunContext:
    request: AttendanceRequest
    day_count: int


class AttendanceService:
    """隐藏源解析、分类、模板写入和另存事务。"""

    def __init__(
        self,
        excel: AttendanceExcelAdapter | None = None,
        history_store: JsonHistoryStore | None = None,
    ) -> None:
        self._excel = excel or ExcelComAdapter()
        self._history_store = history_store

    def preview(
        self, request: AttendanceRequest, cancel_check: CancelCheck | None = None
    ) -> AttendancePreview:
        return self._prepare(request, cancel_check).preview

    def generate(
        self, request: AttendanceRequest, cancel_check: CancelCheck | None = None
    ) -> AttendanceResult:
        prepared = self._prepare(request, cancel_check)
        if prepared.preview.unmatched:
            raise AttendanceError(
                f"存在 {len(prepared.preview.unmatched)} 条未匹配考勤，不能生成结果"
            )
        if request.output_path.exists() and not request.allow_overwrite:
            raise AttendanceError("输出文件已存在，请确认覆盖后重试")
        self._check_cancel(cancel_check)

        staging = request.output_path.with_name(
            f".{request.output_path.stem}.{uuid4().hex}.tmp.xlsx"
        )
        try:
            shutil.copy2(request.plan.template_path, staging)
            self._check_cancel(cancel_check)
            self._excel.write_output(
                staging,
                request.plan,
                prepared,
                cancel_check,
            )
            if not staging.is_file() or staging.stat().st_size == 0:
                raise AttendanceError("Excel 未生成有效的结果副本")
            os.replace(staging, request.output_path)
        except InterruptedError as exc:
            cleanup_error = self._cleanup_staging(staging)
            if cleanup_error is not None:
                raise AttendanceCancelled(f"操作已取消；临时文件清理失败: {staging}") from exc
            raise AttendanceCancelled("操作已取消") from exc
        except Exception as exc:
            cleanup_error = self._cleanup_staging(staging)
            if cleanup_error is not None:
                raise AttendanceError(f"{exc}；临时文件清理失败: {staging}") from exc
            if isinstance(exc, AttendanceError):
                raise
            raise AttendanceError(str(exc)) from exc

        result = AttendanceResult(
            output_path=request.output_path,
            employee_count=prepared.preview.employee_count,
            day_count=prepared.preview.day_count,
            status_counts=prepared.preview.status_counts,
            group_counts=prepared.preview.group_counts,
            target_sheets=prepared.preview.target_sheets,
        )
        if self._history_store is not None:
            try:
                self._history_store.add_record(
                    "attendance",
                    {
                        "plan": request.plan.name,
                        "source": str(request.source_path),
                        "output": str(request.output_path),
                        "year": request.year,
                        "month": request.month,
                        "employee_count": result.employee_count,
                        "status_counts": dict(result.status_counts),
                        "group_counts": dict(result.group_counts),
                        "target_sheets": dict(result.target_sheets),
                    },
                )
            except Exception as exc:  # noqa: BLE001 - 输出已提交，历史只能降级为警告
                result = AttendanceResult(
                    output_path=result.output_path,
                    employee_count=result.employee_count,
                    day_count=result.day_count,
                    status_counts=result.status_counts,
                    group_counts=result.group_counts,
                    target_sheets=result.target_sheets,
                    warnings=(f"结果已生成，但历史记录保存失败: {exc}",),
                )
        return result

    def _prepare(
        self, request: AttendanceRequest, cancel_check: CancelCheck | None
    ) -> PreparedAttendance:
        context = self._validate_request(request)
        try:
            compiled = compile_rules(request.plan.rules)
            template_sheets = self._excel.validate_template(
                request.plan.template_path, request.plan
            )
            self._check_cancel(cancel_check)
            source = self._excel.read_source(
                request.source_path,
                request.plan.source,
                context.day_count,
                cancel_check,
            )
        except InterruptedError as exc:
            raise AttendanceCancelled("操作已取消") from exc
        except (OSError, ValueError) as exc:
            raise AttendanceError(str(exc)) from exc

        employee_groups = self._partition_employees(source, request.plan.split_by_group)
        target_sheets = self._allocate_target_sheets(
            tuple(employee_groups), request, template_sheets
        )
        unmatched: list[UnmatchedAttendance] = []
        counts: Counter[str] = Counter()
        prepared_groups: list[PreparedGroup] = []
        try:
            for group_name, employees in employee_groups.items():
                group_source = SourceAttendance(tuple(employees), source.department)
                symbols = self._classify_group(group_source, compiled, counts, unmatched)
                detail_sheet, summary_sheet = target_sheets[group_name]
                mapping_values = self._group_mapping_values(
                    request,
                    group_source,
                    group_name,
                    detail_sheet,
                    summary_sheet,
                    context.day_count,
                )
                prepared_groups.append(
                    PreparedGroup(
                        attendance_group=group_name,
                        source=group_source,
                        symbols=symbols,
                        detail_sheet=detail_sheet,
                        summary_sheet=summary_sheet,
                        mapping_values=mapping_values,
                    )
                )
            global_mapping_values = self._global_mapping_values(request, source, context.day_count)
        except ValueError as exc:
            raise AttendanceError(str(exc)) from exc

        group_counts = (
            {name: len(employees) for name, employees in employee_groups.items()}
            if request.plan.split_by_group
            else {}
        )
        preview = AttendancePreview(
            employee_count=len(source.employees),
            day_count=context.day_count,
            extra_employee_rows=sum(
                max(0, len(employees) - BASE_EMPLOYEE_ROWS)
                for employees in employee_groups.values()
            ),
            date_column_delta=context.day_count - BASE_DATE_COLUMNS,
            status_counts=dict(counts),
            unmatched=tuple(unmatched),
            group_counts=group_counts,
            target_sheets=target_sheets if request.plan.split_by_group else {},
        )
        return PreparedAttendance(
            groups=tuple(prepared_groups),
            preview=preview,
            global_mapping_values=global_mapping_values,
        )

    @staticmethod
    def _partition_employees(
        source: SourceAttendance, split_by_group: bool
    ) -> dict[str, list[EmployeeAttendance]]:
        if not split_by_group:
            return {"": list(source.employees)}
        groups: dict[str, list[EmployeeAttendance]] = {}
        for employee in source.employees:
            group_name = employee.attendance_group.strip()
            if not group_name:
                raise AttendanceError(f"员工“{employee.name}”缺少考勤组")
            groups.setdefault(group_name, []).append(employee)
        return groups

    @staticmethod
    def _classify_group(
        source: SourceAttendance,
        compiled: tuple[tuple[re.Pattern[str], str], ...],
        counts: Counter[str],
        unmatched: list[UnmatchedAttendance],
    ) -> tuple[tuple[str, ...], ...]:
        symbols: list[tuple[str, ...]] = []
        for employee in source.employees:
            row: list[str] = []
            for day, raw in enumerate(employee.records, start=1):
                symbol = classify(raw, compiled)
                if symbol is None:
                    unmatched.append(
                        UnmatchedAttendance(
                            employee.name,
                            day,
                            raw,
                            employee.attendance_group.strip(),
                        )
                    )
                    row.append("")
                    continue
                row.append(symbol)
                counts[symbol or "空白"] += 1
            symbols.append(tuple(row))
        return tuple(symbols)

    @classmethod
    def _allocate_target_sheets(
        cls,
        group_names: tuple[str, ...],
        request: AttendanceRequest,
        template_sheets: tuple[str, ...],
    ) -> dict[str, tuple[str, str]]:
        target = request.plan.target
        if not request.plan.split_by_group:
            return {"": (target.detail_sheet, target.summary_sheet)}
        reserved = {name.casefold() for name in template_sheets}
        result: dict[str, tuple[str, str]] = {}
        for group_name in group_names:
            detail = cls._unique_sheet_name(f"{target.detail_sheet}-{group_name}", reserved)
            summary = cls._unique_sheet_name(f"{target.summary_sheet}-{group_name}", reserved)
            result[group_name] = (detail, summary)
        return result

    @staticmethod
    def _unique_sheet_name(preferred: str, reserved: set[str]) -> str:
        cleaned = _INVALID_SHEET_CHARS_RE.sub("_", preferred).strip().strip("'") or "未命名组"
        candidate = cleaned[:31]
        suffix = 2
        while candidate.casefold() in reserved:
            tail = f" ({suffix})"
            candidate = f"{cleaned[: 31 - len(tail)]}{tail}"
            suffix += 1
        reserved.add(candidate.casefold())
        return candidate

    @staticmethod
    def _render_mapping(
        mapping: CellMapping,
        request: AttendanceRequest,
        department: str,
        attendance_group: str,
        day_count: int,
        sheet_name: str,
    ) -> tuple[str, CellRef, str]:
        return (
            sheet_name,
            mapping.cell,
            render_content(
                mapping.content_template,
                year=request.year,
                month=request.month,
                last_day=day_count,
                department=department,
                attendance_group=attendance_group,
            ),
        )

    @classmethod
    def _group_mapping_values(
        cls,
        request: AttendanceRequest,
        source: SourceAttendance,
        group_name: str,
        detail_sheet: str,
        summary_sheet: str,
        day_count: int,
    ) -> tuple[tuple[str, CellRef, str], ...]:
        base_sheets = {
            request.plan.target.detail_sheet.casefold(): detail_sheet,
            request.plan.target.summary_sheet.casefold(): summary_sheet,
        }
        values = []
        for mapping in request.plan.mappings:
            mapping_sheet = mapping.sheet_name.casefold()
            if mapping_sheet not in base_sheets:
                continue
            sheet_name = base_sheets[mapping_sheet]
            values.append(
                cls._render_mapping(
                    mapping,
                    request,
                    source.department,
                    group_name,
                    day_count,
                    sheet_name,
                )
            )
        return tuple(values)

    @classmethod
    def _global_mapping_values(
        cls, request: AttendanceRequest, source: SourceAttendance, day_count: int
    ) -> tuple[tuple[str, CellRef, str], ...]:
        base_sheets = {
            request.plan.target.detail_sheet.casefold(),
            request.plan.target.summary_sheet.casefold(),
        }
        values = []
        for mapping in request.plan.mappings:
            if mapping.sheet_name.casefold() in base_sheets:
                continue
            if request.plan.split_by_group and "{{attendance_group}}" in mapping.content_template:
                raise ValueError("非分组工作表的固定映射不能使用 {{attendance_group}}")
            values.append(
                cls._render_mapping(
                    mapping,
                    request,
                    source.department,
                    "",
                    day_count,
                    mapping.sheet_name,
                )
            )
        return tuple(values)

    @staticmethod
    def _validate_request(request: AttendanceRequest) -> _RunContext:
        try:
            _, day_count = calendar.monthrange(request.year, request.month)
        except (ValueError, calendar.IllegalMonthError) as exc:
            raise AttendanceError("年月无效") from exc
        if not request.plan.name.strip():
            raise AttendanceError("方案名称不能为空")
        if not request.source_path.is_file():
            raise AttendanceError(f"原始考勤不存在: {request.source_path}")
        if not request.plan.template_path.is_file():
            raise AttendanceError(f"模板不存在: {request.plan.template_path}")
        if request.source_path.suffix.lower() != ".xlsx":
            raise AttendanceError("原始考勤必须是 .xlsx")
        if request.plan.template_path.suffix.lower() != ".xlsx":
            raise AttendanceError("模板必须是 .xlsx")
        if request.output_path.suffix.lower() != ".xlsx":
            raise AttendanceError("输出文件必须是 .xlsx")
        if not request.output_path.parent.is_dir():
            raise AttendanceError(f"输出目录不存在: {request.output_path.parent}")
        resolved = {
            request.source_path.resolve(),
            request.plan.template_path.resolve(),
            request.output_path.resolve(),
        }
        if len(resolved) != 3:
            raise AttendanceError("输出文件不能与原始考勤或模板相同")
        if request.plan.split_by_group and request.plan.source.attendance_group_start is None:
            raise AttendanceError("按考勤组拆分时必须配置源考勤组起始单元格")
        return _RunContext(request, day_count)

    @staticmethod
    def _check_cancel(cancel_check: CancelCheck | None) -> None:
        if cancel_check is not None and cancel_check():
            raise AttendanceCancelled("操作已取消")

    @staticmethod
    def _cleanup_staging(staging: Path) -> OSError | None:
        try:
            staging.unlink(missing_ok=True)
        except OSError as exc:
            return exc
        return None
