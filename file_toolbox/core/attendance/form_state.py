"""考勤表单的无 Qt 状态:字段、方案/请求构建与预览调整校验。

页面控件只是编辑视图;本模块的 :class:`AttendanceFormState` 是表单字段、
映射/规则与预览调整(分组 Sheet 配置、人员调组、名单排除)的唯一权威状态。
方案/请求构建与关键校验可在无 Qt 环境独立调用;预览行的构建与回收以数据行
为身份,显示层排序或筛选不会改变人员身份。方案持久化继续复用
``plan_to_dict``/``plan_from_dict`` 的 v1–v4 严格迁移语义,本模块不改存储契约。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from file_toolbox.core.attendance.types import (
    AttendancePlan,
    AttendancePreview,
    AttendanceRequest,
    AttendanceRule,
    CellMapping,
    CellRef,
    EmployeeGroupOverride,
    GroupSheetConfig,
    RosterConfig,
    RosterLayout,
    SourceLayout,
    TargetLayout,
    default_rules,
)

MappingRole = Literal["detail", "summary", "legacy"]

_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _required_text(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label}不能为空")
    return value


@dataclass(frozen=True)
class MappingSelection:
    """固定单元格映射的目标 Sheet 选择:跟随明细/汇总改名或保留 legacy 名。"""

    role: MappingRole = "detail"
    legacy_sheet: str = ""
    cell: str = ""
    content: str = ""

    @classmethod
    def for_sheet_name(
        cls,
        sheet_name: str,
        detail_sheet: str,
        summary_sheet: str,
        *,
        cell: str = "",
        content: str = "",
    ) -> MappingSelection:
        """按已保存 Sheet 名解析角色:汇总一致→summary,非明细→legacy,其余→detail。"""
        selected = sheet_name.strip()
        key = selected.casefold()
        if key == summary_sheet.strip().casefold():
            return cls("summary", "", cell, content)
        if key and key != detail_sheet.strip().casefold():
            return cls("legacy", selected, cell, content)
        return cls("detail", "", cell, content)

    def resolved_sheet_name(self, detail_sheet: str, summary_sheet: str) -> str:
        """按角色解析当前 Sheet 名;detail/summary 跟随布局字段,legacy 固定。"""
        if self.role == "detail":
            return detail_sheet.strip()
        if self.role == "summary":
            return summary_sheet.strip()
        return self.legacy_sheet.strip()


@dataclass
class AttendanceFormState:
    """考勤表单的全部可编辑字段与预览调整状态(无 Qt,页面控件只做绑定)。"""

    # 文件与请求范围字段
    source_path: str = ""
    output_dir: str = ""
    output_name: str = ""
    year: int = 2000
    month: int = 1
    # 方案字段
    plan_name: str = "给定格式"
    template_path: str = ""
    # 原始考勤布局
    source_sheet: str = "Sheet1"
    source_name: str = "A2"
    source_department: str = "C2"
    source_group: str = "B2"
    source_detail: str = "G2"
    # 汇总模板布局
    detail_sheet: str = "出勤明细"
    detail_name: str = "C7"
    detail_matrix: str = "D7"
    summary_sheet: str = "考勤汇总表"
    summary_name: str = "C8"
    split_by_group: bool = True
    # 人员名单
    roster_enabled: bool = False
    roster_path: str = ""
    roster_sheet: str = "Sheet1"
    roster_group: str = "A1"
    roster_department: str = "B1"
    roster_name: str = "C1"
    roster_employee_id: str = "D1"
    fill_serial_numbers: bool = True
    fill_employee_ids: bool = True
    detail_serial: str = "A7"
    detail_employee_id: str = "B7"
    summary_serial: str = "A8"
    summary_employee_id: str = "B8"
    # 配置表内容(小表格控件编辑后同步进来)
    mappings: tuple[MappingSelection, ...] = ()
    rules: tuple[AttendanceRule, ...] = field(default_factory=default_rules)
    # 预览调整(以状态为权威,不从控件文字/固定列号回收)
    employee_group_overrides: tuple[EmployeeGroupOverride, ...] = ()
    group_sheet_configs: tuple[GroupSheetConfig, ...] = ()
    excluded_employee_ids: tuple[str, ...] = ()


def default_form_state(today: date | None = None) -> AttendanceFormState:
    """按页面默认值构建表单状态;年月默认取当前日期。"""
    current = today if today is not None else date.today()
    return AttendanceFormState(year=current.year, month=current.month)


def reset_roster_fields(state: AttendanceFormState) -> None:
    """恢复名单页字段默认值(对应旧的 _reset_roster_fields)。"""
    state.roster_path = ""
    state.roster_sheet = "Sheet1"
    state.roster_group = "A1"
    state.roster_department = "B1"
    state.roster_name = "C1"
    state.roster_employee_id = "D1"
    state.fill_serial_numbers = True
    state.fill_employee_ids = True
    state.detail_serial = "A7"
    state.detail_employee_id = "B7"
    state.summary_serial = "A8"
    state.summary_employee_id = "B8"


def apply_plan_to_state(state: AttendanceFormState, plan: AttendancePlan) -> None:
    """把已加载方案写回表单状态;映射按当前明细/汇总 Sheet 名解析角色。"""
    state.plan_name = plan.name
    state.template_path = str(plan.template_path)
    state.source_sheet = plan.source.sheet_name
    state.source_name = plan.source.name_start.address
    state.source_department = plan.source.department_start.address
    state.source_group = (
        plan.source.attendance_group_start.address
        if plan.source.attendance_group_start is not None
        else "B2"
    )
    state.source_detail = plan.source.detail_start.address
    state.detail_sheet = plan.target.detail_sheet
    state.detail_name = plan.target.detail_name_start.address
    state.detail_matrix = plan.target.detail_matrix_start.address
    state.summary_sheet = plan.target.summary_sheet
    state.summary_name = plan.target.summary_name_start.address
    state.split_by_group = plan.split_by_group
    state.employee_group_overrides = plan.employee_group_overrides
    state.group_sheet_configs = plan.group_sheet_configs
    state.excluded_employee_ids = (
        plan.roster.excluded_employee_ids if plan.roster is not None else ()
    )
    state.roster_enabled = plan.roster is not None
    if plan.roster is not None:
        state.roster_path = str(plan.roster.workbook_path)
        state.roster_sheet = plan.roster.layout.sheet_name
        state.roster_group = plan.roster.layout.group_start.address
        state.roster_department = plan.roster.layout.department_start.address
        state.roster_name = plan.roster.layout.name_start.address
        state.roster_employee_id = plan.roster.layout.employee_id_start.address
        state.fill_serial_numbers = plan.roster.fill_serial_numbers
        state.fill_employee_ids = plan.roster.fill_employee_ids
        state.detail_serial = plan.roster.detail_serial_start.address
        state.detail_employee_id = plan.roster.detail_employee_id_start.address
        state.summary_serial = plan.roster.summary_serial_start.address
        state.summary_employee_id = plan.roster.summary_employee_id_start.address
    else:
        reset_roster_fields(state)
    state.mappings = tuple(
        MappingSelection.for_sheet_name(
            mapping.sheet_name,
            plan.target.detail_sheet,
            plan.target.summary_sheet,
            cell=mapping.cell.address,
            content=mapping.content_template,
        )
        for mapping in plan.mappings
    )
    state.rules = plan.rules


def _build_mappings(state: AttendanceFormState) -> tuple[CellMapping, ...]:
    result: list[CellMapping] = []
    for row, selection in enumerate(state.mappings):
        sheet = selection.resolved_sheet_name(state.detail_sheet, state.summary_sheet)
        cell = selection.cell.strip()
        content = selection.content.strip()
        if not cell and not content:
            continue
        result.append(
            CellMapping(
                _required_text(sheet, f"第 {row + 1} 条映射的 Sheet 名"),
                CellRef.parse(cell),
                content,
            )
        )
    return tuple(result)


def _build_rules(state: AttendanceFormState) -> tuple[AttendanceRule, ...]:
    result: list[AttendanceRule] = []
    for row, rule in enumerate(state.rules):
        pattern = rule.pattern.strip()
        if not pattern:
            raise ValueError(f"第 {row + 1} 条规则的正则不能为空")
        result.append(AttendanceRule(pattern, rule.output.strip(), rule.enabled))
    if not result:
        raise ValueError("至少需要一条判定规则")
    return tuple(result)


def build_plan(state: AttendanceFormState) -> AttendancePlan:
    """从表单状态构建考勤方案;校验失败抛 ValueError,语义与页面原实现一致。"""
    name = state.plan_name.strip()
    template = state.template_path.strip()
    if not name:
        raise ValueError("方案名称不能为空")
    if not template:
        raise ValueError("请选择汇总模板")
    roster: RosterConfig | None = None
    if state.roster_enabled:
        roster_path = _required_text(state.roster_path, "人员名单")
        roster = RosterConfig(
            workbook_path=Path(roster_path),
            layout=RosterLayout(
                _required_text(state.roster_sheet, "名单 Sheet 名"),
                CellRef.parse(state.roster_group),
                CellRef.parse(state.roster_department),
                CellRef.parse(state.roster_name),
                CellRef.parse(state.roster_employee_id),
            ),
            fill_serial_numbers=state.fill_serial_numbers,
            fill_employee_ids=state.fill_employee_ids,
            detail_serial_start=CellRef.parse(state.detail_serial),
            detail_employee_id_start=CellRef.parse(state.detail_employee_id),
            summary_serial_start=CellRef.parse(state.summary_serial),
            summary_employee_id_start=CellRef.parse(state.summary_employee_id),
            excluded_employee_ids=state.excluded_employee_ids,
        )
    return AttendancePlan(
        name=name,
        template_path=Path(template),
        source=SourceLayout(
            _required_text(state.source_sheet, "原始 Sheet 名"),
            CellRef.parse(state.source_name),
            CellRef.parse(state.source_department),
            CellRef.parse(state.source_detail),
            CellRef.parse(state.source_group),
        ),
        target=TargetLayout(
            _required_text(state.detail_sheet, "明细 Sheet 名"),
            CellRef.parse(state.detail_name),
            CellRef.parse(state.detail_matrix),
            _required_text(state.summary_sheet, "汇总 Sheet 名"),
            CellRef.parse(state.summary_name),
        ),
        mappings=_build_mappings(state),
        rules=_build_rules(state),
        split_by_group=(True if roster is not None else state.split_by_group),
        employee_group_overrides=(() if roster is not None else state.employee_group_overrides),
        group_sheet_configs=state.group_sheet_configs,
        roster=roster,
    )


def build_request(
    state: AttendanceFormState, *, allow_overwrite: bool = False
) -> AttendanceRequest:
    """从表单状态构建考勤请求并校验输出文件名;失败抛 ValueError。"""
    source = state.source_path.strip()
    output_dir = state.output_dir.strip()
    output_name = state.output_name.strip()
    if not source:
        raise ValueError("请选择原始考勤")
    if not output_dir:
        raise ValueError("请选择结果保存目录")
    if not output_name:
        raise ValueError("请指定结果文件名")
    if Path(output_name).name != output_name or _INVALID_FILENAME_CHARS_RE.search(output_name):
        raise ValueError("结果文件名不能包含路径或 Windows 非法字符")
    normalized_name = Path(output_name).with_suffix(".xlsx").name
    return AttendanceRequest(
        plan=build_plan(state),
        source_path=Path(source),
        output_path=Path(output_dir) / normalized_name,
        year=state.year,
        month=state.month,
        allow_overwrite=allow_overwrite,
    )


def default_output_name(state: AttendanceFormState) -> str:
    """按方案名与年月生成默认输出文件名(非法字符替换为下划线)。"""
    plan_name = _INVALID_FILENAME_CHARS_RE.sub("_", state.plan_name.strip()).strip(" .")
    prefix = plan_name or "考勤汇总"
    return f"{prefix}-{state.year}年{state.month:02d}月考勤汇总.xlsx"


@dataclass(frozen=True)
class GroupPreviewRow:
    """分组预览行:组名/别名/人数与该组的明细、汇总 Sheet 名。"""

    attendance_group: str
    detail_sheet: str
    summary_sheet: str
    group_alias: str = ""
    employee_count: int = 0


@dataclass(frozen=True)
class RosterEmployeePreviewRow:
    """名单模式人员预览行:身份为工号,导出勾选是唯一可编辑调整。"""

    employee_id: str
    name: str
    department: str
    target_group: str
    group_alias: str
    exported: bool
    status: str


@dataclass(frozen=True)
class GroupEmployeePreviewRow:
    """非名单模式人员预览行:身份为(原考勤组, 姓名),输出考勤组可调整。"""

    name: str
    source_group: str
    target_group: str
    unmatched: str


@dataclass(frozen=True)
class PreviewRows:
    """一次预览的可编辑行集合;员工行的可编辑性跟随预览结果。"""

    roster_mode: bool
    target_editable: bool
    groups: tuple[GroupPreviewRow, ...] = ()
    roster_employees: tuple[RosterEmployeePreviewRow, ...] = ()
    group_employees: tuple[GroupEmployeePreviewRow, ...] = ()


def build_preview_rows(
    preview: AttendancePreview, group_sheet_configs: Sequence[GroupSheetConfig]
) -> PreviewRows:
    """把预览结果与对应请求快照的分组配置转成可编辑行。

    未匹配按(姓名, 原组)挂到对应员工;组配置回退使用启动预览时的快照,
    不以结果到达时的当前表单替代。
    """
    roster_mode = preview.roster_path is not None
    unmatched_by_employee: dict[tuple[str, str], list[str]] = {}
    for item in preview.unmatched:
        source_group = item.source_group or item.attendance_group
        key = (item.employee.strip().casefold(), source_group.strip().casefold())
        unmatched_by_employee.setdefault(key, []).append(f"{item.day}日: {item.raw}")

    preview_group_counts = dict(preview.group_counts)
    configured_sheets = {
        config.attendance_group.strip().casefold(): (
            config.detail_sheet,
            config.summary_sheet,
        )
        for config in group_sheet_configs
    }
    if roster_mode:
        for employee in preview.employees:
            preview_group_counts.setdefault(employee.target_group, 0)
    aliases = {employee.target_group: employee.group_alias for employee in preview.employees}
    groups: list[GroupPreviewRow] = []
    for group_name, count in preview_group_counts.items():
        detail_sheet, summary_sheet = preview.target_sheets.get(
            group_name,
            configured_sheets.get(group_name.strip().casefold(), ("", "")),
        )
        groups.append(
            GroupPreviewRow(
                attendance_group=group_name,
                detail_sheet=detail_sheet,
                summary_sheet=summary_sheet,
                group_alias=aliases.get(group_name, ""),
                employee_count=count,
            )
        )

    roster_employees: list[RosterEmployeePreviewRow] = []
    group_employees: list[GroupEmployeePreviewRow] = []
    for employee in preview.employees:
        key = (
            employee.employee_name.strip().casefold(),
            employee.source_group.strip().casefold(),
        )
        unmatched_items = unmatched_by_employee.get(key, [])
        unmatched_text = "；".join(unmatched_items[:3])
        if len(unmatched_items) > 3:
            unmatched_text += f"；另 {len(unmatched_items) - 3} 条"
        if roster_mode:
            status_text = str(employee.match_status)
            if unmatched_text:
                status_text = f"{status_text}；未识别：{unmatched_text}"
            roster_employees.append(
                RosterEmployeePreviewRow(
                    employee_id=employee.employee_id,
                    name=employee.employee_name,
                    department=employee.department,
                    target_group=employee.target_group,
                    group_alias=employee.group_alias,
                    exported=employee.exported,
                    status=status_text,
                )
            )
        else:
            group_employees.append(
                GroupEmployeePreviewRow(
                    name=employee.employee_name,
                    source_group=employee.source_group,
                    target_group=employee.target_group,
                    unmatched=unmatched_text,
                )
            )
    return PreviewRows(
        roster_mode=roster_mode,
        target_editable=bool(preview.group_counts),
        groups=tuple(groups),
        roster_employees=tuple(roster_employees),
        group_employees=tuple(group_employees),
    )


def _validate_group_rows(
    groups: Sequence[GroupPreviewRow], *, roster_mode: bool
) -> list[GroupSheetConfig]:
    configs: list[GroupSheetConfig] = []
    for row, group in enumerate(groups):
        group_name = _required_text(group.attendance_group, f"第 {row + 1} 个输出考勤组")
        alias = (
            _required_text(group.group_alias, f"名单分组“{group_name}”的输出别名")
            if roster_mode
            else ""
        )
        detail_sheet = _required_text(group.detail_sheet, f"考勤组“{group_name}”的明细 Sheet 名")
        summary_sheet = _required_text(group.summary_sheet, f"考勤组“{group_name}”的汇总 Sheet 名")
        configs.append(GroupSheetConfig(group_name, detail_sheet, summary_sheet, alias))
    return configs


def _capture_roster_adjustments(
    state: AttendanceFormState,
    groups: Sequence[GroupPreviewRow],
    employees: Sequence[RosterEmployeePreviewRow],
) -> None:
    configs = _validate_group_rows(groups, roster_mode=True)
    excluded_employee_ids: list[str] = []
    for row, employee in enumerate(employees):
        employee_id = _required_text(employee.employee_id, f"第 {row + 1} 名员工工号")
        if not employee.exported:
            excluded_employee_ids.append(employee_id)
    if configs:
        state.group_sheet_configs = tuple(configs)
    state.employee_group_overrides = ()
    state.excluded_employee_ids = tuple(excluded_employee_ids)


def _capture_group_adjustments(
    state: AttendanceFormState,
    groups: Sequence[GroupPreviewRow],
    employees: Sequence[GroupEmployeePreviewRow],
) -> None:
    configs = _validate_group_rows(groups, roster_mode=False)
    overrides: dict[tuple[str, str], EmployeeGroupOverride] = {}
    for row, employee in enumerate(employees):
        employee_name = _required_text(employee.name, f"第 {row + 1} 名员工姓名")
        source_group = _required_text(employee.source_group, f"员工“{employee_name}”的原考勤组")
        target_group = _required_text(employee.target_group, f"员工“{employee_name}”的输出考勤组")
        if source_group.casefold() == target_group.casefold():
            continue
        key = (source_group.casefold(), employee_name.casefold())
        override = EmployeeGroupOverride(employee_name, source_group, target_group)
        existing = overrides.get(key)
        if existing is not None and existing.target_group.casefold() != target_group.casefold():
            raise ValueError(f"同组同名员工“{source_group}/{employee_name}”存在不同调整")
        overrides[key] = override
    state.group_sheet_configs = tuple(configs)
    state.employee_group_overrides = tuple(overrides.values())


def capture_preview_adjustments(
    state: AttendanceFormState,
    groups: Sequence[GroupPreviewRow],
    roster_employees: Sequence[RosterEmployeePreviewRow],
    group_employees: Sequence[GroupEmployeePreviewRow],
) -> None:
    """把编辑后的预览行回收到表单状态;校验失败抛 ValueError,不修改状态。"""
    if state.roster_enabled:
        _capture_roster_adjustments(state, groups, roster_employees)
        return
    _capture_group_adjustments(state, groups, group_employees)
