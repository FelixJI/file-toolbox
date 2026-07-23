"""OperationParamCollector 测试:用 stub Prompter 模拟输入,验证各 op 类型参数收集。

行为对齐 rename_tab/replace_tab 原内联逻辑(空 find/前缀视为取消,replace 允许空)。
"""

from file_toolbox.gui.controllers.operation_params import (
    OperationParamCollector,
    PromptCancelled,
)


class StubPrompter:
    """记录调用并按预设队列返回结果,模拟 QInputDialog。

    每个方法队列空时抛 PromptCancelled(模拟用户取消)。
    """

    def __init__(self, text_answers=None, int_answers=None, item_answers=None):
        self.text_answers = list(text_answers or [])
        self.int_answers = list(int_answers or [])
        self.item_answers = list(item_answers or [])
        self.text_calls: list = []
        self.int_calls: list = []
        self.item_calls: list = []

    def get_text(self, title, label, text=""):
        self.text_calls.append((title, label, text))
        if not self.text_answers:
            raise PromptCancelled
        return self.text_answers.pop(0)

    def get_int(self, title, label, value=0, minimum=0, maximum=99):
        self.int_calls.append((title, label, value, minimum, maximum))
        if not self.int_answers:
            raise PromptCancelled
        return self.int_answers.pop(0)

    def get_item(self, title, label, items, current=0, editable=False):
        self.item_calls.append((title, label, items, current, editable))
        if not self.item_answers:
            raise PromptCancelled
        return self.item_answers.pop(0)


def _collector(*, text=None, ints=None, items=None):
    return OperationParamCollector(
        StubPrompter(text_answers=text, int_answers=ints, item_answers=items)
    )


# ---------- rename: add_prefix / add_suffix ----------


def test_collect_add_prefix():
    c = _collector(text=["项目_"])
    assert c.collect("add_prefix") == {"text": "项目_"}


def test_collect_add_prefix_empty_returns_none():
    """空前缀视为取消(原行为:ok and text)。"""
    c = _collector(text=[""])
    assert c.collect("add_prefix") is None


def test_collect_add_prefix_cancelled_returns_none():
    c = _collector(text=None)
    assert c.collect("add_prefix") is None


def test_collect_add_suffix():
    c = _collector(text=["_后"])
    assert c.collect("add_suffix") == {"text": "_后"}


def test_collect_add_prefix_existing_prefill():
    """编辑预填:existing.text 透传给 prompter 的默认值。"""
    c = _collector(text=["新前缀"])
    c.collect("add_prefix", existing={"text": "旧前缀"})
    assert c._p.text_calls[0][2] == "旧前缀"


# ---------- rename: replace_text / regex_replace ----------


def test_collect_replace_text():
    c = _collector(text=["旧", "新"])
    assert c.collect("replace_text") == {"find": "旧", "replace": "新"}


def test_collect_replace_text_empty_find_returns_none():
    c = _collector(text=["", "新"])
    assert c.collect("replace_text") is None


def test_collect_replace_text_cancel_replace_keeps_empty():
    """find 有值但 replace 阶段取消 → replace 为空串(不返回 None)。"""
    c = _collector(text=["旧"])  # 第二次 get_text 队列空 → PromptCancelled
    result = c.collect("replace_text")
    assert result == {"find": "旧", "replace": ""}


def test_collect_replace_text_replace_empty_allowed():
    """replace 显式输入空串(删除语义)→ 保留空。"""
    c = _collector(text=["旧", ""])
    assert c.collect("replace_text") == {"find": "旧", "replace": ""}


def test_collect_regex_replace():
    c = _collector(text=[r"\d+", "X"])
    assert c.collect("regex_replace") == {"pattern": r"\d+", "replace": "X", "ignore_case": False}


def test_collect_regex_replace_empty_pattern_returns_none():
    c = _collector(text=["", "X"])
    assert c.collect("regex_replace") is None


def test_collect_regex_replace_preserves_ignore_case():
    c = _collector(text=[r"\d+", "X"])
    result = c.collect("regex_replace", existing={"ignore_case": True})
    assert result == {"pattern": r"\d+", "replace": "X", "ignore_case": True}


# ---------- rename: add_number / delete_chars / add_date ----------


def test_collect_add_number():
    c = _collector(ints=[5, 4])
    assert c.collect("add_number") == {"start": 5, "digits": 4}


def test_collect_add_number_cancelled_returns_none():
    c = _collector(ints=None)
    assert c.collect("add_number") is None


def test_collect_delete_chars():
    c = _collector(items=["prefix"], text=["3"])
    assert c.collect("delete_chars") == {"delete_type": "prefix", "value": "3"}


def test_collect_delete_chars_cancel_item_returns_none():
    c = _collector(items=None, text=["3"])
    assert c.collect("delete_chars") is None


def test_collect_add_date():
    c = _collector(text=["%Y%m%d"])
    assert c.collect("add_date") == {"format": "%Y%m%d"}


def test_collect_add_date_cancelled_returns_none():
    c = _collector(text=None)
    assert c.collect("add_date") is None


def test_collect_add_date_empty_allowed():
    """add_date 空 fmt 不视为取消(原行为:ok 即返回,空串保留)。"""
    c = _collector(text=[""])
    assert c.collect("add_date") == {"format": ""}


# ---------- replace: simple_replace ----------


def test_collect_simple_replace():
    c = _collector(text=["旧", "新"])
    assert c.collect("simple_replace") == {
        "find": "旧",
        "replace": "新",
        "case_sensitive": False,
    }


def test_collect_simple_replace_empty_find_returns_none():
    c = _collector(text=["", "新"])
    assert c.collect("simple_replace") is None


def test_collect_simple_replace_preserves_case_sensitive():
    c = _collector(text=["旧", "新"])
    result = c.collect("simple_replace", existing={"case_sensitive": True})
    assert result == {"find": "旧", "replace": "新", "case_sensitive": True}


# ---------- 未知类型 ----------


def test_collect_unknown_type_returns_none():
    c = _collector(text=["x"])
    assert c.collect("nonexistent_op") is None
