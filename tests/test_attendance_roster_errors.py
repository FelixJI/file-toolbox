"""人员名单协调的校验错误契约：每个可诊断错误都有稳定文案与归类。"""

from pathlib import Path

import pytest

from file_toolbox.core.attendance.roster import resolve_roster
from file_toolbox.core.attendance.types import (
    AttendancePlan,
    CellRef,
    EmployeeAttendance,
    GroupSheetConfig,
    RosterConfig,
    RosterData,
    RosterEmployee,
    RosterLayout,
    SourceAttendance,
    SourceLayout,
    TargetLayout,
)


def _plan(group_configs: tuple[GroupSheetConfig, ...]) -> AttendancePlan:
    return AttendancePlan(
        name="名单",
        template_path=Path("template.xlsx"),
        source=SourceLayout(
            "Sheet1", CellRef.parse("A2"), CellRef.parse("C2"), CellRef.parse("G2")
        ),
        target=TargetLayout(
            "出勤明细", CellRef.parse("C7"), CellRef.parse("D7"), "考勤汇总表", CellRef.parse("C8")
        ),
        split_by_group=True,
        roster=RosterConfig(
            Path("roster.xlsx"),
            RosterLayout(
                "Sheet1",
                CellRef.parse("A1"),
                CellRef.parse("B1"),
                CellRef.parse("C1"),
                CellRef.parse("D1"),
            ),
        ),
        group_sheet_configs=group_configs,
    )


def _roster(*employees: RosterEmployee) -> RosterData:
    return RosterData(tuple(employees))


def _source(*names: str) -> SourceAttendance:
    return SourceAttendance(
        tuple(EmployeeAttendance(name, "市场部", ("正常",)) for name in names),
        "市场部",
    )


def _resolve(
    plan: AttendancePlan,
    roster: RosterData,
    source: SourceAttendance,
    template_sheets: tuple[str, ...] = ("出勤明细", "考勤汇总表"),
):
    return resolve_roster(source, roster, plan, template_sheets, 1)


def test_resolve_roster_requires_roster_config() -> None:
    plan = AttendancePlan(
        name="名单",
        template_path=Path("template.xlsx"),
        source=SourceLayout(
            "Sheet1", CellRef.parse("A2"), CellRef.parse("C2"), CellRef.parse("G2")
        ),
        target=TargetLayout(
            "出勤明细", CellRef.parse("C7"), CellRef.parse("D7"), "考勤汇总表", CellRef.parse("C8")
        ),
    )
    with pytest.raises(AssertionError, match="roster 配置"):
        _resolve(plan, _roster(), _source())


def test_resolve_roster_rejects_duplicate_raw_source_names() -> None:
    plan = _plan((GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表", "正式"),))
    result = _resolve(
        plan,
        _roster(RosterEmployee("001", "张三", "市场部", "徐州中车", 1)),
        _source("张三", "张三"),
    )

    assert any("原始考勤姓名重复" in error and "张三" in error for error in result.errors)


def test_resolve_roster_rejects_duplicate_group_sheet_config() -> None:
    config = GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表", "正式")
    plan = _plan((config, GroupSheetConfig("徐州中车 ", "出勤明细", "考勤汇总表", "别名")))

    result = _resolve(
        plan, _roster(RosterEmployee("001", "张三", "市场部", "徐州中车", 1)), _source("张三")
    )

    assert any("名单分组映射重复" in error for error in result.errors)


def test_resolve_roster_rejects_blank_alias() -> None:
    plan = _plan((GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表", "  "),))
    result = _resolve(
        plan, _roster(RosterEmployee("001", "张三", "市场部", "徐州中车", 1)), _source("张三")
    )

    assert any("输出别名不能为空" in error for error in result.errors)


def test_resolve_roster_rejects_duplicate_alias_between_groups() -> None:
    plan = _plan(
        (
            GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表", "正式"),
            GroupSheetConfig("盛世金源", "出勤明细-劳务", "考勤汇总表-劳务", "正式"),
        )
    )
    roster = _roster(
        RosterEmployee("001", "张三", "市场部", "徐州中车", 1),
        RosterEmployee("002", "李四", "市场部", "盛世金源", 2),
    )

    result = _resolve(plan, roster, _source("张三", "李四"))

    assert any("输出别名重复: 正式" in error for error in result.errors)


def test_resolve_roster_reports_half_missing_sheet_pair() -> None:
    plan = _plan((GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表-劳务", "正式"),))

    result = _resolve(
        plan, _roster(RosterEmployee("001", "张三", "市场部", "徐州中车", 1)), _source("张三")
    )

    assert any("汇总 Sheet 不存在: 考勤汇总表-劳务" in error for error in result.errors)


def test_resolve_roster_rejects_blank_sheet_names() -> None:
    plan = _plan((GroupSheetConfig("徐州中车", "", "考勤汇总表", "正式"),))

    result = _resolve(
        plan, _roster(RosterEmployee("001", "张三", "市场部", "徐州中车", 1)), _source("张三")
    )

    assert any("明细 Sheet 名不能为空" in error for error in result.errors)


def test_resolve_roster_rejects_shared_sheet_between_groups() -> None:
    plan = _plan(
        (
            GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表", "正式"),
            GroupSheetConfig("盛世金源", "出勤明细", "考勤汇总表", "劳务"),
        )
    )
    roster = _roster(
        RosterEmployee("001", "张三", "市场部", "徐州中车", 1),
        RosterEmployee("002", "李四", "市场部", "盛世金源", 2),
    )

    result = _resolve(plan, roster, _source("张三", "李四"))

    assert any("不能共用 Sheet: 出勤明细" in error for error in result.errors)


def test_resolve_roster_reports_no_exportable_employees() -> None:
    plan = replace_plan_excluded(
        _plan((GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表", "正式"),)), ("001",)
    )

    result = _resolve(
        plan, _roster(RosterEmployee("001", "张三", "市场部", "徐州中车", 1)), _source("张三")
    )

    assert any("没有可导出的人员" in error for error in result.errors)
    assert result.excluded_count == 1


def replace_plan_excluded(plan: AttendancePlan, ids: tuple[str, ...]) -> AttendancePlan:
    from dataclasses import replace

    assert plan.roster is not None
    return replace(plan, roster=replace(plan.roster, excluded_employee_ids=ids))


def test_resolve_roster_rejects_mixed_department_group() -> None:
    plan = _plan((GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表", "正式"),))
    roster = _roster(
        RosterEmployee("001", "张三", "市场部", "徐州中车", 1),
        RosterEmployee("002", "李四", "事业部", "徐州中车", 2),
    )

    result = _resolve(plan, roster, _source("张三", "李四"))

    assert any(
        "包含多个部门" in error and "市场部" in error and "事业部" in error
        for error in result.errors
    )
