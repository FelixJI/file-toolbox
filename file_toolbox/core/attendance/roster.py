"""人员名单协调深 module：在单一接口后完成校验、匹配、排序与分组。"""

from __future__ import annotations

from dataclasses import dataclass

from file_toolbox.core.attendance.types import (
    AttendancePlan,
    EmployeeAttendance,
    EmployeeGroupPreview,
    GroupSheetConfig,
    RosterData,
    RosterEmployee,
    RosterMatchStatus,
    SourceAttendance,
)


@dataclass(frozen=True)
class RosterResolution:
    """名单协调后的可导出数据及可展示诊断。"""

    source: SourceAttendance
    employees: tuple[EmployeeGroupPreview, ...]
    target_sheets: dict[str, tuple[str, str]]
    group_aliases: dict[str, str]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    excluded_count: int
    remove_sheet_pairs: tuple[tuple[str, str], ...]


def resolve_roster(
    source: SourceAttendance,
    roster: RosterData,
    plan: AttendancePlan,
    template_sheets: tuple[str, ...],
    day_count: int,
) -> RosterResolution:
    """以名单为权威来源，协调原始考勤并返回稳定顺序的导出模型。"""
    roster_config = plan.roster
    if roster_config is None:
        raise AssertionError("名单协调需要 roster 配置")

    errors: list[str] = []
    warnings: list[str] = []
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
                f"人员名单工号重复: {roster_entry.employee_id}"
                f"（第 {previous_id_row}/{roster_entry.source_row} 行）"
            )
        else:
            employee_id_rows[employee_id_key] = roster_entry.source_row
        previous_name_row = name_rows.get(name_key)
        if previous_name_row is not None:
            errors.append(
                f"人员名单姓名重复: {roster_entry.name}"
                f"（第 {previous_name_row}/{roster_entry.source_row} 行）"
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
                errors.append(f"名单分组“{group_name}”的{label} Sheet 不存在: {configured_name}")
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
            status = RosterMatchStatus.EXCLUDED
        elif raw_employee is None:
            status = RosterMatchStatus.MISSING_ATTENDANCE
            errors.append(
                f"名单人员缺少原始考勤: {roster_employee.name}"
                f"（工号 {roster_employee.employee_id}）"
            )
        else:
            status = RosterMatchStatus.MATCHED
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
                source_group=raw_employee.attendance_group.strip() if raw_employee else "",
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
                source_group=raw_employee.attendance_group.strip() if raw_employee else "",
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
            employee.department.strip()
            for employee in members
            if employee.employee_id.strip().casefold() not in excluded_keys
        }
        if len(departments) > 1:
            errors.append(
                f"名单分组“{group_names[group_key]}”包含多个部门: " + "、".join(sorted(departments))
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
    return RosterResolution(
        source=SourceAttendance(tuple(exported), department),
        employees=tuple(previews),
        target_sheets=active_target_sheets,
        group_aliases=group_aliases,
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
        excluded_count=excluded_count,
        remove_sheet_pairs=remove_sheet_pairs,
    )
