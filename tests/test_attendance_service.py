"""AttendanceService interface 测试。"""

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.attendance import (
    AttendanceError,
    AttendancePlan,
    AttendanceRequest,
    AttendanceService,
    CellMapping,
    CellRef,
    EmployeeGroupOverride,
    GroupSheetConfig,
    SourceLayout,
    TargetLayout,
)
from file_toolbox.core.attendance.types import EmployeeAttendance, SourceAttendance


class FakeExcel:
    def __init__(self, source: SourceAttendance) -> None:
        self.source = source
        self.validated = []
        self.read_calls = []
        self.write_calls = []
        self.write_error = None
        self.sheet_names = ("出勤明细", "考勤汇总表")

    def validate_template(self, template_path, plan):
        self.validated.append((template_path, plan))
        return self.sheet_names

    def read_source(self, source_path, layout, day_count, cancel_check=None):
        self.read_calls.append((source_path, layout, day_count))
        return self.source

    def write_output(self, staging_path, plan, prepared, cancel_check=None):
        self.write_calls.append((staging_path, plan, prepared, cancel_check))
        if self.write_error is not None:
            raise self.write_error
        staging_path.write_bytes(staging_path.read_bytes() + b"-filled")


def _plan(template: Path) -> AttendancePlan:
    return AttendancePlan(
        name="市场部",
        template_path=template,
        source=SourceLayout(
            "Sheet1", CellRef.parse("A2"), CellRef.parse("C2"), CellRef.parse("G2")
        ),
        target=TargetLayout(
            "出勤明细", CellRef.parse("C7"), CellRef.parse("D7"), "考勤汇总表", CellRef.parse("C8")
        ),
        mappings=(
            CellMapping("出勤明细", CellRef.parse("A3"), "{{year}}年{{month}}月 {{department}}"),
        ),
    )


def _request(tmp_path: Path, *, year: int = 2026, month: int = 7, overwrite: bool = False):
    source_path = tmp_path / "source.xlsx"
    template = tmp_path / "template.xlsx"
    source_path.write_bytes(b"source")
    template.write_bytes(b"template")
    return AttendanceRequest(
        plan=_plan(template),
        source_path=source_path,
        output_path=tmp_path / "output.xlsx",
        year=year,
        month=month,
        allow_overwrite=overwrite,
    )


def _source(day_count: int, employee_count: int = 1, raw: str = "正常") -> SourceAttendance:
    return SourceAttendance(
        tuple(
            EmployeeAttendance(f"张三{i + 1}", "市场部", tuple(raw for _ in range(day_count)))
            for i in range(employee_count)
        ),
        "市场部",
    )


@pytest.mark.parametrize(
    ("year", "month", "days", "delta"),
    [(2026, 2, 28, -2), (2024, 2, 29, -1), (2026, 4, 30, 0), (2026, 7, 31, 1)],
)
def test_preview_month_sizes(tmp_path, year, month, days, delta):
    request = _request(tmp_path, year=year, month=month)
    excel = FakeExcel(_source(days, employee_count=16))
    preview = AttendanceService(excel).preview(request)

    assert preview.day_count == days
    assert preview.date_column_delta == delta
    assert preview.employee_count == 16
    assert preview.extra_employee_rows == 1
    assert preview.can_generate is True
    assert excel.read_calls[0][2] == days


def test_preview_ordered_rules_mapping_and_unmatched(tmp_path):
    request = _request(tmp_path)
    records = ("正常,出差", "休息并打卡", "未知") + tuple("" for _ in range(28))
    source = SourceAttendance((EmployeeAttendance("张三", "市场部", records),), "市场部")
    preview = AttendanceService(FakeExcel(source)).preview(request)

    assert preview.status_counts["差"] == 1
    assert preview.status_counts["+"] == 1
    assert preview.can_generate is False
    assert preview.unmatched[0].employee == "张三"
    assert preview.unmatched[0].day == 3


