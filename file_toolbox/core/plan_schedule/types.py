"""计划排布数据类型(纯数据,不依赖 openpyxl/Qt,便于单测)。"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class PlanItem:
    """一个项点:名称 + 起止日期(含端点)。"""

    name: str
    start: date
    end: date
    row: int = 0  # 输入文件中的行号(1-based,供错误定位与预览展示)

    @property
    def days(self) -> int:
        """项点总天数(含首尾)。"""
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class InvalidRow:
    """解析失败的输入行(记录原因,不中断其余行)。"""

    row: int
    error: str


@dataclass(frozen=True)
class ScheduleOptions:
    """生成选项(与 CLI 参数 / GUI 控件一一对应)。"""

    default_year: int | None = None  # 日期串缺年份时使用的年份;None 表示当前年份


@dataclass(frozen=True)
class MonthPlan:
    """排布后的一个月块(纯计算结果,渲染只读它)。

    items: 该月活跃的项点及其逐日格子 [(项点, [(几号, 项点内第几天)])],
    按开始日期、名称排序;"项点内第几天"跨月连续编号。
    parallel: 几号 -> 并行项点数(仅保留 >=1 的日子)。
    """

    year: int
    month: int
    days: int  # 该月天数
    weekends: frozenset[int]  # 周末的"几号"集合
    items: list[tuple[PlanItem, list[tuple[int, int]]]] = field(default_factory=list)
    parallel: dict[int, int] = field(default_factory=dict)


@dataclass
class ScheduleResult:
    """生成结果。

    output 已写出即 success(允许部分输入行无效);
    全部行无效/文件不可读/输出失败时 output 为 None 并给出 error_message。
    """

    output: Path | None = None
    items: list[PlanItem] = field(default_factory=list)
    invalid: list[InvalidRow] = field(default_factory=list)
    error_message: str = ""

    @property
    def success(self) -> bool:
        """已写出输出文件即成功(部分行无效不影响)。"""
        return self.output is not None
