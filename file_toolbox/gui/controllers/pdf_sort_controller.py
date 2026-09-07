"""PDF 排序 Tab 业务编排:控件索引→选项映射、结果汇总文案(无 Qt 依赖)。

与 pdf/invoice controller 同范式:View 把 Qt 控件值读成纯 Python 快照/索引,
controller 做纯 Python 编排,可无 Qt 单测。
"""

from __future__ import annotations

from file_toolbox.core.pdf_sort import (
    ORDER_ASC,
    ORDER_DESC,
    UNMATCHED_FAIL,
    UNMATCHED_FIRST,
    UNMATCHED_LAST,
    SortOptions,
    SortResult,
)

# 下拉框索引 -> 常量值(与 generated/ui_pdf_sort_dialog.py 的 *_LABELS 顺序一致)
_ORDER_BY_INDEX = (ORDER_ASC, ORDER_DESC)
_UNMATCHED_BY_INDEX = (UNMATCHED_LAST, UNMATCHED_FIRST, UNMATCHED_FAIL)


def _clamp_index(index: int, size: int) -> int:
    """下拉框索引越界时夹回有效范围(防御性,Qt 索引正常不会越界)。"""
    return max(0, min(index, size - 1))


class PdfSortController:
    """PDF 排序 Tab 的业务编排(无 Qt 依赖)。"""

    def build_options(self, pattern: str, order_index: int, unmatched_index: int) -> SortOptions:
        """控件值 -> SortOptions。"""
        order = _ORDER_BY_INDEX[_clamp_index(order_index, len(_ORDER_BY_INDEX))]
        unmatched = _UNMATCHED_BY_INDEX[_clamp_index(unmatched_index, len(_UNMATCHED_BY_INDEX))]
        return SortOptions(pattern=pattern, order=order, unmatched=unmatched)

    def format_progress(self, cur: int, total: int, msg: str) -> str:
        """进度文案:"[cur/total] msg"。"""
        return f"[{cur}/{total}] {msg}"

    def summarize(self, result: SortResult) -> str:
        """排序结束后的状态栏一行摘要。"""
        if result.cancelled:
            return "已取消"
        if not result.success:
            return f"失败:{result.error_message or '未处理任何文件'}"
        written = result.written_count
        unchanged = sum(1 for f in result.sorted_files if f.output is None)
        failed = f",{len(result.failed)} 个文件失败" if result.failed else ""
        if written:
            outputs = [f.output for f in result.sorted_files if f.output is not None]
            target = f" -> {outputs[0].name}" if len(outputs) == 1 else f" -> {len(outputs)} 个输出"
            note = f",{unchanged} 个顺序未变" if unchanged else ""
            return f"已写出 {written} 个排序输出{note}{failed}{target}"
        return f"{unchanged} 个文件顺序未变,未写出输出{failed}"
