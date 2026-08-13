"""考勤正则分类与固定单元格变量渲染。"""

from __future__ import annotations

import re
from datetime import date

from file_toolbox.core.attendance.types import AttendanceRule

_TOKEN_RE = re.compile(r"{{([a-z_]+)}}")
CONTENT_TEMPLATE_TOKENS = (
    "year",
    "month",
    "month_start",
    "month_end",
    "department",
    "attendance_group",
    "roster_group",
    "group_alias",
)
_TOKENS = set(CONTENT_TEMPLATE_TOKENS)


def compile_rules(rules: tuple[AttendanceRule, ...]) -> tuple[tuple[re.Pattern[str], str], ...]:
    compiled: list[tuple[re.Pattern[str], str]] = []
    for rule in rules:
        if not rule.enabled:
            continue
        try:
            compiled.append((re.compile(rule.pattern), rule.output))
        except re.error as exc:
            raise ValueError(f"无效正则 {rule.pattern!r}: {exc}") from exc
    if not compiled:
        raise ValueError("至少需要一条启用的考勤规则")
    return tuple(compiled)


def classify(raw: str, rules: tuple[tuple[re.Pattern[str], str], ...]) -> str | None:
    if not raw.strip():
        return ""
    for pattern, output in rules:
        if pattern.search(raw):
            return output
    return None


def render_content(
    template: str,
    *,
    year: int,
    month: int,
    last_day: int,
    department: str,
    attendance_group: str = "",
    roster_group: str = "",
    group_alias: str = "",
) -> str:
    unknown = set(_TOKEN_RE.findall(template)) - _TOKENS
    if unknown:
        raise ValueError(f"未知变量: {', '.join(sorted(unknown))}")
    values = {
        "year": str(year),
        "month": str(month),
        "month_start": _format_date(date(year, month, 1)),
        "month_end": _format_date(date(year, month, last_day)),
        "department": department,
        "attendance_group": attendance_group,
        "roster_group": roster_group,
        "group_alias": group_alias,
    }
    return _TOKEN_RE.sub(lambda match: values[match.group(1)], template)


def _format_date(value: date) -> str:
    return f"{value.year}年{value.month}月{value.day}日"
