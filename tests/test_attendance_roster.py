"""人员名单协调深 module 的接口测试。"""

from pathlib import Path

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
    RosterMatchStatus,
    SourceAttendance,
    SourceLayout,
    TargetLayout,
)


def test_resolve_roster_hides_matching_order_exclusion_and_sheet_allocation() -> None:
    plan = AttendancePlan(
        name="名单",
        template_path=Path("template.xlsx"),
        source=SourceLayout(
            "Sheet1", CellRef.parse("A2"), CellRef.parse("C2"), CellRef.parse("G2")
        ),
        target=TargetLayout(
            "出勤明细",
            CellRef.parse("C7"),
            CellRef.parse("D7"),
            "考勤汇总表",
            CellRef.parse("C8"),
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
            excluded_employee_ids=("002",),
        ),
        group_sheet_configs=(
            GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表", "正式"),
            GroupSheetConfig("盛世金源", "出勤明细-劳务", "考勤汇总表-劳务", "劳务"),
        ),
    )
    roster = RosterData(
        (
            RosterEmployee("001", "张三", "市场部", "徐州中车", 1),
            RosterEmployee("002", "李四", "市场部", "盛世金源", 2),
            RosterEmployee("003", "王五", "市场部", "徐州中车", 3),
        )
    )
    source = SourceAttendance(
        (
            EmployeeAttendance("王五", "市场部", ("正常",)),
            EmployeeAttendance("张三", "旧部门", ("正常",)),
            EmployeeAttendance("额外人员", "市场部", ("正常",)),
        ),
        "",
    )

    result = resolve_roster(
        source,
        roster,
        plan,
        ("出勤明细", "考勤汇总表", "出勤明细-劳务", "考勤汇总表-劳务"),
        1,
    )

    assert result.errors == ()
    assert [employee.name for employee in result.source.employees] == ["张三", "王五"]
    assert result.target_sheets == {"徐州中车": ("出勤明细", "考勤汇总表")}
    assert result.remove_sheet_pairs == (("出勤明细-劳务", "考勤汇总表-劳务"),)
    assert result.employees[1].match_status is RosterMatchStatus.EXCLUDED
    assert any("部门不一致" in warning for warning in result.warnings)
    assert any("额外人员" in warning for warning in result.warnings)
