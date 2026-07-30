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


# ---------------------------------------------------------------------------
# string_keys:零值 / 浮点 / 就地修改 identity(防回归把 `if params[key]` 改 falsy 判定)
# ---------------------------------------------------------------------------


def test_string_keys_coerces_int_zero_to_str():
    """int 0(falsy)必须被强转为 \"0\"。

    回归风险:若实现误把 `if params[key] is not None` 改成 `if params[key]`(truthy),
    0 会被跳过,下游收到 int 0 报 TypeError。锁定 None 判定。
    """
    rules = {"op": ParamRule(string_keys=("replace",))}
    op = {"type": "op", "params": {"replace": 0}}
    validate_params(op, 0, rules)
    assert op["params"]["replace"] == "0"
    assert isinstance(op["params"]["replace"], str)


def test_string_keys_coerces_float_to_str():
    """float 值强转为 str(\"1.5\")。"""
    rules = {"op": ParamRule(string_keys=("replace",))}
    op = {"type": "op", "params": {"replace": 1.5}}
    validate_params(op, 0, rules)
    assert op["params"]["replace"] == "1.5"


def test_string_keys_mutates_same_dict_object():
    """string_keys 强转是就地修改调用方传入的 params(同一对象 identity)。

    契约要求:op_parser 下游 re.subn 使用的是同一 params 引用,若实现改成返回 copy
    则调用方拿不到强转结果。保留原引用断言其被改。
    """
    rules = {"op": ParamRule(string_keys=("find",))}
    op = {"type": "op", "params": {"find": 2024}}
    params_ref = op["params"]
    validate_params(op, 0, rules)
    assert params_ref["find"] == "2024"  # 同一对象被就地修改


# ---------------------------------------------------------------------------
# regex_key:空串 vs 缺失键(均放行,锁定 if pattern: 短路)
# ---------------------------------------------------------------------------


def test_regex_key_empty_string_passes():
    """regex_key 值为空串 → 放行(必填性由 required 负责,空模式不编译)。"""
    rules = {"op": ParamRule(regex_key="pattern")}
    ok, msg = validate_params({"type": "op", "params": {"pattern": ""}}, 0, rules)
    assert ok and msg == ""


def test_regex_key_missing_passes():
    """regex_key 键缺失 → 放行(同空串语义)。"""
    rules = {"op": ParamRule(regex_key="pattern")}
    ok, msg = validate_params({"type": "op", "params": {}}, 0, rules)
    assert ok and msg == ""