def test_generate_writes_staging_then_promotes_and_records_history(tmp_path):
    request = _request(tmp_path)
    excel = FakeExcel(_source(31))
    history = JsonHistoryStore(tmp_path / "history")
    result = AttendanceService(excel, history).generate(request)

    assert result.output_path.read_bytes() == b"template-filled"
    staging = excel.write_calls[0][0]
    assert staging != request.output_path
    assert staging.parent == request.output_path.parent
    assert not staging.exists()
    mapping_values = excel.write_calls[0][2].groups[0].mapping_values
    assert mapping_values[0][2] == "2026年7月 市场部"
    record = history.get_records("attendance")[0]
    assert record["data"]["employee_count"] == 1


def test_generate_history_failure_returns_success_with_warning(tmp_path):
    request = _request(tmp_path)
    history = MagicMock()
    history.add_record.side_effect = OSError("history readonly")

    result = AttendanceService(FakeExcel(_source(31)), history).generate(request)

    assert request.output_path.read_bytes() == b"template-filled"
    assert result.output_path == request.output_path
    assert result.warnings == ("结果已生成，但历史记录保存失败: history readonly",)


def test_generate_does_not_replace_existing_output_on_write_failure(tmp_path):
    request = _request(tmp_path, overwrite=True)
    request.output_path.write_bytes(b"old")
    excel = FakeExcel(_source(31))
    excel.write_error = RuntimeError("COM save failed")

    with pytest.raises(AttendanceError, match="COM save failed"):
        AttendanceService(excel).generate(request)

    assert request.output_path.read_bytes() == b"old"
    assert list(tmp_path.glob(".*.tmp.xlsx")) == []
    assert request.plan.template_path.read_bytes() == b"template"
    assert request.source_path.read_bytes() == b"source"


def test_generate_requires_explicit_overwrite(tmp_path):
    request = _request(tmp_path)
    request.output_path.write_bytes(b"old")
    with pytest.raises(AttendanceError, match="确认覆盖"):
        AttendanceService(FakeExcel(_source(31))).generate(request)
    assert request.output_path.read_bytes() == b"old"


def test_generate_blocks_unmatched(tmp_path):
    request = _request(tmp_path)
    with pytest.raises(AttendanceError, match="未匹配"):
        AttendanceService(FakeExcel(_source(31, raw="未知"))).generate(request)
    assert not request.output_path.exists()


def test_request_rejects_same_output_as_template(tmp_path):
    request = _request(tmp_path)
    bad = AttendanceRequest(
        plan=request.plan,
        source_path=request.source_path,
        output_path=request.plan.template_path,
        year=2026,
        month=7,
    )
    with pytest.raises(AttendanceError, match="不能与"):
        AttendanceService(FakeExcel(_source(31))).preview(bad)


def test_preview_partitions_attendance_groups_and_allocates_sheet_pairs(tmp_path):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
        mappings=(
            CellMapping(
                "出勤明细",
                CellRef.parse("A3"),
                "{{attendance_group}} {{department}} {{month}}月",
            ),
        ),
    )
    request = replace(request, plan=plan)
    source = SourceAttendance(
        (
            EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(31)), "售后组"),
            EmployeeAttendance("李四", "市场部", tuple("正常" for _ in range(31)), "管理组"),
            EmployeeAttendance("王五", "市场部", tuple("正常" for _ in range(31)), "售后组"),
        ),
        "市场部",
    )
    excel = FakeExcel(source)

    result = AttendanceService(excel).generate(request)

    assert result.group_counts == {"售后组": 2, "管理组": 1}
    assert result.target_sheets == {
        "售后组": ("出勤明细-售后组", "考勤汇总表-售后组"),
        "管理组": ("出勤明细-管理组", "考勤汇总表-管理组"),
    }
    prepared = excel.write_calls[0][2]
    assert [group.source.employees[0].name for group in prepared.groups] == ["张三", "李四"]
    assert prepared.groups[0].mapping_values[0][2] == "售后组 市场部 7月"


