"""AttendanceService 请求校验、取消检查点与暂存清理路径的契约测试。"""

from dataclasses import replace
from pathlib import Path

import pytest

from file_toolbox.core.attendance import (
    AttendanceCancelled,
    AttendanceError,
    AttendancePlan,
    AttendanceRequest,
    AttendanceService,
    CellRef,
    EmployeeGroupOverride,
    GroupSheetConfig,
    RosterConfig,
    RosterLayout,
    SourceLayout,
    TargetLayout,
)
from file_toolbox.core.attendance.types import EmployeeAttendance, SourceAttendance


class FakeExcel:
    """只在 cancel/异常注入点可配置的最小 Excel seam。"""

    def __init__(self, source: SourceAttendance, *, write_error: Exception | None = None) -> None:
        self.source = source
        self.write_error = write_error
        self.sheet_names = ("出勤明细", "考勤汇总表")

    def validate_template(self, template_path, plan):
        return self.sheet_names

    def read_source(self, source_path, layout, day_count, cancel_check=None):
        if cancel_check is not None and cancel_check():
            raise InterruptedError("操作已取消")
        return self.source

    def read_roster(self, roster_path, layout, cancel_check=None):
        raise AssertionError("本文件不覆盖名单读取")

    def write_output(self, staging_path, plan, prepared, cancel_check=None):
        if self.write_error is not None:
            raise self.write_error
        staging_path.write_bytes(b"template-filled")


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
    )


def _paths(
    tmp_path: Path, *, source_name: str = "source.xlsx", template_name: str = "template.xlsx"
):
    source = tmp_path / source_name
    template = tmp_path / template_name
    source.write_bytes(b"source")
    template.write_bytes(b"template")
    return source, template


def _request(tmp_path: Path, plan: AttendancePlan | None = None, **overrides) -> AttendanceRequest:
    source, template = _paths(tmp_path)
    return AttendanceRequest(
        plan=plan or _plan(template),
        source_path=source,
        output_path=tmp_path / "output.xlsx",
        year=2026,
        month=7,
        **overrides,
    )


def _source() -> SourceAttendance:
    return SourceAttendance(
        (EmployeeAttendance("张三", "市场部", ("正常",) * 31),),
        "市场部",
    )


def _touch(path: Path) -> Path:
    path.write_bytes(b"stub")
    return path


def _service(tmp_path: Path, **fake_kwargs) -> tuple[AttendanceService, AttendanceRequest]:
    request = _request(tmp_path)
    service = AttendanceService(excel=FakeExcel(_source(), **fake_kwargs))
    return service, request


# --- _validate_request 的可诊断错误 ---


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda request: replace(request, month=0), "年月无效"),
        (
            lambda request: replace(request, plan=replace(request.plan, name=" ")),
            "方案名称不能为空",
        ),
        (
            lambda request: replace(
                request, source_path=_touch(request.source_path.with_suffix(".xls"))
            ),
            "原始考勤必须是 .xlsx",
        ),
        (
            lambda request: replace(
                request,
                plan=replace(
                    request.plan,
                    template_path=_touch(request.plan.template_path.with_suffix(".xls")),
                ),
            ),
            "模板必须是 .xlsx",
        ),
        (
            lambda request: replace(request, output_path=request.output_path.with_suffix(".xls")),
            "输出文件必须是 .xlsx",
        ),
    ],
)
def test_preview_rejects_invalid_requests(tmp_path, mutate, message) -> None:
    service, request = _service(tmp_path)
    request = mutate(request)

    with pytest.raises(AttendanceError, match=message):
        service.preview(request)


def test_preview_rejects_missing_source_template_and_output_dir(tmp_path) -> None:
    service, request = _service(tmp_path)

    with pytest.raises(AttendanceError, match="原始考勤不存在"):
        service.preview(replace(request, source_path=tmp_path / "不存在.xlsx"))
    with pytest.raises(AttendanceError, match="模板不存在"):
        service.preview(
            replace(request, plan=replace(request.plan, template_path=tmp_path / "不存在.xlsx"))
        )
    with pytest.raises(AttendanceError, match="输出目录不存在"):
        service.preview(replace(request, output_path=tmp_path / "不存在目录" / "out.xlsx"))


