"""考勤汇总领域类型。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

_CELL_RE = re.compile(r"^([A-Za-z]{1,3})([1-9]\d*)$")
_PLAN_SCHEMA_VERSION = 3


def _column_number(letters: str) -> int:
    number = 0
    for char in letters.upper():
        number = number * 26 + ord(char) - ord("A") + 1
    return number


def column_letters(number: int) -> str:
    """把 1-based Excel 列号转换为字母。"""
    if number < 1:
        raise ValueError("Excel 列号必须大于 0")
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


@dataclass(frozen=True)
class CellRef:
    """1-based Excel A1 单元格引用。"""

    row: int
    column: int

    def __post_init__(self) -> None:
        if self.row < 1 or self.column < 1:
            raise ValueError("单元格行列必须大于 0")

    @classmethod
    def parse(cls, value: str) -> CellRef:
        match = _CELL_RE.fullmatch(value.strip())
        if match is None:
            raise ValueError(f"无效的 A1 单元格地址: {value}")
        return cls(row=int(match.group(2)), column=_column_number(match.group(1)))

    @property
    def address(self) -> str:
        return f"{column_letters(self.column)}{self.row}"

    def offset(self, *, rows: int = 0, columns: int = 0) -> CellRef:
        return CellRef(self.row + rows, self.column + columns)


@dataclass(frozen=True)
class SourceLayout:
    sheet_name: str
    name_start: CellRef
    department_start: CellRef
    detail_start: CellRef
    attendance_group_start: CellRef | None = None


@dataclass(frozen=True)
class TargetLayout:
    detail_sheet: str
    detail_name_start: CellRef
    detail_matrix_start: CellRef
    summary_sheet: str
    summary_name_start: CellRef


@dataclass(frozen=True)
class CellMapping:
    sheet_name: str
    cell: CellRef
    content_template: str


@dataclass(frozen=True)
class AttendanceRule:
    pattern: str
    output: str
    enabled: bool = True


@dataclass(frozen=True)
class EmployeeGroupOverride:
    employee_name: str
    source_group: str
    target_group: str


@dataclass(frozen=True)
class GroupSheetConfig:
    attendance_group: str
    detail_sheet: str
    summary_sheet: str


def default_rules() -> tuple[AttendanceRule, ...]:
    return (
        AttendanceRule("出差", "差"),
        AttendanceRule("旷工", "旷"),
        AttendanceRule("迟到", "迟"),
        AttendanceRule("早退", "退"),
        AttendanceRule("缺卡", "缺"),
        AttendanceRule("休息并打卡", "+"),
        AttendanceRule("休息", ""),
        AttendanceRule("外勤|正常", "√"),
    )


@dataclass(frozen=True)
class AttendancePlan:
    name: str
    template_path: Path
    source: SourceLayout
    target: TargetLayout
    mappings: tuple[CellMapping, ...] = ()
    rules: tuple[AttendanceRule, ...] = field(default_factory=default_rules)
    schema_version: int = _PLAN_SCHEMA_VERSION
    split_by_group: bool = False
    employee_group_overrides: tuple[EmployeeGroupOverride, ...] = ()
    group_sheet_configs: tuple[GroupSheetConfig, ...] = ()


@dataclass(frozen=True)
class AttendanceRequest:
    plan: AttendancePlan
    source_path: Path
    output_path: Path
    year: int
    month: int
    allow_overwrite: bool = False


@dataclass(frozen=True)
class EmployeeAttendance:
    name: str
    department: str
    records: tuple[str, ...]
    attendance_group: str = ""


@dataclass(frozen=True)
class SourceAttendance:
    employees: tuple[EmployeeAttendance, ...]
    department: str


@dataclass(frozen=True)
class UnmatchedAttendance:
    employee: str
    day: int
    raw: str
    attendance_group: str = ""


@dataclass(frozen=True)
class EmployeeGroupPreview:
    employee_name: str
    source_group: str
    target_group: str


@dataclass(frozen=True)
class AttendancePreview:
    employee_count: int
    day_count: int
    extra_employee_rows: int
    date_column_delta: int
    status_counts: Mapping[str, int]
    unmatched: tuple[UnmatchedAttendance, ...]
    group_counts: Mapping[str, int] = field(default_factory=dict)
    target_sheets: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    employees: tuple[EmployeeGroupPreview, ...] = ()

    @property
    def can_generate(self) -> bool:
        return not self.unmatched


@dataclass(frozen=True)
class AttendanceResult:
    output_path: Path
    employee_count: int
    day_count: int
    status_counts: Mapping[str, int]
    warnings: tuple[str, ...] = ()
    group_counts: Mapping[str, int] = field(default_factory=dict)
    target_sheets: Mapping[str, tuple[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparedGroup:
    attendance_group: str
    source: SourceAttendance
    symbols: tuple[tuple[str, ...], ...]
    detail_sheet: str
    summary_sheet: str
    mapping_values: tuple[tuple[str, CellRef, str], ...]


@dataclass(frozen=True)
class PreparedAttendance:
    groups: tuple[PreparedGroup, ...]
    preview: AttendancePreview
    global_mapping_values: tuple[tuple[str, CellRef, str], ...]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} 必须是对象")
    return {str(key): item for key, item in value.items()}


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是列表")
    return value


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return value.strip()


def plan_to_dict(plan: AttendancePlan) -> dict[str, object]:
    """把方案转换为可 JSON 序列化对象。"""
    return {
        "schema_version": _PLAN_SCHEMA_VERSION,
        "name": plan.name,
        "template_path": str(plan.template_path),
        "source": {
            "sheet_name": plan.source.sheet_name,
            "name_start": plan.source.name_start.address,
            "department_start": plan.source.department_start.address,
            "detail_start": plan.source.detail_start.address,
            "attendance_group_start": (
                plan.source.attendance_group_start.address
                if plan.source.attendance_group_start is not None
                else None
            ),
        },
        "target": {
            "detail_sheet": plan.target.detail_sheet,
            "detail_name_start": plan.target.detail_name_start.address,
            "detail_matrix_start": plan.target.detail_matrix_start.address,
            "summary_sheet": plan.target.summary_sheet,
            "summary_name_start": plan.target.summary_name_start.address,
        },
        "mappings": [
            {
                "sheet_name": mapping.sheet_name,
                "cell": mapping.cell.address,
                "content_template": mapping.content_template,
            }
            for mapping in plan.mappings
        ],
        "rules": [
            {"pattern": rule.pattern, "output": rule.output, "enabled": rule.enabled}
            for rule in plan.rules
        ],
        "split_by_group": plan.split_by_group,
        "employee_group_overrides": [
            {
                "employee_name": override.employee_name,
                "source_group": override.source_group,
                "target_group": override.target_group,
            }
            for override in plan.employee_group_overrides
        ],
        "group_sheet_configs": [
            {
                "attendance_group": config.attendance_group,
                "detail_sheet": config.detail_sheet,
                "summary_sheet": config.summary_sheet,
            }
            for config in plan.group_sheet_configs
        ],
    }


def plan_from_dict(value: object) -> AttendancePlan:
    """严格解析持久化方案。"""
    data = _mapping(value, "方案")
    version = data.get("schema_version")
    if version not in {1, 2, _PLAN_SCHEMA_VERSION}:
        raise ValueError("不支持的考勤方案版本")
    source_data = _mapping(data.get("source"), "source")
    target_data = _mapping(data.get("target"), "target")
    split_by_group = data.get("split_by_group", False) if version in {2, 3} else False
    if not isinstance(split_by_group, bool):
        raise ValueError("split_by_group 必须是布尔值")
    group_start_value = source_data.get("attendance_group_start") if version in {2, 3} else None
    if group_start_value is not None and not isinstance(group_start_value, str):
        raise ValueError("attendance_group_start 必须是单元格地址或 null")

    mappings: list[CellMapping] = []
    for item in _sequence(data.get("mappings", []), "mappings"):
        mapping = _mapping(item, "mapping")
        mappings.append(
            CellMapping(
                sheet_name=_text(mapping, "sheet_name"),
                cell=CellRef.parse(_text(mapping, "cell")),
                content_template=str(mapping.get("content_template", "")),
            )
        )

    rules: list[AttendanceRule] = []
    for item in _sequence(data.get("rules", []), "rules"):
        rule = _mapping(item, "rule")
        enabled = rule.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("rule.enabled 必须是布尔值")
        rules.append(
            AttendanceRule(
                pattern=_text(rule, "pattern"),
                output=str(rule.get("output", "")),
                enabled=enabled,
            )
        )

    employee_group_overrides: list[EmployeeGroupOverride] = []
    group_sheet_configs: list[GroupSheetConfig] = []
    if version == 3:
        for item in _sequence(data.get("employee_group_overrides", []), "employee_group_overrides"):
            override = _mapping(item, "employee_group_override")
            employee_group_overrides.append(
                EmployeeGroupOverride(
                    employee_name=_text(override, "employee_name"),
                    source_group=_text(override, "source_group"),
                    target_group=_text(override, "target_group"),
                )
            )
        for item in _sequence(data.get("group_sheet_configs", []), "group_sheet_configs"):
            config = _mapping(item, "group_sheet_config")
            group_sheet_configs.append(
                GroupSheetConfig(
                    attendance_group=_text(config, "attendance_group"),
                    detail_sheet=_text(config, "detail_sheet"),
                    summary_sheet=_text(config, "summary_sheet"),
                )
            )

    return AttendancePlan(
        name=_text(data, "name"),
        template_path=Path(_text(data, "template_path")),
        source=SourceLayout(
            sheet_name=_text(source_data, "sheet_name"),
            name_start=CellRef.parse(_text(source_data, "name_start")),
            department_start=CellRef.parse(_text(source_data, "department_start")),
            detail_start=CellRef.parse(_text(source_data, "detail_start")),
            attendance_group_start=(
                CellRef.parse(group_start_value) if group_start_value is not None else None
            ),
        ),
        target=TargetLayout(
            detail_sheet=_text(target_data, "detail_sheet"),
            detail_name_start=CellRef.parse(_text(target_data, "detail_name_start")),
            detail_matrix_start=CellRef.parse(_text(target_data, "detail_matrix_start")),
            summary_sheet=_text(target_data, "summary_sheet"),
            summary_name_start=CellRef.parse(_text(target_data, "summary_name_start")),
        ),
        mappings=tuple(mappings),
        rules=tuple(rules),
        split_by_group=split_by_group,
        employee_group_overrides=tuple(employee_group_overrides),
        group_sheet_configs=tuple(group_sheet_configs),
        schema_version=_PLAN_SCHEMA_VERSION,
    )
