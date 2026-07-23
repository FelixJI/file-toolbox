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
