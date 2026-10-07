"""考勤表单状态的无 Qt 构建、校验、预览行与调整回收测试。

AC2/AC1 证据:方案/请求构建与关键校验不依赖 Qt;真实 legacy(v1/v2/v3)方案
样例经状态读回不丢字段;预览行回收以数据行为身份。
"""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from file_toolbox.core.attendance import (
    AttendancePlanStore,
    AttendancePreview,
    AttendanceRule,
    CellMapping,
    CellRef,
    EmployeeGroupOverride,
    EmployeeGroupPreview,
    GroupSheetConfig,
    UnmatchedAttendance,
)
from file_toolbox.core.attendance.form_state import (
    AttendanceFormState,
    GroupEmployeePreviewRow,
    GroupPreviewRow,
    MappingSelection,
    PreviewRows,
    RosterEmployeePreviewRow,
    apply_plan_to_state,
    build_plan,
    build_preview_rows,
    build_request,
    capture_preview_adjustments,
    default_form_state,
    default_output_name,
    reset_roster_fields,
)
from file_toolbox.core.attendance.types import plan_from_dict, plan_to_dict


def _state(**overrides: object) -> AttendanceFormState:
    state = default_form_state(today=date(2026, 7, 1))
    state.template_path = "template.xlsx"
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def test_default_state_matches_page_defaults():
    state = _state()

    assert state.year == 2026
    assert state.month == 7
    plan = build_plan(state)
    assert plan.source.sheet_name == "Sheet1"
    assert plan.source.name_start.address == "A2"
    assert plan.source.department_start.address == "C2"
    assert plan.source.attendance_group_start is not None
    assert plan.source.attendance_group_start.address == "B2"
    assert plan.source.detail_start.address == "G2"
    assert plan.split_by_group is True
    assert plan.target.detail_sheet == "出勤明细"
    assert plan.target.detail_matrix_start.address == "D7"
    assert plan.target.summary_sheet == "考勤汇总表"
    assert len(plan.rules) == 8
    assert plan.roster is None
    assert state.roster_sheet == "Sheet1"
    assert state.roster_group == "A1"
    assert state.fill_serial_numbers is True
    assert state.detail_employee_id == "B7"


def test_build_plan_requires_name_and_template():
    with pytest.raises(ValueError, match="方案名称不能为空"):
        build_plan(_state(plan_name=" "))
    with pytest.raises(ValueError, match="请选择汇总模板"):
        build_plan(_state(template_path=""))


def test_build_plan_validates_layout_and_rules():
    state = _state()
    state.source_sheet = " "
    with pytest.raises(ValueError, match="原始 Sheet 名不能为空"):
        build_plan(state)

    state = _state()
    state.source_name = "not-a-cell"
    with pytest.raises(ValueError, match="无效的 A1 单元格地址"):
        build_plan(state)

    state = _state(rules=())
    with pytest.raises(ValueError, match="至少需要一条判定规则"):
        build_plan(state)

    state = _state(rules=(AttendanceRule(" ", "x"),))
    with pytest.raises(ValueError, match="正则不能为空"):
        build_plan(state)


def test_build_plan_roster_fields_are_required(tmp_path):
    state = _state(roster_enabled=True, roster_path=str(tmp_path / "roster.xlsx"))
    state.roster_sheet = " "
    with pytest.raises(ValueError, match="名单 Sheet 名不能为空"):
        build_plan(state)

    state = _state(roster_enabled=True)
    with pytest.raises(ValueError, match="人员名单不能为空"):
        build_plan(state)

    state = _state(
        roster_enabled=True,
        roster_path=str(tmp_path / "roster.xlsx"),
        excluded_employee_ids=("wb002",),
    )
    plan = build_plan(state)
    assert plan.roster is not None
    assert plan.roster.excluded_employee_ids == ("wb002",)
    assert plan.split_by_group is True
    assert plan.employee_group_overrides == ()


