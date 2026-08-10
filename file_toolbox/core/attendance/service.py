"""考勤汇总深 module：预览与安全生成。"""

from __future__ import annotations

import calendar
import os
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
    CellRef,
    PreparedAttendance,
    UnmatchedAttendance,
)

CancelCheck = Callable[[], bool]


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
                prepared.source,
                prepared.symbols,
                prepared.mapping_values,
                prepared.preview.day_count,
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
        )
        if self._history_store is not None:
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
                },
            )
        return result

    def _prepare(
        self, request: AttendanceRequest, cancel_check: CancelCheck | None
    ) -> PreparedAttendance:
        context = self._validate_request(request)
        try:
            compiled = compile_rules(request.plan.rules)
            self._excel.validate_template(request.plan.template_path, request.plan)
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

        unmatched: list[UnmatchedAttendance] = []
        symbols: list[tuple[str, ...]] = []
        counts: Counter[str] = Counter()
        for employee in source.employees:
            row: list[str] = []
            for day, raw in enumerate(employee.records, start=1):
                symbol = classify(raw, compiled)
                if symbol is None:
                    unmatched.append(UnmatchedAttendance(employee.name, day, raw))
                    row.append("")
                    continue
                row.append(symbol)
                counts[symbol or "空白"] += 1
            symbols.append(tuple(row))

        mapping_values: list[tuple[str, CellRef, str]] = []
        try:
            for mapping in request.plan.mappings:
                mapping_values.append(
                    (
                        mapping.sheet_name,
                        mapping.cell,
                        render_content(
                            mapping.content_template,
                            year=request.year,
                            month=request.month,
                            last_day=context.day_count,
                            department=source.department,
                        ),
                    )
                )
        except ValueError as exc:
            raise AttendanceError(str(exc)) from exc

        preview = AttendancePreview(
            employee_count=len(source.employees),
            day_count=context.day_count,
            extra_employee_rows=max(0, len(source.employees) - BASE_EMPLOYEE_ROWS),
            date_column_delta=context.day_count - BASE_DATE_COLUMNS,
            status_counts=dict(counts),
            unmatched=tuple(unmatched),
        )
        return PreparedAttendance(
            source=source,
            symbols=tuple(symbols),
            preview=preview,
            mapping_values=tuple(mapping_values),
        )

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
