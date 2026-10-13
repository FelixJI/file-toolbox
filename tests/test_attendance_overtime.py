"""指定节假日按班次截取、半小时取整及原有加班累加契约。

记录缺失或无法解析的日期不参与加班计算、不抛错:异常进入返回清单
(employee/日号/原因),由上层提示并在结果表格中标黄。
"""

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
    actual, anomalies = add_holiday_overtime(employee, days)
    assert actual.overtime_hours == (1, 2, 3 + expected)
    assert employee.overtime_hours == (1, 2, 3)
    assert anomalies == ()


@pytest.mark.parametrize("base", ["", " 1.25 ", 1.25])
def test_existing_holiday_overtime_is_added_without_rounding(base):
    employee = EmployeeAttendance(
        "张三", "部门", ("正常(08:00,09:00)",), overtime_hours=("", 2, base)
    )
    actual, anomalies = add_holiday_overtime(employee, (1,))
    assert actual.overtime_hours == ("", 2, (float(base) if base else 0) + 1)
    assert anomalies == ()


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
        "正常\n(19:55)",
    ],
)
def test_invalid_holiday_punches_report_anomaly_without_raising(raw):
    employee = EmployeeAttendance("张三", "部门", (raw,), overtime_hours=(1, 2, 3))

    actual, anomalies = add_holiday_overtime(employee, (1,))

    assert actual.overtime_hours == (1, 2, 3)
    assert len(anomalies) == 1
    assert anomalies[0].employee_name == "张三"
    assert anomalies[0].day == 1
    assert "节假日加班未计算" in anomalies[0].message


def test_pre_holiday_incomplete_record_reports_anomaly_and_skips_overnight():
    employee = EmployeeAttendance("张三", "部门", ("正常\n(19:55)", "休息"))

    actual, anomalies = add_holiday_overtime(employee, (2,))

    assert actual.overtime_hours == ("", "", "")
    assert len(anomalies) == 1
    assert anomalies[0].day == 1
    assert "节假日前一日记录不全" in anomalies[0].message
    assert "无法识别上下班时间" in anomalies[0].message


def test_pre_holiday_day_anomaly_explains_overnight_scope():
    employee = EmployeeAttendance("张三", "部门", ("正常(08:00)", "休息"))

    _, anomalies = add_holiday_overtime(employee, (2,))

    assert len(anomalies) == 1
    assert anomalies[0].employee_name == "张三"
    assert anomalies[0].day == 1
    assert "未参与跨夜加班计算" in anomalies[0].message


def test_holiday_day_anomaly_keeps_original_wording():
    employee = EmployeeAttendance("张三", "部门", ("正常(08:00)",))

    _, anomalies = add_holiday_overtime(employee, (1,))

    assert len(anomalies) == 1
    assert "节假日加班未计算" in anomalies[0].message
    assert "无法识别上下班时间" in anomalies[0].message


@pytest.mark.parametrize("base", ["未知", "NaN", "Infinity", -1])
def test_invalid_existing_overtime_is_not_silently_replaced(base):
    employee = EmployeeAttendance(
        "张三", "部门", ("正常(08:00,09:00)",), overtime_hours=(0, 0, base)
    )

    actual, anomalies = add_holiday_overtime(employee, (1,))

    assert actual.overtime_hours == (0, 0, base)
    assert len(anomalies) == 1
    assert anomalies[0].day == 0
    assert "原有节假日加班不是有效时长" in anomalies[0].message
    assert "未累计" in anomalies[0].message


def test_missing_record_is_not_silently_ignored():
    employee = EmployeeAttendance("张三", "部门", (), overtime_hours=(1, 2, 3))

    actual, anomalies = add_holiday_overtime(employee, (1,))

    assert actual.overtime_hours == (1, 2, 3)
    assert anomalies[0].day == 1
    assert "缺少当日考勤记录" in anomalies[0].message


def test_missing_pre_holiday_record_reports_anomaly_for_overnight_day():
    employee = EmployeeAttendance("张三", "部门", (), overtime_hours=(1, 2, 3))

    _, anomalies = add_holiday_overtime(employee, (2,))

    assert {anomaly.day for anomaly in anomalies} == {1, 2}
    assert any("节假日前一日缺少考勤记录" in anomaly.message for anomaly in anomalies)
    assert any("缺少当日考勤记录" in anomaly.message for anomaly in anomalies)