def test_build_plan_roster_clears_legacy_overrides():
    state = _state(
        roster_enabled=True,
        roster_path="roster.xlsx",
        employee_group_overrides=(EmployeeGroupOverride("张三", "A", "B"),),
    )

    plan = build_plan(state)

    assert plan.employee_group_overrides == ()
    assert plan.split_by_group is True


def test_build_request_validation_and_normalization(tmp_path):
    state = _state()
    state.source_path = ""
    with pytest.raises(ValueError, match="请选择原始考勤"):
        build_request(state)
    state.source_path = str(tmp_path / "source.xlsx")

    state.output_dir = ""
    with pytest.raises(ValueError, match="请选择结果保存目录"):
        build_request(state)
    state.output_dir = str(tmp_path)

    state.output_name = ""
    with pytest.raises(ValueError, match="请指定结果文件名"):
        build_request(state)
    state.output_name = "子目录/结果.xlsx"
    with pytest.raises(ValueError, match="不能包含路径"):
        build_request(state)

    state.output_name = "自定义结果.xls"
    request = build_request(state, allow_overwrite=True)
    assert request.output_path == tmp_path / "自定义结果.xlsx"
    assert request.year == 2026
    assert request.month == 7
    assert request.allow_overwrite is True
    assert request.source_path == tmp_path / "source.xlsx"
    assert request.plan.template_path == Path("template.xlsx")


def test_default_output_name_sanitizes_and_falls_back():
    state = _state(plan_name="市场:部?")
    assert default_output_name(state) == "市场_部_-2026年07月考勤汇总.xlsx"

    state = _state(plan_name=" . ")
    assert default_output_name(state) == "考勤汇总-2026年07月考勤汇总.xlsx"


def test_mapping_selection_roles_follow_sheet_rename():
    summary = MappingSelection.for_sheet_name("考勤汇总表", "出勤明细", "考勤汇总表")
    assert summary.role == "summary"
    assert summary.resolved_sheet_name("出勤明细", "新汇总") == "新汇总"

    legacy = MappingSelection.for_sheet_name("封面", "出勤明细", "考勤汇总表")
    assert legacy.role == "legacy"
    assert legacy.resolved_sheet_name("改名明细", "改名汇总") == "封面"

    detail = MappingSelection.for_sheet_name("", "出勤明细", "考勤汇总表")
    assert detail.role == "detail"
    assert detail.resolved_sheet_name("改名明细", "考勤汇总表") == "改名明细"

    # 大小写不一致的 Sheet 名不匹配当前明细/汇总 → legacy(与旧选择器一致;
    # 大小写不敏感匹配发生在 service 的映射构建层)
    casefolded = MappingSelection.for_sheet_name("出勤明细", "Detail", "Summary")
    assert casefolded.role == "legacy"
    assert casefolded.resolved_sheet_name("Detail", "Summary") == "出勤明细"


def test_build_plan_mappings_use_roles_against_current_sheets():
    state = _state()
    state.mappings = (
        MappingSelection.for_sheet_name(
            "考勤汇总表", "出勤明细", "考勤汇总表", cell="A1", content="汇总标题"
        ),
        MappingSelection.for_sheet_name(
            "封面", "出勤明细", "考勤汇总表", cell="B2", content="封面标题"
        ),
    )
    state.summary_sheet = "改名汇总"

    plan = build_plan(state)

    assert [mapping.sheet_name for mapping in plan.mappings] == ["改名汇总", "封面"]
    assert plan.mappings == (
        CellMapping("改名汇总", CellRef.parse("A1"), "汇总标题"),
        CellMapping("封面", CellRef.parse("B2"), "封面标题"),
    )


def test_build_plan_skips_blank_mapping_rows():
    state = _state()
    state.mappings = (MappingSelection(cell="", content=""),)

    assert build_plan(state).mappings == ()


