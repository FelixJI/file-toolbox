"""op_schema 声明式参数校验的单测。"""

from file_toolbox.common.op_schema import ParamRule, validate_params


def test_required_passes_when_present():
    rules = {"op": ParamRule(required=("text",))}
    ok, msg = validate_params({"type": "op", "params": {"text": "x"}}, 0, rules)
    assert ok and msg == ""


def test_required_empty_string_rejected():
    rules = {"op": ParamRule(required=("text",))}
    ok, msg = validate_params({"type": "op", "params": {"text": "  "}}, 2, rules)
    assert ok is False
    assert "操作 3" in msg  # index 0-based -> 第 3 个


def test_required_missing_rejected():
    rules = {"op": ParamRule(required=("find",))}
    ok, msg = validate_params({"type": "op", "params": {}}, 0, rules)
    assert ok is False
    assert "find" in msg


def test_empty_message_override():
    rules = {"op": ParamRule(required=("find",), empty_messages={"find": "查找文本不能为空"})}
    ok, msg = validate_params({"type": "op", "params": {"find": ""}}, 0, rules)
    assert ok is False
    assert msg == "操作 1: 查找文本不能为空"


def test_regex_key_valid():
    rules = {"op": ParamRule(regex_key="pattern")}
    ok, msg = validate_params({"type": "op", "params": {"pattern": r"\d+"}}, 0, rules)
    assert ok and msg == ""


def test_regex_key_invalid():
    rules = {"op": ParamRule(regex_key="pattern")}
    ok, msg = validate_params({"type": "op", "params": {"pattern": "("}}, 0, rules)
    assert ok is False
    assert "正则" in msg


def test_extra_callback_invoked():
    def custom(op, idx):
        return (False, f"自定义失败 {idx + 1}")

    rules = {"op": ParamRule(extra=custom)}
    ok, msg = validate_params({"type": "op", "params": {}}, 1, rules)
    assert ok is False
    assert msg == "自定义失败 2"


def test_unknown_type_passes():
    """无规则的类型由调用方/基类负责,此处视为通过。"""
    ok, msg = validate_params({"type": "mystery", "params": {}}, 0, {})
    assert ok and msg == ""
