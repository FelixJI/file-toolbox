"""ReplaceController —— 内容替换 Tab 的视图层格式化(操作标签、历史行展示)。

不 import PySide6 —— 与 pdf/mkdir/invoice 三控制器对齐,纯 Python 可无 Qt 单测。
历史记录构建已下沉 ContentReplaceService(本控制器不含 build_history_record)。
"""

from __future__ import annotations

from typing import Any

from file_toolbox.core.batch_replace import ReplaceOperationType


class ReplaceController:
    """内容替换 Tab 的视图层格式化(纯 Python)。

    - format_op_label:单个操作 -> 操作列表展示文本(替代 replace_tab._refresh_op_list 内联)。
    - format_history_line:历史记录 -> 一行展示文本(替代 replace_tab._show_history 内联)。
    """

    def format_op_label(self, op: dict[str, Any]) -> str:
        """单个操作 -> 操作列表展示文本。

        与原 replace_tab._refresh_op_list 内联格式一致:
        - SIMPLE_REPLACE: "替换: <find> -> <replace>"
        - REGEX_REPLACE: "正则: /<pattern>/ -> <replace>"
        """
        p = op.get("params", {})
        if op.get("type") == ReplaceOperationType.SIMPLE_REPLACE.value:
            return f"替换: {p.get('find', '')!r} -> {p.get('replace', '')!r}"
        return f"正则: /{p.get('pattern', '')}/ -> {p.get('replace', '')!r}"

    def format_history_line(self, record: dict[str, Any]) -> str:
        """历史记录 -> 一行展示文本(与 replace_tab._show_history 内联格式一致)。

        格式:"#<id> <timestamp[:19]>  <首个文件>"(取 files 列表首项)。
        """
        rid = record.get("id", "?")
        ts = str(record.get("timestamp", ""))[:19]
        data = record.get("data", {})
        files = data.get("files", [])
        return f"#{rid} {ts}  {files[:1]}"


__all__ = ["ReplaceController"]