def test_plan_round_trip_through_state_and_store(tmp_path):
    """无 Qt 调用链:状态构建 -> 保存 -> 重新加载 -> 状态读回等价(AC1)。"""
    state = _state()
    state.split_by_group = True
    state.employee_group_overrides = (EmployeeGroupOverride("张三", "售后组", "管理组"),)
    state.group_sheet_configs = (GroupSheetConfig("管理组", "管理明细", "管理汇总", "正式"),)
    state.mappings = (
        MappingSelection.for_sheet_name(
            "封面", "出勤明细", "考勤汇总表", cell="B2", content="{{month_start}}"
        ),
    )
    state.roster_enabled = True
    state.roster_path = str(tmp_path / "roster.xlsx")
    state.excluded_employee_ids = ("wb002",)
    original = build_plan(state)

    store = AttendancePlanStore(tmp_path / "plans.json")
    store.save(original)

    restored_state = AttendanceFormState()
    apply_plan_to_state(restored_state, store.get(original.name))
    assert build_plan(restored_state) == original
    assert restored_state.roster_enabled is True
    assert restored_state.group_sheet_configs == original.group_sheet_configs
    assert restored_state.excluded_employee_ids == ("wb002",)
    # 编辑状态后再次保存/读回仍等价
    restored_state.detail_sheet = "改名明细"
    edited = build_plan(restored_state)
    store.save(edited, overwrite=True)
    again = AttendanceFormState()
    apply_plan_to_state(again, store.get(edited.name))
    assert build_plan(again) == edited


def test_legacy_schema_versions_survive_state_round_trip():
    """真实 v1/v2/v3 legacy 样例:旧已支持字段经状态读回不丢(AC1)。"""
    base = plan_to_dict(build_plan(_state(split_by_group=True)))

    v1 = {**base, "schema_version": 1}
    v1.pop("split_by_group")
    v1["source"] = {**base["source"]}
    v1["source"].pop("attendance_group_start")  # type: ignore[union-attr]
    v1_plan = plan_from_dict(v1)
    v1_state = AttendanceFormState()
    apply_plan_to_state(v1_state, v1_plan)
    assert v1_state.split_by_group is False
    # None 起始在编辑态显示为默认 B2（与旧页面一致），其余字段全部保留
    assert v1_state.source_group == "B2"
    assert build_plan(v1_state) == replace(
        v1_plan, source=replace(v1_plan.source, attendance_group_start=CellRef.parse("B2"))
    )

    v2 = {**base, "schema_version": 2}
    v2.pop("employee_group_overrides")
    v2.pop("group_sheet_configs")
    v2_plan = plan_from_dict(v2)
    v2_state = AttendanceFormState()
    apply_plan_to_state(v2_state, v2_plan)
    assert v2_state.employee_group_overrides == ()
    assert v2_state.group_sheet_configs == ()
    assert build_plan(v2_state) == v2_plan

    v3 = {**base, "schema_version": 3}
    v3.pop("roster")
    for config in v3["group_sheet_configs"]:  # type: ignore[union-attr]
        config.pop("group_alias")
    v3_plan = plan_from_dict(v3)
    v3_state = AttendanceFormState()
    apply_plan_to_state(v3_state, v3_plan)
    assert v3_state.roster_enabled is False
    assert build_plan(v3_state) == v3_plan


def test_plan_state_round_trip_rejects_unknown_fields_unchanged():
    """存储策略不变:未知字段仍被严格拒绝(不在状态层透传)。"""
    data = plan_to_dict(build_plan(_state()))
    data["unknown_field"] = "typo"
    with pytest.raises(ValueError, match="无效的考勤方案"):
        plan_from_dict(data)


def test_reset_roster_fields_restores_defaults():
    state = _state(roster_enabled=True, roster_path="roster.xlsx", roster_sheet="名单页")
    state.fill_serial_numbers = False

    reset_roster_fields(state)

    assert state.roster_path == ""
    assert state.roster_sheet == "Sheet1"
    assert state.roster_group == "A1"
    assert state.roster_department == "B1"
    assert state.roster_name == "C1"
    assert state.roster_employee_id == "D1"
    assert state.fill_serial_numbers is True
    assert state.fill_employee_ids is True
    assert state.detail_serial == "A7"
    assert state.summary_employee_id == "B8"


