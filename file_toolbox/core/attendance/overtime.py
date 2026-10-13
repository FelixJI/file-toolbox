"""按自然日截取打卡工时，补充指定节假日加班。"""

from __future__ import annotations

import math
import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation

from file_toolbox.core.attendance.types import EmployeeAttendance

_PUNCHES = re.compile(
    r"[（(]\s*([0-9]{1,2})[:：]([0-9]{2})\s*[,，]\s*([0-9]{1,2})[:：]([0-9]{2})\s*[）)]\s*$"
)
# 班次:状态\n(-) 这类导出格式用 “-” 表示当日无打卡；判据统一为“是否存在时间 token”：
# 有时间却解析不出唯一班次必须报错，完全没有时间才视为无打卡。
_TIME = re.compile(r"[0-9]{1,2}[:：][0-9]{2}")


def _punches(raw: str) -> tuple[int, int] | None:
    match = _PUNCHES.search(raw)
    if match is None:
        if _TIME.search(raw) or re.search(r"正常|外勤|打卡", raw):
            raise ValueError(f"无法识别上下班时间: {raw}")
        return None
    if _TIME.search(raw[: match.start()]):
        raise ValueError(f"考勤包含多段时间，无法识别唯一班次: {raw}")
    start_hour, start_minute, end_hour, end_minute = map(int, match.groups())
    if start_hour > 23 or end_hour > 23 or start_minute > 59 or end_minute > 59:
        raise ValueError(f"上下班时间超出有效范围: {raw}")
    return start_hour * 60 + start_minute, end_hour * 60 + end_minute


def add_holiday_overtime(
    employee: EmployeeAttendance, holiday_days: tuple[int, ...]
) -> EmployeeAttendance:
    """每段班次只保留节假日部分；连续节假日跨夜班次合并取整。"""
    if not holiday_days:
        return employee
    holidays = set(holiday_days)
    half_hours = 0
    # 包含节假日前一天，以接住非节假日跨夜进入节假日的班次。
    relevant_days = holidays | {day - 1 for day in holidays if day > 1}
    for day in sorted(relevant_days):
        try:
            if day > len(employee.records):
                raise ValueError("缺少当日考勤记录")
            punches = _punches(employee.records[day - 1])
            if punches is None:
                continue
            start, end = punches
            if end > start:
                minutes = end - start if day in holidays else 0
            else:
                minutes = 24 * 60 - start if day in holidays else 0
                if day + 1 in holidays:
                    minutes += end
            half_hours += minutes // 30
        except ValueError as exc:
            if day in holidays:
                raise ValueError(f"员工“{employee.name}”{day} 日节假日加班计算失败: {exc}") from exc
            raise ValueError(
                f"员工“{employee.name}”{day} 日（节假日前一日，用于跨夜班次）加班计算失败: {exc}"
            ) from exc
    if not half_hours:
        return employee
    weekday, rest_day, holiday = employee.overtime_hours
    try:
        base = Decimal(str(holiday).strip() or "0")
        total = float(base + Decimal(half_hours) / 2)
        if not base.is_finite() or base < 0 or not math.isfinite(total):
            raise ValueError("节假日加班必须是有限非负数")
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError(f"员工“{employee.name}”原有节假日加班不是有效时长: {holiday}") from exc
    return replace(employee, overtime_hours=(weekday, rest_day, total))
