"""OperationParamCollector 测试:用 stub Prompter 模拟输入,验证各 op 类型参数收集。

行为对齐 rename_tab/replace_tab 原内联逻辑(空 find/前缀视为取消,replace 允许空)。
"""

from file_toolbox.gui.controllers.operation_params import (
    OperationParamCollector,
    PromptCancelled,
    Prompter,
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


def test_collect_add_suffix_empty_returns_none():
    """空后缀视为取消(与 add_prefix 一致:ok and text)。"""
    c = _collector(text=[""])
    assert c.collect("add_suffix") is None


def test_collect_add_suffix_cancelled_returns_none():
    """后缀阶段直接取消(队列空 → PromptCancelled)→ collect 返回 None。"""
    c = _collector(text=None)
    assert c.collect("add_suffix") is None


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


def test_collect_regex_replace_cancel_replace_keeps_empty():
    """pattern 有值但 replace 阶段取消 → replace 为空串(不返回 None)。"""
    c = _collector(text=[r"\d+"])  # 第二次 get_text 队列空 → PromptCancelled
    result = c.collect("regex_replace")
    assert result == {"pattern": r"\d+", "replace": "", "ignore_case": False}


def test_collect_regex_replace_replace_empty_allowed():
    """replace 显式输入空串(删除语义)→ 保留空。"""
    c = _collector(text=[r"\d+", ""])
    assert c.collect("regex_replace") == {"pattern": r"\d+", "replace": "", "ignore_case": False}


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


def test_collect_delete_chars_cancel_value_returns_none():
    """delete_chars:选了类型但 value 提示被取消 → **整体取消返回 None**(锁定当前行为)。

    注:这与 _collect_replace_text 不同(replace 对 value 取消 try/except 保留空串)。
    delete_chars 的 value get_text 未包 try,故取消直接抛 PromptCancelled → collect 返回 None。
    锁定该不一致:未来若统一为「value 取消保留空串」,该测试应变红提醒有意更新。
    """
    c = _collector(items=["suffix"], text=None)  # value 取消(队列空)
    assert c.collect("delete_chars") is None


def test_collect_add_number_int_coerces_existing_str_prefill():
    """add_number:existing 的 start/digits 为字符串时,int() 强转后作为 prefill 透传。

    回归保护:int(ex.get('start',1)) 的强转若被移除,字符串 prefill 会 TypeError。
    断言 get_int 收到的 value 是 int(强转后)且来自 existing。
    """
    c = _collector(ints=[9, 2])
    c.collect("add_number", existing={"start": "9", "digits": "2"})
    # 第一次 get_int(start) 的 prefill value 应为 int 9(字符串被 int() 转过)
    assert c._p.int_calls[0][2] == 9
    assert c._p.int_calls[1][2] == 2


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


def test_collect_simple_replace_cancel_replace_keeps_empty():
    """find 有值但 replace 阶段取消 → replace 为空串(不返回 None)。"""
    c = _collector(text=["旧"])  # 第二次 get_text 队列空 → PromptCancelled
    result = c.collect("simple_replace")
    assert result == {"find": "旧", "replace": "", "case_sensitive": False}


def test_collect_simple_replace_replace_empty_allowed():
    """replace 显式输入空串(删除语义)→ 保留空。"""
    c = _collector(text=["旧", ""])
    assert c.collect("simple_replace") == {"find": "旧", "replace": "", "case_sensitive": False}


# ---------- 未知类型 ----------


def test_collect_unknown_type_returns_none():
    c = _collector(text=["x"])
    assert c.collect("nonexistent_op") is None


# ---------- Prompter Protocol 声明体(`...` 方法体)----------

# Protocol 方法体的 `...` 是 Ellipsis 表达式语句,本身可执行:用一个继承 Protocol
# 的具体子类调用其继承得到的方法体即可让覆盖计入(StubPrompter 定义了自己的方法,
# 不会命中 Protocol 体内的 `...`)。此处验证 Protocol 声明的方法体可被调用且返回 None。


def test_prompter_protocol_body_methods_return_none():
    """Prompter Protocol 的三个 `...` 方法体经具体子类调用,均返回 None。

    覆盖 operation_params.py 第 21/27/33 行(Protocol 方法体的 `...` 表达式语句)。
    """

    class _ConcretePrompter(Prompter):
        pass

    p = _ConcretePrompter()
    assert p.get_text("t", "l") is None
    assert p.get_int("t", "l") is None
    assert p.get_item("t", "l", []) is None