def _preview(**kwargs: object) -> AttendancePreview:
    defaults: dict[str, object] = {
        "employee_count": 2,
        "day_count": 31,
        "extra_employee_rows": 0,
        "date_column_delta": 1,
        "status_counts": {"√": 62},
        "unmatched": (),
    }
    defaults.update(kwargs)
    return AttendancePreview(**defaults)  # type: ignore[arg-type]


def test_build_preview_rows_roster_mode_merges_configured_groups():
    state = _state(roster_enabled=True, roster_path="roster.xlsx")
    state.group_sheet_configs = (
        GroupSheetConfig("盛世金源", "出勤明细-劳务", "考勤汇总表-劳务", "劳务"),
    )
    preview = _preview(
        group_counts={"徐州中车": 1},
        target_sheets={"徐州中车": ("出勤明细", "考勤汇总表")},
        employees=(
            EmployeeGroupPreview(
                "张三", "售后组", "徐州中车", "001", "市场部", "正式", True, "已匹配"
            ),
            EmployeeGroupPreview(
                "李四", "管理组", "盛世金源", "wb002", "市场部", "劳务", False, "已排除"
            ),
        ),
        roster_path=Path("roster.xlsx"),
    )

    rows = build_preview_rows(preview, state.group_sheet_configs)

    assert rows.roster_mode is True
    assert rows.groups == (
        GroupPreviewRow("徐州中车", "出勤明细", "考勤汇总表", "正式", 1),
        GroupPreviewRow("盛世金源", "出勤明细-劳务", "考勤汇总表-劳务", "劳务", 0),
    )
    assert rows.roster_employees[1].exported is False
    assert rows.roster_employees[0].status == "已匹配"


def test_build_preview_rows_non_roster_groups_unmatched_by_source_group():
    preview = _preview(
        group_counts={"C组": 2},
        target_sheets={"C组": ("C组明细", "C组汇总")},
        unmatched=(
            UnmatchedAttendance("张三", 2, "A组异常", "C组", "A组"),
            UnmatchedAttendance("张三", 3, "B组异常", "C组", "B组"),
        ),
        employees=(
            EmployeeGroupPreview("张三", "A组", "C组"),
            EmployeeGroupPreview("张三", "B组", "C组"),
        ),
    )

    rows = build_preview_rows(preview, ())

    assert rows.roster_mode is False
    assert rows.target_editable is True
    assert rows.group_employees[0].unmatched == "2日: A组异常"
    assert rows.group_employees[1].unmatched == "3日: B组异常"


def test_build_preview_rows_truncates_unmatched_overflow():
    preview = _preview(
        unmatched=tuple(
            UnmatchedAttendance("张三", day, f"异常{day}", "售后组") for day in range(1, 5)
        ),
        employees=(EmployeeGroupPreview("张三", "售后组", "售后组"),),
    )

    rows = build_preview_rows(preview, ())

    assert rows.group_employees[0].unmatched == "1日: 异常1；2日: 异常2；3日: 异常3；另 1 条"


def test_capture_group_adjustments_moves_and_keeps_identity_keys():
    state = _state()
    state.split_by_group = True

    capture_preview_adjustments(
        state,
        (
            GroupPreviewRow("售后组", "售后明细", "售后汇总", "", 1),
            GroupPreviewRow("管理组", "管理明细", "管理汇总", "", 1),
        ),
        (),
        (
            GroupEmployeePreviewRow("张三", "售后组 ", "管理组", ""),
            GroupEmployeePreviewRow("李四", "管理组", "管理组", ""),
        ),
    )

    # 大小写/空白不敏感的(原组, 姓名)身份;回收文本经 strip,未变化的行不产生调整
    assert state.employee_group_overrides == (EmployeeGroupOverride("张三", "售后组", "管理组"),)
    assert state.group_sheet_configs == (
        GroupSheetConfig("售后组", "售后明细", "售后汇总"),
        GroupSheetConfig("管理组", "管理明细", "管理汇总"),
    )


