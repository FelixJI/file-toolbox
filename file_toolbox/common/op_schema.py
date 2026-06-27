"""操作参数验证 —— 声明式规则表驱动,消除各 service 中重复的验证长链。

各业务 service(replace/rename)声明自己的参数规则表(REQUIRED_PARAMS / REGEX_PARAMS),
再调用本模块的 :func:`validate_params` 完成具体校验。
这样"必填字段""正则编译"两类通用校验只有一份实现。
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

# 业务自定义校验回调签名:(operation, index) -> (ok, msg)
ExtraValidator = Callable[[dict, int], "tuple[bool, str]"]


@dataclass(frozen=True)
class ParamRule:
    """单个操作类型的参数校验规则。

    - required: 这些键不能为空(空字符串/None/缺失均视为无效)。
    - empty_messages: required 键 -> 该键为空时的中文提示(缺省回退到 "{key} 不能为空")。
    - regex_key: 该键的值需能被 re.compile 编译为合法正则(且为必填)。
    - extra: 业务自定义校验 (operation, index) -> (ok, msg),返回 (True,"") 表示通过。
    """

    required: tuple[str, ...] = ()
    empty_messages: dict[str, str] = field(default_factory=dict)
    regex_key: str | None = None
    extra: ExtraValidator | None = None


def _is_empty(value) -> bool:
    """空字符串/None 视为缺失。"""
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_params(
    operation: dict,
    index: int,
    rules: dict[str, ParamRule],
    *,
    label: str = "操作",
) -> tuple[bool, str]:
    """根据规则表校验单个 operation 的参数。

    Args:
        operation: {"type": ..., "params": {...}}
        index: 操作序号(用于错误消息,0 基)。
        rules: 操作类型 -> ParamRule 的映射。
        label: 错误消息前缀,如 "操作"。

    Returns:
        (是否有效, 错误消息)。
    """
    op_type: str | None = operation.get("type")
    params = operation.get("params", {})
    rule = rules.get(op_type) if op_type is not None else None

    if rule is None:
        # 无规则约束的操作类型视为通过(类型合法性由调用方/基类先行校验)
        return True, ""

    n = index + 1

    # 1. 必填字段非空
    for key in rule.required:
        if _is_empty(params.get(key)):
            msg = rule.empty_messages.get(key, f"{key} 不能为空")
            return False, f"{label} {n}: {msg}"

    # 2. 正则字段可编译
    if rule.regex_key is not None:
        pattern = params.get(rule.regex_key, "")
        if pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                return False, f"{label} {n}: 正则表达式错误 - {e!s}"

    # 3. 业务自定义校验
    if rule.extra is not None:
        return rule.extra(operation, index)

    return True, ""
