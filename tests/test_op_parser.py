import pytest

from file_toolbox.cli.op_parser import OpParseError, parse_op, parse_ops


def test_parse_single_op():
    ops = parse_ops(["add_prefix:prefix=项目_"])
    assert ops == [{"type": "add_prefix", "params": {"prefix": "项目_"}}]


def test_parse_multiple_ops():
    ops = parse_ops(["add_prefix:prefix=A", "add_suffix:text=B"])
    assert ops == [
        {"type": "add_prefix", "params": {"prefix": "A"}},
        {"type": "add_suffix", "params": {"text": "B"}},
    ]


def test_parse_multi_params():
    ops = parse_ops(["add_number:start=1,digits=3,position=start"])
    assert ops == [{"type": "add_number", "params": {"start": 1, "digits": 3, "position": "start"}}]


def test_parse_int_values_coerced():
    ops = parse_ops(["add_number:start=5,digits=2"])
    assert ops[0]["params"]["start"] == 5
    assert ops[0]["params"]["digits"] == 2
    assert isinstance(ops[0]["params"]["start"], int)


def test_parse_bool_values():
    ops = parse_ops(["simple_replace:find=a,replace=b,case_sensitive=true"])
    assert ops[0]["params"]["case_sensitive"] is True


def test_parse_bool_false():
    ops = parse_ops(["regex_replace:pattern=x,replace=y,ignore_case=false"])
    assert ops[0]["params"]["ignore_case"] is False


def test_parse_quoted_value_with_comma():
    ops = parse_ops(['simple_replace:find="a,b",replace=c'])
    assert ops[0]["params"]["find"] == "a,b"


def test_parse_quoted_value_with_equals():
    ops = parse_ops(['simple_replace:find="x=y",replace=z'])
    assert ops[0]["params"]["find"] == "x=y"


def test_parse_empty_list():
    assert parse_ops([]) == []


def test_parse_op_missing_colon_raises():
    with pytest.raises(OpParseError):
        parse_op("no_colon_here")


def test_parse_op_empty_type_raises():
    with pytest.raises(OpParseError):
        parse_op(":prefix=A")


def test_parse_op_empty_key_raises():
    with pytest.raises(OpParseError):
        parse_op("add_prefix:=A")


# ---------------------------------------------------------------------------
# _coerce:类型强转边界 —— 锁定当前行为(防静默类型错乱)
# ---------------------------------------------------------------------------
# _coerce 是所有 --op 值的共用强转层:true/false→bool,否则 int(),否则原样 str。
# 下列锁定其当前行为:未来若改强转逻辑(如支持 float / 保留前导零)这些测试应变红。


def test_coerce_leading_zero_int_destroys_zeros():
    """'007' → int 7(前导零丢失)。锁死:若值是发票号式 '007' 应声明 string_keys 保留。

    op_schema.string_keys 对 find/replace 等文本键会强转回 str,但任意未声明键仍走
    int() 截断前导零。这是已知行为,锁定以便未来 float 支持等改动有据可查。
    """
    from file_toolbox.cli.op_parser import _coerce

    assert _coerce("007") == 7
    assert isinstance(_coerce("007"), int)


def test_coerce_float_returns_str_not_float():
    """'2.5' / '1e3' → int() 失败 → 原样返回 str(当前不支持 float)。"""
    from file_toolbox.cli.op_parser import _coerce

    assert _coerce("2.5") == "2.5"
    assert isinstance(_coerce("2.5"), str)
    assert _coerce("1e3") == "1e3"


def test_coerce_bool_case_insensitive():
    """'True'/'FALSE' 等大小写变体 → bool(value.lower() 比较)。"""
    from file_toolbox.cli.op_parser import _coerce

    assert _coerce("True") is True
    assert _coerce("FALSE") is False
    assert _coerce("Yes") == "Yes"  # 非 true/false → 原样 str


def test_coerce_negative_int():
    """'-3' → int -3。"""
    from file_toolbox.cli.op_parser import _coerce

    assert _coerce("-3") == -3
    assert isinstance(_coerce("-3"), int)


def test_coerce_empty_string_returns_empty():
    """'' → int('') 失败 → 原样返回 ''。"""
    from file_toolbox.cli.op_parser import _coerce

    assert _coerce("") == ""


def test_parse_op_duplicate_keys_last_wins():
    """重复键 → 后值覆盖前值(无报错)。锁定当前 last-wins 行为。"""
    ops = parse_ops(["add_number:start=1,start=9"])
    assert ops[0]["params"]["start"] == 9
