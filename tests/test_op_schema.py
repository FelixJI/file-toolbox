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


def test_string_keys_coerces_int_to_str():
    """string_keys 声明的键,校验时强制转为 str(就地修改 params)。

    回归 op_parser._coerce:裸数字值(如 replace=2026)被解析为 int,
    导致下游 re.subn/replaced 报 TypeError。声明为 string_keys 后应转回 str。
    """
    rules = {"op": ParamRule(required=("find",), string_keys=("find", "replace"))}
    op = {"type": "op", "params": {"find": 2024, "replace": 2026}}
    ok, msg = validate_params(op, 0, rules)
    assert ok and msg == ""
    # 关键:值被就地转为 str
    assert op["params"]["find"] == "2024"
    assert op["params"]["replace"] == "2026"
    assert isinstance(op["params"]["replace"], str)


def test_string_keys_preserves_existing_str():
    """string_keys 对已是 str 的值无副作用。"""
    rules = {"op": ParamRule(string_keys=("replace",))}
    op = {"type": "op", "params": {"replace": "新公司"}}
    ok, _ = validate_params(op, 0, rules)
    assert ok
    assert op["params"]["replace"] == "新公司"


def test_string_keys_missing_key_no_error():
    """string_keys 声明的键若缺失,不报错(必填性由 required 负责)。"""
    rules = {"op": ParamRule(string_keys=("replace",))}
    op = {"type": "op", "params": {"find": "x"}}
    ok, _ = validate_params(op, 0, rules)
    assert ok