def test_preview_rejects_blank_attendance_group(tmp_path):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
    )
    request = replace(request, plan=plan)

    with pytest.raises(AttendanceError, match="张三1.*缺少考勤组"):
        AttendanceService(FakeExcel(_source(31))).preview(request)


def test_unmatched_records_include_group_for_duplicate_employee_names(tmp_path):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
    )
    request = replace(request, plan=plan)
    records = ("未知",) + tuple("正常" for _ in range(30))
    source = SourceAttendance(
        (
            EmployeeAttendance("张三", "市场部", records, "售后组"),
            EmployeeAttendance("张三", "市场部", records, "管理组"),
        ),
        "市场部",
    )

    preview = AttendanceService(FakeExcel(source)).preview(request)

    assert [item.attendance_group for item in preview.unmatched] == ["售后组", "管理组"]


def test_group_sheet_names_are_sanitized_and_do_not_collide(tmp_path):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
    )
    request = replace(request, plan=plan)
    source = SourceAttendance(
        (EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(31)), "管理/组"),),
        "市场部",
    )
    excel = FakeExcel(source)
    excel.sheet_names = ("出勤明细", "考勤汇总表", "出勤明细-管理_组")

    preview = AttendanceService(excel).preview(request)

    assert preview.target_sheets["管理/组"] == (
        "出勤明细-管理_组 (2)",
        "考勤汇总表-管理_组",
    )


def test_group_sheet_names_do_not_reuse_31_character_base_names(tmp_path):
    request = _request(tmp_path)
    detail_base = "D" * 31
    summary_base = "S" * 31
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
        target=replace(
            request.plan.target,
            detail_sheet=detail_base,
            summary_sheet=summary_base,
        ),
    )
    request = replace(request, plan=plan)
    source = SourceAttendance(
        (EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(31)), "管理组"),),
        "市场部",
    )
    excel = FakeExcel(source)
    excel.sheet_names = (detail_base, summary_base)

    preview = AttendanceService(excel).preview(request)

    assert preview.target_sheets["管理组"] == (
        f"{'D' * 27} (2)",
        f"{'S' * 27} (2)",
    )


def test_group_mappings_match_base_sheet_names_case_insensitively(tmp_path):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
        target=replace(
            request.plan.target,
            detail_sheet="Detail",
            summary_sheet="Summary",
        ),
        mappings=(CellMapping("detail", CellRef.parse("A1"), "{{attendance_group}}"),),
    )
    request = replace(request, plan=plan)
    source = SourceAttendance(
        (EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(31)), "管理组"),),
        "市场部",
    )
    excel = FakeExcel(source)
    excel.sheet_names = ("Detail", "Summary")

    AttendanceService(excel).generate(request)

    prepared = excel.write_calls[0][2]
    assert prepared.groups[0].mapping_values == (("Detail-管理组", CellRef.parse("A1"), "管理组"),)
    assert prepared.global_mapping_values == ()


def test_group_mode_rejects_group_variable_on_global_sheet(tmp_path):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
        mappings=(CellMapping("封面", CellRef.parse("A1"), "{{attendance_group}}"),),
    )
    request = replace(request, plan=plan)
    source = SourceAttendance(
        (EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(31)), "管理组"),),
        "市场部",
    )

    with pytest.raises(AttendanceError, match="非分组工作表"):
        AttendanceService(FakeExcel(source)).preview(request)


