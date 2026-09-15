"""计划排布 Tab 业务编排:控件值→选项映射、结果行构造、汇总文案(无 Qt 依赖)。

与 excel_merge controller 同范式:View 把 Qt 控件值读成纯 Python 快照,
controller 做纯 Python 编排,可无 Qt 单测。
"""

from __future__ import annotations

from file_toolbox.core.plan_schedule import (
    CELL_INDEX,
    CELL_NAME,
    ScheduleOptions,
    ScheduleResult,
)

# 下拉框索引 -> 常量值(与 generated/ui_plan_schedule_dialog.py 的 CELL_LABELS 顺序一致)
_CELL_BY_INDEX = (CELL_INDEX, CELL_NAME)


def _clamp_index(index: int, size: int) -> int:
    """下拉框索引越界时夹回有效范围(防御性,Qt 索引正常不会越界)。"""
    return max(0, min(index, size - 1))


class PlanScheduleController:
    """计划排布 Tab 的业务编排(无 Qt 依赖)。"""

    @staticmethod
    def build_options(year: int | None, cell_index: int = 0) -> ScheduleOptions:
        """年份/格子内容控件值 -> ScheduleOptions(年份 None 表示用当前年份)。"""
        cell = _CELL_BY_INDEX[_clamp_index(cell_index, len(_CELL_BY_INDEX))]
        return ScheduleOptions(default_year=year, cell_mode=cell)

    @staticmethod
    def format_progress(cur: int, total: int, msg: str) -> str:
        """进度文案:"[cur/total] msg"。"""
        return f"[{cur}/{total}] {msg}"

    @staticmethod
    def result_rows(
        result: ScheduleResult,
    ) -> list[tuple[list[str], bool]]:
        """结果表格行:项点行 + 无效行(无效行标记失败底色)。"""
        rows: list[tuple[list[str], bool]] = [
            (
                [item.name, str(item.start), str(item.end), f"{item.days}天", "已排布"],
                False,
            )
            for item in result.items
        ]
        rows += [
            ([f"第{inv.row}行", "", "", "", f"无效:{inv.error}"], True) for inv in result.invalid
        ]
        return rows

    @staticmethod
    def summarize(result: ScheduleResult) -> str:
        """生成结束后的状态栏一行摘要。"""
        if not result.success:
            return f"失败:{result.error_message or '未生成输出'}"
        assert result.output is not None
        invalid = f",{len(result.invalid)} 行无效" if result.invalid else ""
        return f"已排布 {len(result.items)} 个项点{invalid} -> {result.output}"
