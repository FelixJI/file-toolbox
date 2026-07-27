"""
内容替换类型定义与参数校验规则
"""

from enum import Enum

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
