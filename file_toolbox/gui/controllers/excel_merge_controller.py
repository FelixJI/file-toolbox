"""Excel 合并 Tab 业务编排:控件索引→选项映射、结果汇总文案(无 Qt 依赖)。

与 pdf/invoice controller 同范式:View 把 Qt 控件值读成纯 Python 快照/索引,
controller 做纯 Python 编排,可无 Qt 单测。
"""

from __future__ import annotations

from file_toolbox.core.excel_merge import (
    MODE_FORMULAS,
    MODE_VALUES,
    NAMING_KEEP,
    NAMING_PREFIX,
    MergeOptions,
    MergeResult,
)

# 下拉框索引 -> 常量值(与 generated/ui_excel_merge_dialog.py 的 *_LABELS 顺序一致)
_NAMING_BY_INDEX = (NAMING_PREFIX, NAMING_KEEP)
_MODE_BY_INDEX = (MODE_VALUES, MODE_FORMULAS)


def _clamp_index(index: int, size: int) -> int:
    """下拉框索引越界时夹回有效范围(防御性,Qt 索引正常不会越界)。"""
    return max(0, min(index, size - 1))


class ExcelMergeController:
    """Excel 合并 Tab 的业务编排(无 Qt 依赖)。"""

    def build_options(
        self, naming_index: int, mode_index: int, include_hidden: bool
    ) -> MergeOptions:
        """控件索引 -> MergeOptions。"""
        naming = _NAMING_BY_INDEX[_clamp_index(naming_index, len(_NAMING_BY_INDEX))]
        mode = _MODE_BY_INDEX[_clamp_index(mode_index, len(_MODE_BY_INDEX))]
        return MergeOptions(naming=naming, mode=mode, include_hidden=include_hidden)

    def format_progress(self, cur: int, total: int, msg: str) -> str:
        """进度文案:"[cur/total] msg"。"""
        return f"[{cur}/{total}] {msg}"

    def summarize(self, result: MergeResult) -> str:
        """合并结束后的状态栏一行摘要。"""
        if result.cancelled:
            return "已取消"
        if not result.success:
            return f"失败:{result.error_message or '未生成输出'}"
        assert result.output is not None
        failed = f",{len(result.failed)} 个文件失败" if result.failed else ""
        return f"已合并 {len(result.sheets)} 个工作表{failed} -> {result.output}"