def test_preview_rejects_output_colliding_with_inputs(tmp_path) -> None:
    service, request = _service(tmp_path)

    with pytest.raises(AttendanceError, match="不能与原始考勤或模板相同"):
        service.preview(replace(request, output_path=request.source_path))


def test_roster_request_validation_errors(tmp_path) -> None:
    service, request = _service(tmp_path)
    roster_layout = RosterLayout(
        "Sheet1", CellRef.parse("A1"), CellRef.parse("B1"), CellRef.parse("C1"), CellRef.parse("D1")
    )
    roster_xlsx = tmp_path / "roster.xlsx"
    roster_xlsx.write_bytes(b"roster")
    base_roster = RosterConfig(roster_xlsx, roster_layout)

    with pytest.raises(AttendanceError, match="人员名单不存在"):
        service.preview(
            replace(
                request,
                plan=replace(
                    request.plan,
                    split_by_group=True,
                    roster=RosterConfig(tmp_path / "无.xlsx", roster_layout),
                ),
            )
        )
    with pytest.raises(AttendanceError, match="人员名单必须是 .xlsx"):
        service.preview(
            replace(
                request,
                plan=replace(
                    request.plan,
                    split_by_group=True,
                    roster=RosterConfig(_touch(tmp_path / "roster.xls"), roster_layout),
                ),
            )
        )
    with pytest.raises(AttendanceError, match="必须按名单分组输出"):
        service.preview(replace(request, plan=replace(request.plan, roster=base_roster)))
    with pytest.raises(AttendanceError, match="不能使用原始考勤人员调组"):
        service.preview(
            replace(
                request,
                plan=replace(
                    request.plan,
                    split_by_group=True,
                    roster=base_roster,
                    employee_group_overrides=(EmployeeGroupOverride("张三", "A", "B"),),
                ),
            )
        )


def test_split_mode_requires_source_group_cell(tmp_path) -> None:
    service, request = _service(tmp_path)

    with pytest.raises(AttendanceError, match="源考勤组起始单元格"):
        service.preview(replace(request, plan=replace(request.plan, split_by_group=True)))


# --- 取消检查点与暂存清理 ---


def test_preview_cancel_inside_excel_read_maps_to_cancelled(tmp_path) -> None:
    service, request = _service(tmp_path)

    with pytest.raises(AttendanceCancelled, match="操作已取消"):
        service.preview(request, cancel_check=lambda: True)


def test_generate_cancel_during_write_cleans_staging(tmp_path) -> None:
    service, request = _service(tmp_path, write_error=InterruptedError("操作已取消"))

    with pytest.raises(AttendanceCancelled, match="操作已取消"):
        service.generate(request)

    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".output.")]
    assert leftovers == []


def test_generate_cancel_with_failing_cleanup_reports_both(tmp_path) -> None:
    request = _request(tmp_path)
    service = AttendanceService(excel=_UndeletableStagingExcel(_source()))

    with pytest.raises(AttendanceCancelled, match="临时文件清理失败"):
        service.generate(request)


class _UndeletableStagingExcel(FakeExcel):
    """取消同时把暂存副本变成不可 unlink 的目录,制造清理失败路径。"""

    def write_output(self, staging_path, plan, prepared, cancel_check=None) -> None:
        staging_path.unlink()
        staging_path.mkdir()
        raise InterruptedError("操作已取消")


def test_generate_write_failure_wraps_and_cleans_staging(tmp_path) -> None:
    service, request = _service(tmp_path, write_error=RuntimeError("Excel 崩溃"))

    with pytest.raises(AttendanceError, match="Excel 崩溃"):
        service.generate(request)

    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".output.")]
    assert leftovers == []


def test_generate_preserves_attendance_error_as_is(tmp_path) -> None:
    service, request = _service(tmp_path, write_error=AttendanceError("自定义业务错误"))

    with pytest.raises(AttendanceError, match="自定义业务错误"):
        service.generate(request)


