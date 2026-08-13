"""考勤领域类型、规则与变量测试。"""

from pathlib import Path

import pytest

from file_toolbox.core.attendance.rules import classify, compile_rules, render_content
from file_toolbox.core.attendance.types import (
    AttendancePlan,
    AttendanceRule,
    CellMapping,
    CellRef,
    EmployeeGroupOverride,
    GroupSheetConfig,
    RosterConfig,
    RosterLayout,
    SourceLayout,
    TargetLayout,
    column_letters,
    default_rules,
    plan_from_dict,
    plan_to_dict,
)


def _plan() -> AttendancePlan:
    return AttendancePlan(
        name="市场部",
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
        mappings=(CellMapping("出勤明细", CellRef.parse("A3"), "{{year}}年{{month}}月"),),
        rules=default_rules(),
    )


@pytest.mark.parametrize(
    ("address", "row", "column"),
    [("A1", 1, 1), ("D7", 7, 4), ("AG26", 26, 33), ("XFD1", 1, 16384)],
)
def test_cell_ref_round_trip(address, row, column):
    ref = CellRef.parse(address)
    assert (ref.row, ref.column) == (row, column)
    assert ref.address == address


@pytest.mark.parametrize("value", ["", "A0", "1A", "A", "$A$1", "AAAA1"])
def test_cell_ref_rejects_invalid_address(value):
    with pytest.raises(ValueError, match="无效"):
        CellRef.parse(value)


def test_column_letters_rejects_zero():
    with pytest.raises(ValueError):
        column_letters(0)


def test_plan_serialization_round_trip():
    original = _plan()
    plan = AttendancePlan(
        **{
            **original.__dict__,
            "source": SourceLayout(
                original.source.sheet_name,
                original.source.name_start,
                original.source.department_start,
                original.source.detail_start,
                CellRef.parse("B2"),
            ),
            "split_by_group": True,
            "employee_group_overrides": (EmployeeGroupOverride("张三", "售后组", "管理组"),),
            "group_sheet_configs": (GroupSheetConfig("管理组", "管理明细", "管理汇总", "正式"),),
            "roster": RosterConfig(
                workbook_path=Path("roster.xlsx"),
                layout=RosterLayout(
                    "Sheet1",
                    CellRef.parse("A1"),
                    CellRef.parse("B1"),
                    CellRef.parse("C1"),
                    CellRef.parse("D1"),
                ),
                excluded_employee_ids=("001",),
            ),
        }
    )
    assert plan_from_dict(plan_to_dict(plan)) == plan


def test_plan_from_old_dict_defaults_to_single_group_mode():
    data = plan_to_dict(_plan())
    data["schema_version"] = 1
    data.pop("split_by_group")
    source = data["source"]
    assert isinstance(source, dict)
    source.pop("attendance_group_start")

    plan = plan_from_dict(data)

    assert plan.split_by_group is False
    assert plan.source.attendance_group_start is None
    assert plan.schema_version == 4
    assert plan.roster is None


def test_v2_plan_migrates_without_manual_adjustments():
    original = _plan()
    plan = AttendancePlan(
        **{
            **original.__dict__,
            "source": SourceLayout(
                original.source.sheet_name,
                original.source.name_start,
                original.source.department_start,
                original.source.detail_start,
                CellRef.parse("B2"),
            ),
            "split_by_group": True,
        }
    )
    data = plan_to_dict(plan)
    data["schema_version"] = 2
    data.pop("employee_group_overrides")
    data.pop("group_sheet_configs")

    migrated = plan_from_dict(data)

    assert migrated.split_by_group is True
    assert migrated.source.attendance_group_start == CellRef.parse("B2")
    assert migrated.employee_group_overrides == ()
    assert migrated.group_sheet_configs == ()
    assert migrated.schema_version == 4
    assert migrated.roster is None


def test_v3_plan_migrates_without_roster_configuration():
    data = plan_to_dict(_plan())
    data["schema_version"] = 3
    data.pop("roster")
    for config in data["group_sheet_configs"]:
        config.pop("group_alias")

    migrated = plan_from_dict(data)

    assert migrated.schema_version == 4
    assert migrated.roster is None


def test_new_plan_serializes_as_v4_so_old_reader_rejects_new_semantics():
    assert plan_to_dict(_plan())["schema_version"] == 4


def test_plan_from_dict_rejects_unknown_version():
    data = plan_to_dict(_plan())
    data["schema_version"] = 99
    with pytest.raises(ValueError, match="版本"):
        plan_from_dict(data)


def test_plan_from_dict_rejects_unknown_fields():
    data = plan_to_dict(_plan())
    data["unknown_field"] = "typo"
    with pytest.raises(ValueError, match="无效的考勤方案"):
        plan_from_dict(data)


@pytest.mark.parametrize(("field", "value"), [("split_by_group", 1), ("split_by_group", "false")])
def test_plan_from_dict_keeps_boolean_fields_strict(field, value):
    data = plan_to_dict(_plan())
    data[field] = value
    with pytest.raises(ValueError, match="无效的考勤方案"):
        plan_from_dict(data)


def test_default_rule_order_handles_mixed_status():
    rules = compile_rules(default_rules())
    assert classify("正常,出差07-02到07-03", rules) == "差"
    assert classify("长白班:上班严重迟到2分钟", rules) == "迟"
    assert classify("休息并打卡\n(15:49,19:37)", rules) == "+"
    assert classify("休息\n(-)", rules) == ""
    assert classify("上班外勤,下班外勤", rules) == "√"
    assert classify("", rules) == ""
    assert classify("未知状态", rules) is None


def test_compile_rules_rejects_invalid_or_all_disabled():
    with pytest.raises(ValueError, match="无效正则"):
        compile_rules((AttendanceRule("[", "x"),))
    with pytest.raises(ValueError, match="至少"):
        compile_rules((AttendanceRule("正常", "√", enabled=False),))


def test_render_content_supports_minimal_variables():
    value = render_content(
        "{{department}} {{year}}/{{month}} {{month_start}} - {{month_end}}",
        year=2024,
        month=2,
        last_day=29,
        department="市场部",
    )
    assert value == "市场部 2024/2 2024年2月1日 - 2024年2月29日"


def test_render_content_supports_attendance_group():
    value = render_content(
        "{{department}}-{{attendance_group}}",
        year=2026,
        month=7,
        last_day=31,
        department="市场部",
        attendance_group="售后组",
    )
    assert value == "市场部-售后组"


def test_render_content_supports_roster_group_and_alias():
    value = render_content(
        "{{roster_group}}/{{group_alias}}",
        year=2026,
        month=7,
        last_day=31,
        department="市场部",
        roster_group="徐州中车",
        group_alias="正式",
    )

    assert value == "徐州中车/正式"


def test_render_content_rejects_unknown_variable():
    with pytest.raises(ValueError, match="unknown"):
        render_content("{{unknown}}", year=2026, month=7, last_day=31, department="市场部")
