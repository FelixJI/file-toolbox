"""PDF 排序纯逻辑:从页面文字提取排序键、自然排序键、计算新页序。

全部为无 IO 纯函数,便于用普通字符串直接单测。
"""

from __future__ import annotations

import re

from file_toolbox.core.pdf_sort.constants import (
    ORDER_DESC,
    UNMATCHED_FAIL,
    UNMATCHED_FIRST,
)

_WHITESPACE_RE = re.compile(r"\s+")
_DIGIT_RUN_RE = re.compile(r"(\d+)")

# 自然排序键的元素:数字段 (0, int) 恒排在文字段 (1, str) 之前,
# 避免不同形态键(如 "N/A" 与 "2024-01-01")在相同位置出现 int 与 str 比较报错。
NaturalKeyPart = tuple[int, int] | tuple[int, str]


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """编译匹配格式,非法正则给中文错误(ValueError)。"""
    try:
        return re.compile(pattern)
    except re.error as e:
        raise ValueError(f"无效的匹配格式: {e}") from e


def extract_key(text: str, pattern: re.Pattern[str]) -> str | None:
    """从一页文字提取排序键:取首个匹配,捕获组 1(非 None)优先,否则整个匹配。

    依次对三个候选文本匹配,先命中者生效:
    1. 原始提取文字(含换行,pypdf 按行拼接);
    2. 空白折叠为单个空格(容忍 OCR 在词间插入的空格/换行);
    3. 去除全部空白(容忍中文被逐字拆开,如"出 库 日 期")。
    """
    candidates = (text, _WHITESPACE_RE.sub(" ", text), _WHITESPACE_RE.sub("", text))
    for candidate in candidates:
        if not candidate:
            continue
        m = pattern.search(candidate)
        if m:
            key = m.group(1) if m.re.groups and m.group(1) is not None else m.group(0)
            return key
    return None


def natural_key(value: str) -> tuple[NaturalKeyPart, ...]:
    """数字段按数值比较的自然排序键:'NO.9' < 'NO.10','2024-1-9' < '2024-1-10'。"""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part) for part in _DIGIT_RUN_RE.split(value)
    )


def compute_order(keys: list[str | None], order: str, unmatched: str) -> list[int] | None:
    """由每页排序键计算新页序(原页索引列表)。

    - 排序稳定:键相同的页保持原有先后(升序降序均如此);
    - unmatched=first/last:未匹配页保持原相对顺序置于最前/末尾;
    - unmatched=fail 且存在未匹配页:返回 None(调用方按失败处理)。
    """
    matched = [(idx, key) for idx, key in enumerate(keys) if key is not None]
    unmatched_idx = [idx for idx, key in enumerate(keys) if key is None]
    if unmatched_idx and unmatched == UNMATCHED_FAIL:
        return None
    ranked = sorted(matched, key=lambda item: natural_key(item[1]), reverse=order == ORDER_DESC)
    ordered = [idx for idx, _key in ranked]
    if unmatched_idx and unmatched == UNMATCHED_FIRST:
        return unmatched_idx + ordered
    return ordered + unmatched_idx