def test_generate_rejects_empty_staging_copy(tmp_path) -> None:
    request = _request(tmp_path)
    service = AttendanceService(excel=_EmptyWriteExcel(_source()))

    with pytest.raises(AttendanceError, match="未生成有效的结果副本"):
        service.generate(request)


class _EmptyWriteExcel(FakeExcel):
    def write_output(self, staging_path, plan, prepared, cancel_check=None) -> None:
        staging_path.write_bytes(b"")


def test_cleanup_staging_reports_oserror_for_undeletable_target(tmp_path) -> None:
    error = AttendanceService._cleanup_staging(tmp_path)

    assert isinstance(error, OSError)


# --- 人员调组与分组 Sheet 分配的错误 ---


def _grouped_plan(template: Path, **overrides) -> AttendancePlan:
    base = replace(
        _plan(template),
        split_by_group=True,
        source=SourceLayout(
            "Sheet1",
            CellRef.parse("A2"),
            CellRef.parse("C2"),
            CellRef.parse("G2"),
            CellRef.parse("B2"),
        ),
    )
    return replace(base, **overrides)


def _grouped_source() -> SourceAttendance:
    return SourceAttendance(
        (
            EmployeeAttendance("张三", "市场部", ("正常",), "售后组"),
            EmployeeAttendance("李四", "市场部", ("正常",), "管理组"),
        ),
        "市场部",
    )


def _grouped_service(tmp_path: Path, plan: AttendancePlan) -> AttendanceService:
    excel = FakeExcel(_grouped_source())
    excel.sheet_names = ("出勤明细", "考勤汇总表")
    return AttendanceService(excel=excel)


def test_duplicate_employee_override_is_rejected(tmp_path) -> None:
    _, template = _paths(tmp_path)
    plan = _grouped_plan(
        template,
        employee_group_overrides=(
            EmployeeGroupOverride("张三", "售后组", "管理组"),
            EmployeeGroupOverride("张三", "售后组", "售后组"),
        ),
    )
    service = _grouped_service(tmp_path, plan)

    with pytest.raises(AttendanceError, match="人员分组调整重复"):
        service.preview(_request(tmp_path, plan))


def test_blank_override_target_group_is_rejected(tmp_path) -> None:
    _, template = _paths(tmp_path)
    plan = _grouped_plan(
        template, employee_group_overrides=(EmployeeGroupOverride("张三", "售后组", " "),)
    )
    service = _grouped_service(tmp_path, plan)

    with pytest.raises(AttendanceError, match="输出考勤组不能为空"):
        service.preview(_request(tmp_path, plan))


def test_duplicate_group_sheet_config_is_rejected(tmp_path) -> None:
    _, template = _paths(tmp_path)
    plan = _grouped_plan(
        template,
        group_sheet_configs=(
            GroupSheetConfig("售后组", "售后明细", "售后汇总"),
            GroupSheetConfig("售后组 ", "售后明细2", "售后汇总2"),
        ),
    )
    service = _grouped_service(tmp_path, plan)

    with pytest.raises(AttendanceError, match="考勤组 Sheet 配置重复"):
        service.preview(_request(tmp_path, plan))


def test_blank_configured_sheet_name_is_rejected(tmp_path) -> None:
    _, template = _paths(tmp_path)
    plan = _grouped_plan(
        template, group_sheet_configs=(GroupSheetConfig("售后组", "", "售后汇总"),)
    )
    service = _grouped_service(tmp_path, plan)

    with pytest.raises(AttendanceError, match="明细 Sheet 名不能为空"):
        service.preview(_request(tmp_path, plan))


def test_configured_sheet_name_existing_in_template_is_rejected(tmp_path) -> None:
    _, template = _paths(tmp_path)
    plan = _grouped_plan(
        template,
        group_sheet_configs=(GroupSheetConfig("售后组", "出勤明细", "考勤汇总表"),),
    )
    service = _grouped_service(tmp_path, plan)

    with pytest.raises(AttendanceError, match="Sheet 名已存在: 出勤明细"):
        service.preview(_request(tmp_path, plan))
