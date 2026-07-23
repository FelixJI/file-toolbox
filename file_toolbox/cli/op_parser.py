"""解析 --op type:key=value,key=value 紧凑语法。"""

import re

# 匹配 key="quoted"|key=rawvalue
_KV_PATTERN = re.compile(r'(\w+)=(?:"([^"]*)"|([^,]*))')


class OpParseError(ValueError):
    """--op 解析错误。"""


def _coerce(value: str) -> int | bool | str:
    """把字符串值转为 int/bool/str。"""
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value


def parse_op(op_str: str) -> dict[str, object]:
    """解析单个 --op 字符串为 {"type":..., "params":{...}}。"""
    if ":" not in op_str:
        raise OpParseError(f"无效的 --op 格式(缺少冒号): {op_str!r}")
    type_part, params_part = op_str.split(":", 1)
    type_part = type_part.strip()
    if not type_part:
        raise OpParseError(f"无效的 --op 格式(缺少操作类型): {op_str!r}")

    # 检测空键(行首或逗号后紧跟 =):如 "=A" 或 "a=1,=B"
    if re.search(r"(?:^|,)\s*=", params_part):
        raise OpParseError(f"无效的 --op 参数键(空): {op_str!r}")

    params: dict[str, int | bool | str] = {}
    for m in _KV_PATTERN.finditer(params_part):
        key, quoted, raw = m.group(1), m.group(2), m.group(3)
        value = quoted if quoted is not None else raw
        params[key] = _coerce(value)
    return {"type": type_part, "params": params}


def parse_ops(op_strs: list[str]) -> list[dict[str, object]]:
    """解析多个 --op 字符串列表。"""
    return [parse_op(s) for s in op_strs]
