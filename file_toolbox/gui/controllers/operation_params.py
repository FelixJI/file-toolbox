"""操作参数收集框架 —— 把 rename/replace 的 QInputDialog 弹窗逻辑收口。

设计:collector 不直接 import PySide6,通过 Prompter protocol 抽象输入交互。
View 提供 QInputDialog 实现,测试提供 stub 实现。这样参数收集逻辑可无 Qt 单测。
"""

from __future__ import annotations

from typing import Any, Protocol


class PromptCancelled(Exception):
    """用户在 prompter 对话框中点了取消(或输入了无效空值)。"""


class Prompter(Protocol):
    """输入交互抽象 —— View 用 QInputDialog 实现,测试用 stub。"""

    def get_text(self, title: str, label: str, text: str = "") -> str:
        """弹文本输入框;取消时抛 PromptCancelled。"""
        ...

    def get_int(
        self, title: str, label: str, value: int = 0, minimum: int = 0, maximum: int = 99
    ) -> int:
        """弹整数输入框;取消时抛 PromptCancelled。"""
        ...

    def get_item(
        self, title: str, label: str, items: list[str], current: int = 0, editable: bool = False
    ) -> str:
        """弹下拉选择框;取消时抛 PromptCancelled。"""
        ...


class OperationParamCollector:
    """根据操作类型收集参数。collect 返回 params dict 或 None(取消/无效)。"""

    # 操作类型 -> 收集方法名(在 collect 里按名查找,避免类体内前向引用问题)。
    _DISPATCH: dict[str, str] = {
        "add_prefix": "_collect_add_prefix",
        "add_suffix": "_collect_add_suffix",
        "replace_text": "_collect_replace_text",
        "regex_replace": "_collect_regex_replace",
        "add_number": "_collect_add_number",
        "delete_chars": "_collect_delete_chars",
        "add_date": "_collect_add_date",
        "simple_replace": "_collect_simple_replace",
    }

    def __init__(self, prompter: Prompter):
        self._p = prompter

    def collect(
        self, op_type: str, existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """收集指定操作类型的参数。返回 params dict,取消/未知类型返回 None。"""
        existing = existing or {}
        method_name = self._DISPATCH.get(op_type)
        if method_name is None:
            return None
        try:
            method = getattr(self, method_name)
            result: dict[str, Any] = method(existing)
            return result
        except PromptCancelled:
            return None

    # ---------- rename 操作类型 ----------

    def _collect_add_prefix(self, ex: dict[str, Any]) -> dict[str, Any]:
        # 空 text 视为取消(与原 QInputDialog 行为一致:ok and text)
        text = self._p.get_text("添加前缀", "前缀文本:", text=ex.get("text", ""))
        if not text:
            raise PromptCancelled
        return {"text": text}

    def _collect_add_suffix(self, ex: dict[str, Any]) -> dict[str, Any]:
        text = self._p.get_text("添加后缀", "后缀文本:", text=ex.get("text", ""))
        if not text:
            raise PromptCancelled
        return {"text": text}

    def _collect_replace_text(self, ex: dict[str, Any]) -> dict[str, Any]:
        find = self._p.get_text("替换字符", "查找:", text=ex.get("find", ""))
        if not find:
            raise PromptCancelled
        # replace 允许空(删除语义);get_text 失败(取消)时返回空串而非抛异常,
        # 故用空串作为"未取消"的占位 —— 由调用方决定。
        try:
            replace = self._p.get_text(
                "替换字符", f"将 {find!r} 替换为:", text=ex.get("replace", "")
            )
        except PromptCancelled:
            replace = ""
        return {"find": find, "replace": replace}

    def _collect_regex_replace(self, ex: dict[str, Any]) -> dict[str, Any]:
        pattern = self._p.get_text("正则替换", "正则表达式:", text=ex.get("pattern", ""))
        if not pattern:
            raise PromptCancelled
        try:
            replace = self._p.get_text("正则替换", "替换为:", text=ex.get("replace", ""))
        except PromptCancelled:
            replace = ""
        # ignore_case:rename 与 replace 都读此键(rename 默认 False,replace 由 UI 传入)。
        return {"pattern": pattern, "replace": replace, "ignore_case": ex.get("ignore_case", False)}

    def _collect_add_number(self, ex: dict[str, Any]) -> dict[str, Any]:
        start = self._p.get_int("添加序号", "起始序号:", value=int(ex.get("start", 1)), minimum=0)
        digits = self._p.get_int(
            "添加序号", "位数:", value=int(ex.get("digits", 3)), minimum=1, maximum=10
        )
        return {"start": start, "digits": digits}

    def _collect_delete_chars(self, ex: dict[str, Any]) -> dict[str, Any]:
        dtype = self._p.get_item(
            "删除字符", "删除类型:", ["prefix", "suffix", "text"], current=0, editable=False
        )
        value = self._p.get_text(
            "删除字符",
            "值(前缀/后缀为数量,文本为要删除的文本):",
            text=str(ex.get("value", "")),
        )
        return {"delete_type": dtype, "value": value}

    def _collect_add_date(self, ex: dict[str, Any]) -> dict[str, Any]:
        fmt = self._p.get_text("添加日期", "日期格式:", text=ex.get("format", "%Y%m%d"))
        return {"format": fmt}

    # ---------- replace 操作类型 ----------

    def _collect_simple_replace(self, ex: dict[str, Any]) -> dict[str, Any]:
        find = self._p.get_text("简单替换", "查找文本:", text=ex.get("find", ""))
        if not find:
            raise PromptCancelled
        try:
            replace = self._p.get_text(
                "简单替换", f"将 {find!r} 替换为:", text=ex.get("replace", "")
            )
        except PromptCancelled:
            replace = ""
        return {
            "find": find,
            "replace": replace,
            "case_sensitive": ex.get("case_sensitive", False),
        }
