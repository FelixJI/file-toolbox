"""
内容替换类型定义与参数校验规则
"""

import re
from enum import Enum
from typing import Any

from file_toolbox.common.op_schema import ParamRule


class ReplaceOperationType(Enum):
    """替换操作类型枚举"""

    SIMPLE_REPLACE = "simple_replace"  # 简单文本替换
    REGEX_REPLACE = "regex_replace"  # 正则表达式替换


# 参数校验规则表(声明式,由 ContentReplaceService._validate_params 复用)。
REPLACE_PARAM_RULES: dict[str, ParamRule] = {
    ReplaceOperationType.SIMPLE_REPLACE.value: ParamRule(
        required=("find",),
        empty_messages={"find": "查找文本不能为空"},
        # find/replace 是文本值:op_parser._coerce 会把裸数字(如 replace=2026)转 int,
        # 文本替换语义要求字符串,否则 re.subn/text.replace 收到 int 报 TypeError。
        string_keys=("find", "replace"),
    ),
    ReplaceOperationType.REGEX_REPLACE.value: ParamRule(
        required=("pattern",),
        empty_messages={"pattern": "正则表达式不能为空"},
        regex_key="pattern",
        string_keys=("replace",),
    ),
}


def count_text_matches(content: str, operations: list[dict[str, Any]]) -> int:
    """统计文本 content 中按 operations 规则可命中的匹配数。

    供 word/excel/text 三个 handler 复用,统一 simple/regex 两类替换的计数口径:
    - simple_replace:大小写敏感时 content.count(find),否则 lower() 后 count。
    - regex_replace:re.finditer 计数;非法 pattern 静默跳过(返回 0)。
    - 空 find/空 pattern 贡献 0。
    """
    total = 0
    for operation in operations:
        op_type = operation.get("type")
        params = operation.get("params", {})

        if op_type == ReplaceOperationType.SIMPLE_REPLACE.value:
            find_text = params.get("find", "")
            case_sensitive = params.get("case_sensitive", False)
            if not find_text:
                continue
            if case_sensitive:
                total += content.count(find_text)
            else:
                total += content.lower().count(find_text.lower())

        elif op_type == ReplaceOperationType.REGEX_REPLACE.value:
            pattern = params.get("pattern", "")
            ignore_case = params.get("ignore_case", False)
            if not pattern:
                continue
            try:
                flags = re.IGNORECASE if ignore_case else 0
                total += len(list(re.finditer(pattern, content, flags)))
            except re.error:
                pass

    return total
