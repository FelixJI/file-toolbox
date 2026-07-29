"""RenameController —— 重命名 Tab 的视图层格式化(操作标签、历史行展示)。

不 import PySide6 —— 与 pdf/mkdir/invoice 三控制器对齐,纯 Python 可无 Qt 单测。
历史记录构建已下沉 FileRenameService(本控制器不含 build_history_record)。
"""

from __future__ import annotations

from typing import Any

from file_toolbox.core.batch_rename import OperationType


class RenameController:
    """重命名 Tab 的视图层格式化(纯 Python)。

    - OP_LABELS:操作类型 -> 中文标签(操作列表展示、模板描述共用)。
    - op_label:取单个操作的中文标签(未知类型回退为 type 字符串)。
    - summarize_rename:执行结果 -> (count, 格式化串)。
    - format_history_line:历史记录 -> 一行展示文本(替代 rename_tab._show_history 内联)。
    """

    # 操作类型 -> 中文标签(从 rename_tab._OP_LABELS 迁入,操作列表展示、模板描述共用)
    OP_LABELS: dict[str, str] = {
        OperationType.ADD_PREFIX.value: "添加前缀",
        OperationType.ADD_SUFFIX.value: "添加后缀",
        OperationType.REPLACE_TEXT.value: "替换字符",
        OperationType.REGEX_REPLACE.value: "正则替换",
        OperationType.ADD_NUMBER.value: "添加序号",
        OperationType.DELETE_CHARS.value: "删除字符",
        OperationType.ADD_DATE.value: "添加日期",
    }

    def op_label(self, op_type: Any) -> str:
        """操作类型 -> 中文标签。op_type 非 str 或未知时回退为其字符串形式。"""
        op_type_str = op_type if isinstance(op_type, str) else str(op_type)
        return self.OP_LABELS.get(op_type_str, op_type_str)

    def summarize_rename(self, apply_result: dict[Any, tuple[Any, str]]) -> tuple[int, str]:
        """统计执行结果中就绪文件数,返回 (count, 格式化串)。

        apply_result: FileRenameService.apply_operations 的返回值
            {原路径: (新路径, 状态消息)}。就绪 = 状态含 "准备"。
        """
        ready = sum(1 for _, (_, status) in apply_result.items() if "准备" in status)
        return ready, f"{ready} 个文件准备就绪"

    def format_history_line(self, record: dict[str, Any]) -> str:
        """历史记录 -> 一行展示文本(与 rename_tab._show_history 内联格式一致)。

        格式:"#<id> <timestamp[:19]>  <n> 个文件"。
        """
        rid = record.get("id", "?")
        ts = str(record.get("timestamp", ""))[:19]
        data = record.get("data", {})
        n = len(data.get("rename_map", {}))
        return f"#{rid} {ts}  {n} 个文件"


__all__ = ["RenameController"]
