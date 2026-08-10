"""AttendanceService interface 测试。"""

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

    def validate_template(self, template_path, plan):
        self.validated.append((template_path, plan))

    def read_source(self, source_path, layout, day_count, cancel_check=None):
        self.read_calls.append((source_path, layout, day_count))
        return self.source

    def write_output(
        self, staging_path, plan, source, symbols, mapping_values, day_count, cancel_check=None
    ):
        self.write_calls.append(
            (staging_path, plan, source, symbols, mapping_values, day_count, cancel_check)
        )
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
    mapping_values = excel.write_calls[0][4]
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
