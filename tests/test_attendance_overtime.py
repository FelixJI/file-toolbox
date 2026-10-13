"""指定节假日按班次截取、半小时取整及原有加班累加契约。"""

import pytest

from file_toolbox.core.attendance.overtime import add_holiday_overtime
from file_toolbox.core.attendance.types import EmployeeAttendance


@pytest.mark.parametrize(
    ("records", "days", "expected"),
    [
        (("正常(08:43,18:26)",), (1,), 9.5),
        (("下班外勤 (08:33,23:57)",), (1,), 15),
        (("正常(19:47,08:19)", "休息"), (1,), 4),
        (("正常(19:47,08:19)", "休息"), (2,), 8),
        (("正常(18:50,08:20)", "休息"), (1, 2), 13.5),
        (("正常(18:50,08:20)", "正常(18:50,08:20)", "休息"), (1, 2), 18.5),
        (("正常(18:50,08:20)", "正常(18:50,08:20)", "休息"), (2,), 13),
        (("正常(18:50,08:20)", "正常(18:50,08:20)", "休息"), (1, 2, 3), 27),
        (("上班外勤,下班外勤 (08:32,08:06)",) * 3, (1, 2, 3), 62),
        (("正常(08:00,09:48)",), (1,), 1.5),
        (("正常(08:00,10:18)",), (1,), 2),
        (("正常(08:00,08:29)",), (1,), 0),
        (("正常(08:00,08:30)",), (1, 1), 0.5),
        (("正常(08:00,08:00)", "休息"), (1, 2), 24),
        (("休息", "", "请假"), (1, 2, 3), 0),
        (("正常（08:00，09:00）",), (1,), 1),
        (("正常",), (), 0),
        (("正常(18:50,08:20)", "休息", "正常(18:50,08:20)"), (1, 3), 10),
        (("长白班:旷工\n(-)",), (1,), 0),
        (("长白班:旷工\n(-)", "休息"), (2,), 0),
        (("长白班:旷工\n（-，-）",), (1,), 0),
        (("长白班:旷工\n(-)", "长白班:正常\n(08:00,17:00)"), (2,), 9),
        (("长白班:正常\n(19:47,08:19)", "休息"), (2,), 8),
        (("长白班:迟到\n(08:30,17:00)",), (1,), 8.5),
        (("长白班:迟到\n（08：30，17：00）",), (1,), 8.5),
    ],
)
def test_holiday_shift_hours(records, days, expected):
    employee = EmployeeAttendance("张三", "部门", records, overtime_hours=(1, 2, 3))
    actual = add_holiday_overtime(employee, days)
    assert actual.overtime_hours == (1, 2, 3 + expected)
    assert employee.overtime_hours == (1, 2, 3)


@pytest.mark.parametrize("base", ["", " 1.25 ", 1.25])
def test_existing_holiday_overtime_is_added_without_rounding(base):
    employee = EmployeeAttendance(
        "张三", "部门", ("正常(08:00,09:00)",), overtime_hours=("", 2, base)
    )
    assert add_holiday_overtime(employee, (1,)).overtime_hours == (
        "",
        2,
        (float(base) if base else 0) + 1,
    )


@pytest.mark.parametrize(
    "raw",
    [
        "正常",
        "正常(08:00)",
        "正常(24:00,09:00)",
        "正常(08:60,09:00)",
        "正常(08:00,09:00)(10:00,11:00)",
        "长白班:缺卡\n(08:00,-)",
        "长白班:旷工\n(-)\n补卡 08:00",
        "长白班:缺卡\n（08：00）",
        "打卡 08:00,09:00\n补卡(10:00,11:00)",
    ],
)
def test_invalid_punches_fail_with_employee_and_day(raw):
    with pytest.raises(ValueError, match="张三.*1 日"):
        add_holiday_overtime(EmployeeAttendance("张三", "部门", (raw,)), (1,))


def test_pre_holiday_day_error_explains_overnight_scope():
    employee = EmployeeAttendance("张三", "部门", ("正常(08:00)", "休息"))
    with pytest.raises(ValueError, match=r"1 日（节假日前一日，用于跨夜班次）"):
        add_holiday_overtime(employee, (2,))


def test_holiday_day_error_keeps_original_wording():
    employee = EmployeeAttendance("张三", "部门", ("正常(08:00)",))
    with pytest.raises(ValueError, match=r"1 日节假日加班计算失败"):
        add_holiday_overtime(employee, (1,))


@pytest.mark.parametrize("base", ["未知", "NaN", "Infinity", -1])
def test_invalid_existing_overtime_is_not_silently_replaced(base):
    employee = EmployeeAttendance(
        "张三", "部门", ("正常(08:00,09:00)",), overtime_hours=(0, 0, base)
    )
    with pytest.raises(ValueError, match="原有节假日加班"):
        add_holiday_overtime(employee, (1,))


def test_missing_record_is_not_silently_ignored():
    with pytest.raises(ValueError, match="缺少当日考勤"):
        add_holiday_overtime(EmployeeAttendance("张三", "部门", ()), (1,))
