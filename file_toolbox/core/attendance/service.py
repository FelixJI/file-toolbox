"""考勤汇总深 module：预览与安全生成。"""

from __future__ import annotations

import calendar
import os
import re
import shutil
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
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
    AttendancePlan,
    AttendancePreview,
    AttendanceRequest,
    AttendanceResult,
    CellMapping,
    CellRef,
    EmployeeAttendance,
    EmployeeGroupPreview,
    GroupSheetConfig,
    PreparedAttendance,
    PreparedGroup,
    RosterData,
    RosterEmployee,
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


@dataclass(frozen=True)
class _RosterResolution:
    source: SourceAttendance
    employees: tuple[EmployeeGroupPreview, ...]
    target_sheets: dict[str, tuple[str, str]]
    group_aliases: dict[str, str]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    excluded_count: int
    remove_sheet_pairs: tuple[tuple[str, str], ...]


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
        if not prepared.preview.can_generate:
            if prepared.preview.errors:
                raise AttendanceError("；".join(prepared.preview.errors[:3]))
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
            warnings=prepared.preview.warnings,
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
                        "roster": (
                            str(request.plan.roster.workbook_path)
                            if request.plan.roster is not None
                            else None
                        ),
                        "excluded_count": prepared.preview.excluded_count,
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
                    warnings=(
                        *result.warnings,
                        f"结果已生成，但历史记录保存失败: {exc}",
                    ),
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
            roster_data = (
                self._excel.read_roster(
                    request.plan.roster.workbook_path,
                    request.plan.roster.layout,
                    cancel_check,
                )
                if request.plan.roster is not None
                else None
            )
        except InterruptedError as exc:
            raise AttendanceCancelled("操作已取消") from exc
        except (OSError, ValueError) as exc:
            raise AttendanceError(str(exc)) from exc

        errors: tuple[str, ...] = ()
        warnings: tuple[str, ...] = ()
        excluded_count = 0
        remove_sheet_pairs: tuple[tuple[str, str], ...] = ()
        group_aliases: dict[str, str] = {}
        if roster_data is not None:
            resolution = self._reconcile_roster(
                source, roster_data, request.plan, template_sheets, context.day_count
            )
            source = resolution.source
            employee_previews = resolution.employees
            target_sheets = resolution.target_sheets
            group_aliases = resolution.group_aliases
            errors = resolution.errors
            warnings = resolution.warnings
            excluded_count = resolution.excluded_count
            remove_sheet_pairs = resolution.remove_sheet_pairs
            employee_groups = self._partition_employees(source, True)
        else:
            source, employee_previews = self._apply_employee_group_overrides(source, request.plan)
            employee_groups = self._partition_employees(source, request.plan.split_by_group)
            target_sheets = self._allocate_target_sheets(
                tuple(employee_groups), request, template_sheets
            )
        unmatched: list[UnmatchedAttendance] = []
        counts: Counter[str] = Counter()
        prepared_groups: list[PreparedGroup] = []
        try:
            for group_name, employees in employee_groups.items():
                departments = {
                    employee.department.strip()
                    for employee in employees
                    if employee.department.strip()
                }
                group_department = next(iter(departments), "") if len(departments) == 1 else ""
                group_source = SourceAttendance(tuple(employees), group_department)
                symbols = self._classify_group(group_source, compiled, counts, unmatched)
                detail_sheet, summary_sheet = target_sheets[group_name]
                mapping_values = self._group_mapping_values(
                    request,
                    group_source,
                    group_name,
                    detail_sheet,
                    summary_sheet,
                    context.day_count,
                    group_aliases.get(group_name, ""),
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
            if request.plan.split_by_group or request.plan.roster is not None
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
            employees=employee_previews,
            errors=errors,
            warnings=warnings,
            excluded_count=excluded_count,
            roster_path=(
                request.plan.roster.workbook_path if request.plan.roster is not None else None
            ),
        )
        return PreparedAttendance(
            groups=tuple(prepared_groups),
            preview=preview,
            global_mapping_values=global_mapping_values,
            remove_sheet_pairs=remove_sheet_pairs,
            roster_mode=request.plan.roster is not None,
        )

    @classmethod
    def _reconcile_roster(
        cls,
        source: SourceAttendance,
        roster: RosterData,
        plan: AttendancePlan,
        template_sheets: tuple[str, ...],
        day_count: int,
    ) -> _RosterResolution:
        errors: list[str] = []
        warnings: list[str] = []
        roster_config = plan.roster
        if roster_config is None:
            raise AssertionError("名单 reconciliation 需要 roster 配置")

        employee_id_rows: dict[str, int] = {}
        name_rows: dict[str, int] = {}
        roster_names: set[str] = set()
        group_names: dict[str, str] = {}
        group_members: dict[str, list[RosterEmployee]] = {}
        for roster_entry in roster.employees:
            employee_id_key = roster_entry.employee_id.strip().casefold()
            name_key = roster_entry.name.strip()
            group_key = roster_entry.roster_group.strip().casefold()
            previous_id_row = employee_id_rows.get(employee_id_key)
            if previous_id_row is not None:
                errors.append(
                    f"人员名单工号重复: {roster_entry.employee_id}（第 {previous_id_row}/{roster_entry.source_row} 行）"
                )
            else:
                employee_id_rows[employee_id_key] = roster_entry.source_row
            previous_name_row = name_rows.get(name_key)
            if previous_name_row is not None:
                errors.append(
                    f"人员名单姓名重复: {roster_entry.name}（第 {previous_name_row}/{roster_entry.source_row} 行）"
                )
            else:
                name_rows[name_key] = roster_entry.source_row
            roster_names.add(name_key)
            group_names.setdefault(group_key, roster_entry.roster_group.strip())
            group_members.setdefault(group_key, []).append(roster_entry)

        raw_by_name: dict[str, EmployeeAttendance] = {}
        duplicate_raw_names: set[str] = set()
        for source_employee in source.employees:
            name_key = source_employee.name.strip()
            if name_key in raw_by_name:
                duplicate_raw_names.add(name_key)
            else:
                raw_by_name[name_key] = source_employee
        for name in sorted(duplicate_raw_names):
            errors.append(f"原始考勤姓名重复，无法匹配名单: {name}")

        template_by_key = {name.casefold(): name for name in template_sheets}
        configs: dict[str, GroupSheetConfig] = {}
        for sheet_config in plan.group_sheet_configs:
            key = sheet_config.attendance_group.strip().casefold()
            if key in configs:
                errors.append(f"名单分组映射重复: {sheet_config.attendance_group}")
            else:
                configs[key] = sheet_config

        target_sheets: dict[str, tuple[str, str]] = {}
        group_aliases: dict[str, str] = {}
        claimed_sheets: set[str] = set()
        claimed_aliases: set[str] = set()
        for group_key, group_name in group_names.items():
            mapped_config = configs.get(group_key)
            if mapped_config is None:
                errors.append(f"名单分组缺少 Sheet 映射: {group_name}")
                target_sheets[group_name] = ("", "")
                group_aliases[group_name] = ""
                continue
            alias = mapped_config.group_alias.strip()
            if not alias:
                errors.append(f"名单分组“{group_name}”的输出别名不能为空")
            elif alias.casefold() in claimed_aliases:
                errors.append(f"名单分组输出别名重复: {alias}")
            else:
                claimed_aliases.add(alias.casefold())
            resolved_names: list[str] = []
            for label, configured_name in (
                ("明细", mapped_config.detail_sheet),
                ("汇总", mapped_config.summary_sheet),
            ):
                actual = template_by_key.get(configured_name.strip().casefold())
                if actual is None:
                    errors.append(
                        f"名单分组“{group_name}”的{label} Sheet 不存在: {configured_name}"
                    )
                    resolved_names.append(configured_name.strip())
                else:
                    if actual.casefold() in claimed_sheets:
                        errors.append(f"多个名单分组不能共用 Sheet: {actual}")
                    claimed_sheets.add(actual.casefold())
                    resolved_names.append(actual)
            target_sheets[group_name] = (resolved_names[0], resolved_names[1])
            group_aliases[group_name] = alias

        for config_key, stale_config in configs.items():
            if config_key not in group_names:
                warnings.append(f"方案中的名单分组已不存在: {stale_config.attendance_group}")

        excluded_keys = {
            employee_id.strip().casefold()
            for employee_id in roster_config.excluded_employee_ids
            if employee_id.strip()
        }
        stale_exclusions = sorted(excluded_keys - set(employee_id_rows))
        warnings.extend(f"排除工号已不在名单中: {employee_id}" for employee_id in stale_exclusions)

        previews: list[EmployeeGroupPreview] = []
        exported: list[EmployeeAttendance] = []
        exported_group_keys: set[str] = set()
        excluded_count = 0
        for roster_employee in roster.employees:
            employee_id_key = roster_employee.employee_id.strip().casefold()
            group_key = roster_employee.roster_group.strip().casefold()
            group_name = group_names[group_key]
            alias = group_aliases.get(group_name, "")
            raw_employee = raw_by_name.get(roster_employee.name.strip())
            is_excluded = employee_id_key in excluded_keys
            if is_excluded:
                excluded_count += 1
                status = "已排除"
            elif raw_employee is None:
                status = "名单有、考勤无"
                errors.append(
                    f"名单人员缺少原始考勤: {roster_employee.name}（工号 {roster_employee.employee_id}）"
                )
            else:
                status = "已匹配"
                if (
                    raw_employee.department.strip()
                    and raw_employee.department.strip() != roster_employee.department.strip()
                ):
                    warnings.append(
                        f"部门不一致，使用名单值: {roster_employee.name} "
                        f"({raw_employee.department.strip()} → {roster_employee.department.strip()})"
                    )
            previews.append(
                EmployeeGroupPreview(
                    employee_name=roster_employee.name,
                    source_group=(raw_employee.attendance_group.strip() if raw_employee else ""),
                    target_group=group_name,
                    employee_id=roster_employee.employee_id,
                    department=roster_employee.department,
                    group_alias=alias,
                    exported=not is_excluded,
                    match_status=status,
                )
            )
            if is_excluded:
                continue
            records = raw_employee.records if raw_employee is not None else ("",) * day_count
            exported.append(
                EmployeeAttendance(
                    name=roster_employee.name,
                    department=roster_employee.department,
                    records=records,
                    attendance_group=group_name,
                    source_group=(raw_employee.attendance_group.strip() if raw_employee else ""),
                    employee_id=roster_employee.employee_id,
                    group_alias=alias,
                )
            )
            exported_group_keys.add(group_key)

        for raw_name in raw_by_name:
            if raw_name not in roster_names:
                warnings.append(f"原始考勤人员不在名单中，已忽略: {raw_name}")
        if not exported:
            errors.append("人员名单中没有可导出的人员")

        for group_key, members in group_members.items():
            departments = {
                str(employee.department).strip()
                for employee in members
                if employee.employee_id.strip().casefold() not in excluded_keys
            }
            if len(departments) > 1:
                errors.append(
                    f"名单分组“{group_names[group_key]}”包含多个部门: "
                    + "、".join(sorted(departments))
                )

        remove_sheet_pairs = tuple(
            target_sheets[group_names[group_key]]
            for group_key in group_names
            if group_key not in exported_group_keys
            and all(target_sheets.get(group_names[group_key], ()))
        )
        for group_key in group_names:
            if group_key not in exported_group_keys:
                warnings.append(f"名单分组人员全部排除，不导出: {group_names[group_key]}")
        departments = {
            exported_employee.department.strip()
            for exported_employee in exported
            if exported_employee.department.strip()
        }
        department = next(iter(departments), "") if len(departments) == 1 else ""
        active_target_sheets: dict[str, tuple[str, str]] = {}
        for exported_employee in exported:
            active_target_sheets.setdefault(
                exported_employee.attendance_group,
                target_sheets[exported_employee.attendance_group],
            )
        return _RosterResolution(
            source=SourceAttendance(tuple(exported), department),
            employees=tuple(previews),
            target_sheets=active_target_sheets,
            group_aliases=group_aliases,
            errors=tuple(dict.fromkeys(errors)),
            warnings=tuple(dict.fromkeys(warnings)),
            excluded_count=excluded_count,
            remove_sheet_pairs=remove_sheet_pairs,
        )

    @staticmethod
    def _apply_employee_group_overrides(
        source: SourceAttendance, plan: AttendancePlan
    ) -> tuple[SourceAttendance, tuple[EmployeeGroupPreview, ...]]:
        source_keys = Counter(
            (
                employee.attendance_group.strip().casefold(),
                employee.name.strip().casefold(),
            )
            for employee in source.employees
        )
        overrides: dict[tuple[str, str], str] = {}
        if plan.split_by_group:
            for override in plan.employee_group_overrides:
                key = (
                    override.source_group.strip().casefold(),
                    override.employee_name.strip().casefold(),
                )
                target_group = override.target_group.strip()
                if key in overrides:
                    raise AttendanceError(
                        f"人员分组调整重复: {override.source_group}/{override.employee_name}"
                    )
                count = source_keys[key]
                if count == 0:
                    raise AttendanceError(
                        f"人员分组调整未找到员工: {override.source_group}/{override.employee_name}"
                    )
                if count > 1:
                    raise AttendanceError(
                        f"人员分组调整存在同组同名歧义: {override.source_group}/{override.employee_name}"
                    )
                if not target_group:
                    raise AttendanceError(f"员工“{override.employee_name}”的输出考勤组不能为空")
                overrides[key] = target_group

        adjusted: list[EmployeeAttendance] = []
        previews: list[EmployeeGroupPreview] = []
        for employee in source.employees:
            source_group = employee.attendance_group.strip()
            key = (source_group.casefold(), employee.name.strip().casefold())
            target_group = overrides.get(key, source_group)
            adjusted.append(
                replace(employee, attendance_group=target_group, source_group=source_group)
            )
            previews.append(EmployeeGroupPreview(employee.name, source_group, target_group))
        return SourceAttendance(tuple(adjusted), source.department), tuple(previews)

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
                            employee.source_group.strip(),
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
        configs: dict[str, GroupSheetConfig] = {}
        for config in request.plan.group_sheet_configs:
            key = config.attendance_group.strip().casefold()
            if key in configs:
                raise AttendanceError(f"考勤组 Sheet 配置重复: {config.attendance_group}")
            configs[key] = config

        for group_name in group_names:
            configured = configs.get(group_name.casefold())
            if configured is None:
                continue
            detail = cls._reserve_configured_sheet_name(
                configured.detail_sheet, group_name, "明细", reserved
            )
            summary = cls._reserve_configured_sheet_name(
                configured.summary_sheet, group_name, "汇总", reserved
            )
            result[group_name] = (detail, summary)

        for group_name in group_names:
            if group_name in result:
                continue
            detail = cls._unique_sheet_name(f"{target.detail_sheet}-{group_name}", reserved)
            summary = cls._unique_sheet_name(f"{target.summary_sheet}-{group_name}", reserved)
            result[group_name] = (detail, summary)
        return result

    @staticmethod
    def _reserve_configured_sheet_name(
        name: str,
        group_name: str,
        label: str,
        reserved: set[str],
    ) -> str:
        value = name.strip()
        if not value:
            raise AttendanceError(f"考勤组“{group_name}”的{label} Sheet 名不能为空")
        if len(value) > 31:
            raise AttendanceError(f"考勤组“{group_name}”的{label} Sheet 名超过 31 字符")
        if _INVALID_SHEET_CHARS_RE.search(value) or value.startswith("'") or value.endswith("'"):
            raise AttendanceError(f"考勤组“{group_name}”的{label} Sheet 名包含 Excel 非法字符")
        if value.casefold() in reserved:
            raise AttendanceError(f"考勤组“{group_name}”的{label} Sheet 名已存在: {value}")
        reserved.add(value.casefold())
        return value

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
        group_alias: str = "",
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
                roster_group=attendance_group if request.plan.roster is not None else "",
                group_alias=group_alias,
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
        group_alias: str = "",
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
                    group_alias,
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
            group_tokens = ("{{attendance_group}}", "{{roster_group}}", "{{group_alias}}")
            if request.plan.split_by_group and any(
                token in mapping.content_template for token in group_tokens
            ):
                raise ValueError("非分组工作表的固定映射不能使用分组变量")
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
        if request.plan.roster is not None:
            if not request.plan.roster.workbook_path.is_file():
                raise AttendanceError(f"人员名单不存在: {request.plan.roster.workbook_path}")
            if request.plan.roster.workbook_path.suffix.lower() != ".xlsx":
                raise AttendanceError("人员名单必须是 .xlsx")
            if not request.plan.split_by_group:
                raise AttendanceError("启用人员名单时必须按名单分组输出")
            if request.plan.employee_group_overrides:
                raise AttendanceError("名单模式不能使用原始考勤人员调组")
        if request.output_path.suffix.lower() != ".xlsx":
            raise AttendanceError("输出文件必须是 .xlsx")
        if not request.output_path.parent.is_dir():
            raise AttendanceError(f"输出目录不存在: {request.output_path.parent}")
        resolved = {
            request.source_path.resolve(),
            request.plan.template_path.resolve(),
            request.output_path.resolve(),
        }
        if request.plan.roster is not None:
            resolved.add(request.plan.roster.workbook_path.resolve())
        expected_paths = 4 if request.plan.roster is not None else 3
        if len(resolved) != expected_paths:
            raise AttendanceError("输出文件不能与原始考勤或模板相同")
        if (
            request.plan.roster is None
            and request.plan.split_by_group
            and request.plan.source.attendance_group_start is None
        ):
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
