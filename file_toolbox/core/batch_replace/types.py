"""
内容替换类型定义
"""

from enum import Enum


class ReplaceOperationType(Enum):
    """替换操作类型枚举"""

    SIMPLE_REPLACE = "simple_replace"  # 简单文本替换
    REGEX_REPLACE = "regex_replace"  # 正则表达式替换