def test_capture_group_adjustments_rejects_same_name_conflicting_targets():
    state = _state()
    with pytest.raises(ValueError, match="同组同名员工“售后组/张三”存在不同调整"):
        capture_preview_adjustments(
            state,
            (),
            (),
            (
                GroupEmployeePreviewRow("张三", "售后组", "B组", ""),
                GroupEmployeePreviewRow("张三 ", "售后组 ", "C组", ""),
            ),
        )


def test_capture_group_adjustments_requires_names_sheets_and_targets():
    with pytest.raises(ValueError, match="第 1 个输出考勤组"):
        capture_preview_adjustments(_state(), (GroupPreviewRow(" ", "d", "s"),), (), ())
    with pytest.raises(ValueError, match="明细 Sheet 名不能为空"):
        capture_preview_adjustments(_state(), (GroupPreviewRow("A组", "", "s"),), (), ())
    with pytest.raises(ValueError, match="汇总 Sheet 名不能为空"):
        capture_preview_adjustments(_state(), (GroupPreviewRow("A组", "d", " "),), (), ())
    with pytest.raises(ValueError, match="第 1 名员工姓名"):
        capture_preview_adjustments(_state(), (), (), (GroupEmployeePreviewRow("", "A", "B", ""),))
    with pytest.raises(ValueError, match="员工“张三”的原考勤组"):
        capture_preview_adjustments(
            _state(), (), (), (GroupEmployeePreviewRow("张三", "", "B", ""),)
        )
    with pytest.raises(ValueError, match="员工“张三”的输出考勤组"):
        capture_preview_adjustments(
            _state(), (), (), (GroupEmployeePreviewRow("张三", "A", " ", ""),)
        )


def test_capture_roster_adjustments_collects_exclusions():
    state = _state(roster_enabled=True, roster_path="roster.xlsx")
    state.employee_group_overrides = (EmployeeGroupOverride("张三", "A", "B"),)
    state.group_sheet_configs = (GroupSheetConfig("旧组", "旧明细", "旧汇总"),)

    capture_preview_adjustments(
        state,
        (GroupPreviewRow("徐州中车", "出勤明细", "考勤汇总表", "正式", 1),),
        (
            RosterEmployeePreviewRow("001", "张三", "市场部", "徐州中车", "正式", True, "已匹配"),
            RosterEmployeePreviewRow(
                "wb002", "李四", "市场部", "徐州中车", "正式", False, "已排除"
            ),
        ),
        (),
    )

    assert state.excluded_employee_ids == ("wb002",)
    assert state.employee_group_overrides == ()
    assert state.group_sheet_configs == (
        GroupSheetConfig("徐州中车", "出勤明细", "考勤汇总表", "正式"),
    )


def test_capture_roster_adjustments_without_group_rows_keeps_configs():
    state = _state(roster_enabled=True, roster_path="roster.xlsx")
    state.group_sheet_configs = (GroupSheetConfig("旧组", "旧明细", "旧汇总"),)

    capture_preview_adjustments(
        state,
        (),
        (RosterEmployeePreviewRow("wb001", "张三", "市场部", "旧组", "", False, "已排除"),),
        (),
    )

    assert state.excluded_employee_ids == ("wb001",)
    assert state.group_sheet_configs == (GroupSheetConfig("旧组", "旧明细", "旧汇总"),)


def test_capture_roster_adjustments_requires_alias_and_employee_id():
    state = _state(roster_enabled=True, roster_path="roster.xlsx")
    with pytest.raises(ValueError, match="名单分组“徐州中车”的输出别名不能为空"):
        capture_preview_adjustments(state, (GroupPreviewRow("徐州中车", "d", "s", " "),), (), ())
    with pytest.raises(ValueError, match="第 1 名员工工号"):
        capture_preview_adjustments(
            state, (), (RosterEmployeePreviewRow("", "张三", "市场部", "A", "", True, ""),), ()
        )


def test_preview_rows_container_defaults():
    rows = PreviewRows(roster_mode=False, target_editable=False)
    assert rows.groups == ()
    assert rows.roster_employees == ()
    assert rows.group_employees == ()