def test_employee_override_moves_one_person_and_preserves_source_order(tmp_path):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
        employee_group_overrides=(EmployeeGroupOverride("张三", "售后组", "管理组"),),
        group_sheet_configs=(GroupSheetConfig("管理组", "管理明细", "管理汇总"),),
    )
    request = replace(request, plan=plan)
    source = SourceAttendance(
        (
            EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(31)), "售后组"),
            EmployeeAttendance("李四", "市场部", tuple("正常" for _ in range(31)), "售后组"),
            EmployeeAttendance("王五", "市场部", tuple("正常" for _ in range(31)), "管理组"),
        ),
        "市场部",
    )
    excel = FakeExcel(source)

    result = AttendanceService(excel).generate(request)

    assert result.group_counts == {"管理组": 2, "售后组": 1}
    prepared = excel.write_calls[0][2]
    assert [group.attendance_group for group in prepared.groups] == ["管理组", "售后组"]
    assert [employee.name for employee in prepared.groups[0].source.employees] == ["张三", "王五"]
    assert result.target_sheets["管理组"] == ("管理明细", "管理汇总")
    assert [
        (employee.employee_name, employee.source_group, employee.target_group)
        for employee in prepared.preview.employees
    ] == [
        ("张三", "售后组", "管理组"),
        ("李四", "售后组", "售后组"),
        ("王五", "管理组", "管理组"),
    ]


@pytest.mark.parametrize(
    ("employees", "override", "message"),
    [
        (
            (
                EmployeeAttendance("张三", "市场部", ("正常",), "售后组"),
                EmployeeAttendance("张三", "市场部", ("正常",), "售后组"),
            ),
            EmployeeGroupOverride("张三", "售后组", "管理组"),
            "同组同名歧义",
        ),
        (
            (EmployeeAttendance("张三", "市场部", ("正常",), "售后组"),),
            EmployeeGroupOverride("李四", "售后组", "管理组"),
            "未找到员工",
        ),
    ],
)
def test_employee_override_rejects_ambiguous_or_missing_employee(
    tmp_path, employees, override, message
):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
        employee_group_overrides=(override,),
    )
    request = replace(request, plan=plan)

    with pytest.raises(AttendanceError, match=message):
        AttendanceService(FakeExcel(SourceAttendance(employees, "市场部"))).preview(request)


def test_unmatched_records_keep_original_group_after_same_name_moves(tmp_path):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
        employee_group_overrides=(
            EmployeeGroupOverride("张三", "A组", "C组"),
            EmployeeGroupOverride("张三", "B组", "C组"),
        ),
    )
    request = replace(request, plan=plan)
    source = SourceAttendance(
        (
            EmployeeAttendance("张三", "市场部", ("A组异常",), "A组"),
            EmployeeAttendance("张三", "市场部", ("B组异常",), "B组"),
        ),
        "市场部",
    )

    preview = AttendanceService(FakeExcel(source)).preview(request)

    assert [item.source_group for item in preview.unmatched] == ["A组", "B组"]
    assert [item.attendance_group for item in preview.unmatched] == ["C组", "C组"]


def test_explicit_sheet_names_win_and_automatic_names_avoid_them(tmp_path):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
        group_sheet_configs=(GroupSheetConfig("管理组", "出勤明细-售后组", "管理组自定义汇总"),),
    )
    request = replace(request, plan=plan)
    source = SourceAttendance(
        (
            EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(31)), "售后组"),
            EmployeeAttendance("李四", "市场部", tuple("正常" for _ in range(31)), "管理组"),
        ),
        "市场部",
    )

    preview = AttendanceService(FakeExcel(source)).preview(request)

    assert preview.target_sheets["管理组"] == ("出勤明细-售后组", "管理组自定义汇总")
    assert preview.target_sheets["售后组"][0] == "出勤明细-售后组 (2)"


@pytest.mark.parametrize("sheet_name", ["坏/名称", "A" * 32, "'首尾引号'"])
def test_explicit_sheet_names_reject_invalid_excel_names(tmp_path, sheet_name):
    request = _request(tmp_path)
    plan = replace(
        request.plan,
        split_by_group=True,
        source=replace(request.plan.source, attendance_group_start=CellRef.parse("B2")),
        group_sheet_configs=(GroupSheetConfig("管理组", sheet_name, "管理汇总"),),
    )
    request = replace(request, plan=plan)
    source = SourceAttendance(
        (EmployeeAttendance("张三", "市场部", tuple("正常" for _ in range(31)), "管理组"),),
        "市场部",
    )

    with pytest.raises(AttendanceError, match="Sheet 名"):
        AttendanceService(FakeExcel(source)).preview(request)
