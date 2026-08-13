"""考勤汇总领域类型。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import cast

from cattrs import Converter
from cattrs.errors import BaseValidationError, ForbiddenExtraKeysError

_CELL_RE = re.compile(r"^([A-Za-z]{1,3})([1-9]\d*)$")
_PLAN_SCHEMA_VERSION = 4

OvertimeValue = str | int | float


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
class RosterLayout:
    sheet_name: str
    group_start: CellRef
    department_start: CellRef
    name_start: CellRef
    employee_id_start: CellRef


@dataclass(frozen=True)
class RosterConfig:
    workbook_path: Path
    layout: RosterLayout
    fill_serial_numbers: bool = True
    fill_employee_ids: bool = True
    detail_serial_start: CellRef = CellRef(7, 1)
    detail_employee_id_start: CellRef = CellRef(7, 2)
    summary_serial_start: CellRef = CellRef(8, 1)
    summary_employee_id_start: CellRef = CellRef(8, 2)
    excluded_employee_ids: tuple[str, ...] = ()


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
    group_alias: str = ""


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
    roster: RosterConfig | None = None


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
    source_group: str = ""
    employee_id: str = ""
    group_alias: str = ""
    overtime_hours: tuple[OvertimeValue, OvertimeValue, OvertimeValue] = ("", "", "")


@dataclass(frozen=True)
class RosterEmployee:
    employee_id: str
    name: str
    department: str
    roster_group: str
    source_row: int


@dataclass(frozen=True)
class RosterData:
    employees: tuple[RosterEmployee, ...]


class RosterMatchStatus(StrEnum):
    """名单人员与原始考勤的匹配结果。"""

    UNKNOWN = ""
    MATCHED = "已匹配"
    EXCLUDED = "已排除"
    MISSING_ATTENDANCE = "名单有、考勤无"


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
    source_group: str = ""


@dataclass(frozen=True)
class EmployeeGroupPreview:
    employee_name: str
    source_group: str
    target_group: str
    employee_id: str = ""
    department: str = ""
    group_alias: str = ""
    exported: bool = True
    match_status: RosterMatchStatus = RosterMatchStatus.UNKNOWN


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
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    excluded_count: int = 0
    roster_path: Path | None = None

    @property
    def can_generate(self) -> bool:
        return not self.unmatched and not self.errors


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
    remove_sheet_pairs: tuple[tuple[str, str], ...] = ()
    roster_mode: bool = False


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} 必须是对象")
    return {str(key): item for key, item in value.items()}


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是列表")
    return value


def _structure_str(value: object, _: type[str]) -> str:
    if not isinstance(value, str):
        raise ValueError("值必须是字符串")
    return value


def _structure_bool(value: object, _: type[bool]) -> bool:
    if not isinstance(value, bool):
        raise ValueError("值必须是布尔值")
    return value


def _structure_path(value: object, _: type[Path]) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("路径必须是非空字符串")
    return Path(value.strip())


def _structure_cell_ref(value: object, _: type[CellRef]) -> CellRef:
    if not isinstance(value, str):
        raise ValueError("单元格地址必须是字符串")
    return CellRef.parse(value)


def _unstructure_cell_ref(value: CellRef) -> str:
    return value.address


_PLAN_CONVERTER = Converter(
    forbid_extra_keys=True,
    unstruct_collection_overrides={tuple: list},
)
_PLAN_CONVERTER.register_structure_hook(str, _structure_str)
_PLAN_CONVERTER.register_structure_hook(bool, _structure_bool)
_PLAN_CONVERTER.register_structure_hook(Path, _structure_path)
_PLAN_CONVERTER.register_structure_hook(CellRef, _structure_cell_ref)
_PLAN_CONVERTER.register_unstructure_hook(CellRef, _unstructure_cell_ref)


def plan_to_dict(plan: AttendancePlan) -> dict[str, object]:
    """使用 cattrs 把方案转换为 JSON 兼容对象。"""
    value = _PLAN_CONVERTER.unstructure(
        replace(plan, schema_version=_PLAN_SCHEMA_VERSION), AttendancePlan
    )
    return cast(dict[str, object], value)


def _migrate_plan_payload(value: object) -> dict[str, object]:
    """把历史 schema 显式迁移为 cattrs 可结构化的完整 v4 payload。"""
    data = dict(_mapping(value, "方案"))
    version = data.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version not in {1, 2, 3, 4}:
        raise ValueError("不支持的考勤方案版本")

    source = dict(_mapping(data.get("source"), "source"))
    data["source"] = source
    data.setdefault("mappings", [])
    data.setdefault("rules", [])

    if version == 1:
        data["split_by_group"] = False
        source["attendance_group_start"] = None
    else:
        data.setdefault("split_by_group", False)
        source.setdefault("attendance_group_start", None)

    if version < 3:
        data["employee_group_overrides"] = []
        data["group_sheet_configs"] = []
    else:
        data.setdefault("employee_group_overrides", [])
        data.setdefault("group_sheet_configs", [])

    if version == 3:
        configs: list[dict[str, object]] = []
        for item in _sequence(data["group_sheet_configs"], "group_sheet_configs"):
            config = dict(_mapping(item, "group_sheet_config"))
            config["group_alias"] = ""
            configs.append(config)
        data["group_sheet_configs"] = configs

    if version < 4:
        data["roster"] = None
    else:
        data.setdefault("roster", None)

    data["schema_version"] = _PLAN_SCHEMA_VERSION
    return data


def _required_text(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} 必须是非空字符串")
    return value


def _normalize_plan(plan: AttendancePlan) -> AttendancePlan:
    """应用 cattrs 之外的领域文本约束，并保持旧解析器的 strip 语义。"""
    source = replace(plan.source, sheet_name=_required_text(plan.source.sheet_name, "sheet_name"))
    target = replace(
        plan.target,
        detail_sheet=_required_text(plan.target.detail_sheet, "detail_sheet"),
        summary_sheet=_required_text(plan.target.summary_sheet, "summary_sheet"),
    )
    mappings = tuple(
        replace(mapping, sheet_name=_required_text(mapping.sheet_name, "sheet_name"))
        for mapping in plan.mappings
    )
    rules = tuple(
        replace(rule, pattern=_required_text(rule.pattern, "pattern")) for rule in plan.rules
    )
    overrides = tuple(
        replace(
            override,
            employee_name=_required_text(override.employee_name, "employee_name"),
            source_group=_required_text(override.source_group, "source_group"),
            target_group=_required_text(override.target_group, "target_group"),
        )
        for override in plan.employee_group_overrides
    )
    configs = tuple(
        replace(
            config,
            attendance_group=_required_text(config.attendance_group, "attendance_group"),
            detail_sheet=_required_text(config.detail_sheet, "detail_sheet"),
            summary_sheet=_required_text(config.summary_sheet, "summary_sheet"),
            group_alias=config.group_alias.strip(),
        )
        for config in plan.group_sheet_configs
    )

    roster = plan.roster
    if roster is not None:
        roster = replace(
            roster,
            layout=replace(
                roster.layout,
                sheet_name=_required_text(roster.layout.sheet_name, "roster.layout.sheet_name"),
            ),
            excluded_employee_ids=tuple(
                employee_id.strip()
                for employee_id in roster.excluded_employee_ids
                if employee_id.strip()
            ),
        )

    return replace(
        plan,
        name=_required_text(plan.name, "name"),
        source=source,
        target=target,
        mappings=mappings,
        rules=rules,
        employee_group_overrides=overrides,
        group_sheet_configs=configs,
        roster=roster,
        schema_version=_PLAN_SCHEMA_VERSION,
    )


def plan_from_dict(value: object) -> AttendancePlan:
    """迁移历史 schema 后使用 cattrs 严格解析持久化方案。"""
    try:
        plan = _PLAN_CONVERTER.structure(_migrate_plan_payload(value), AttendancePlan)
    except (BaseValidationError, ForbiddenExtraKeysError, KeyError, TypeError) as exc:
        raise ValueError(f"无效的考勤方案: {exc}") from exc
    return _normalize_plan(plan)
