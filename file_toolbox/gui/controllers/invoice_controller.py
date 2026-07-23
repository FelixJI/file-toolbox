"""发票识别 Tab 控制器:把 UI 无关的纯逻辑从 InvoiceTab 收口。

不 import PySide6 —— 这样映射/状态串/历史记录等逻辑可无 Qt 单测。
对应 View 层 file_toolbox.gui.dialogs.invoice_tab.InvoiceTab 仅做控件读写与编排。
"""

from __future__ import annotations

from typing import Any

from file_toolbox.core.invoice.dedupe import DEDUPE, KEEP_ALL, MARK


class InvoiceController:
    """发票识别 Tab 的纯逻辑层。

    - 去重策略:下拉框索引 → KEEP_ALL/DEDUPE/MARK 常量。
    - 格式:三个单选按钮状态 → "excel"/"json"/"both" 字符串。
    - 状态串:解析计数 → 摘要文本。
    - 历史记录:导出结果 → history.add_record 的 dict。
    """

    # 下拉框 addItems 顺序:keep_all(不处理) / dedupe(去重) / mark(标色)
    _DEDUPE_BY_INDEX = [KEEP_ALL, DEDUPE, MARK]

    def dedupe_strategy(self, index: int) -> str:
        """下拉框索引映射为去重策略常量。索引越界时按列表语义抛 IndexError。"""
        return self._DEDUPE_BY_INDEX[index]

    def format(self, json_checked: bool, both_checked: bool) -> str:
        """根据单选按钮状态返回格式字符串,与原 InvoiceTab._format 行为一致。"""
        if json_checked:
            return "json"
        if both_checked:
            return "both"
        return "excel"

    def format_status(
        self,
        invoice_count: int,
        duplicate_marked: int,
        dedupe_removed: int,
        failed: int,
    ) -> str:
        """解析完成后的状态摘要文本,措辞与原 InvoiceTab._parse 完全一致。"""
        return (
            f"成功 {invoice_count} | 重复标记 {duplicate_marked} | "
            f"去重移除 {dedupe_removed} | 失败 {failed}"
        )

    def build_history_record(
        self,
        file_count: int,
        invoice_count: int,
        dedupe_strategy: str,
        fmt: str,
        outputs: list[Any],
    ) -> dict[str, Any]:
        """构造 history.add_record 的 record dict,键与原 InvoiceTab._export 一致。

        outputs 转为 str 列表(原行为:[str(w) for w in written])。
        """
        return {
            "file_count": file_count,
            "invoice_count": invoice_count,
            "dedupe_strategy": dedupe_strategy,
            "fmt": fmt,
            "outputs": [str(w) for w in outputs],
        }
