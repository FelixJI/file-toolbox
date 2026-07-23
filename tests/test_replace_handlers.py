"""Word/Excel 替换处理器纯逻辑方法的单元测试。

仅覆盖 `_count_matches_in_text`(纯字符串/正则处理,不依赖 COM)。
通过 `Handler.__new__(Handler)` 绕过 `__init__`,避免触发 COM/Office 依赖
(`__init__` 仅注入 PID 管理回调,本测试用不到)。
"""

from file_toolbox.core.batch_replace.handlers.excel_handler import ExcelHandler
from file_toolbox.core.batch_replace.handlers.word_handler import WordHandler

SIMPLE = "simple_replace"
REGEX = "regex_replace"


def _word() -> WordHandler:
    """构造一个不触发 __init__(无 COM)的 WordHandler 实例。"""
    return WordHandler.__new__(WordHandler)


def _excel() -> ExcelHandler:
    """构造一个不触发 __init__(无 COM)的 ExcelHandler 实例。"""
    return ExcelHandler.__new__(ExcelHandler)


# ---------------------------------------------------------------------------
# 简单文本匹配计数
# ---------------------------------------------------------------------------


def test_word_count_simple_multiple_matches():
    h = _word()
    n = h._count_matches_in_text(
        "hello hello world",
        [{"type": SIMPLE, "params": {"find": "hello"}}],
    )
    assert n == 2


def test_word_count_simple_single_match():
    h = _word()
    assert h._count_matches_in_text("abc", [{"type": SIMPLE, "params": {"find": "b"}}]) == 1


def test_word_count_simple_no_match():
    h = _word()
    assert (
        h._count_matches_in_text("nothing here", [{"type": SIMPLE, "params": {"find": "zzz"}}]) == 0
    )


# ---------------------------------------------------------------------------
# 大小写敏感 / 不敏感
# ---------------------------------------------------------------------------


def test_word_count_case_insensitive_default():
    """默认 case_sensitive=False:大小写不敏感。"""
    h = _word()
    n = h._count_matches_in_text(
        "Hello HELLO hello",
        [{"type": SIMPLE, "params": {"find": "hello"}}],
    )
    assert n == 3


def test_word_count_case_sensitive():
    """case_sensitive=True:只计精确大小写匹配。"""
    h = _word()
    n = h._count_matches_in_text(
        "Hello HELLO hello",
        [{"type": SIMPLE, "params": {"find": "Hello", "case_sensitive": True}}],
    )
    assert n == 1


# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------


def test_word_count_regex_digits():
    h = _word()
    n = h._count_matches_in_text(
        "a1 b2 c3",
        [{"type": REGEX, "params": {"pattern": r"\d"}}],
    )
    assert n == 3


def test_word_count_regex_year_pattern():
    h = _word()
    n = h._count_matches_in_text(
        "2023 2024 2025",
        [{"type": REGEX, "params": {"pattern": r"\d{4}"}}],
    )
    assert n == 3


def test_word_count_regex_ignore_case():
    """ignore_case=True:正则带 IGNORECASE 标志。"""
    h = _word()
    n = h._count_matches_in_text(
        "Foo FOO foo",
        [{"type": REGEX, "params": {"pattern": "foo", "ignore_case": True}}],
    )
    assert n == 3


def test_word_count_regex_case_sensitive_default():
    """默认 ignore_case=False:正则区分大小写。"""
    h = _word()
    n = h._count_matches_in_text(
        "Foo FOO foo",
        [{"type": REGEX, "params": {"pattern": "foo"}}],
    )
    assert n == 1


def test_word_count_regex_no_match():
    h = _word()
    assert h._count_matches_in_text("abc", [{"type": REGEX, "params": {"pattern": r"\d"}}]) == 0


# ---------------------------------------------------------------------------
# 边界情况:空 find / 坏正则 / 未知类型(与源码行为一致)
# ---------------------------------------------------------------------------


def test_word_count_empty_find_skipped():
    """空 find 字符串 → find_text 为假 → 该操作跳过,贡献 0。"""
    h = _word()
    assert h._count_matches_in_text("hello", [{"type": SIMPLE, "params": {"find": ""}}]) == 0


def test_word_count_empty_pattern_skipped():
    """空正则 pattern → 跳过,贡献 0。"""
    h = _word()
    assert h._count_matches_in_text("hello", [{"type": REGEX, "params": {"pattern": ""}}]) == 0


def test_word_count_bad_regex_returns_zero():
    """无效正则触发 re.error → 被 except 捕获,贡献 0(不抛异常)。"""
    h = _word()
    assert h._count_matches_in_text("abc", [{"type": REGEX, "params": {"pattern": "("}}]) == 0


def test_word_count_bad_regex_ignore_case_returns_zero():
    """无效正则 + ignore_case 同样被吞掉,返回 0。"""
    h = _word()
    assert (
        h._count_matches_in_text(
            "abc", [{"type": REGEX, "params": {"pattern": "(", "ignore_case": True}}]
        )
        == 0
    )


def test_word_count_unknown_op_type_ignored():
    """未知操作类型 → 两分支都不命中,贡献 0。"""
    h = _word()
    assert h._count_matches_in_text("hello", [{"type": "bogus", "params": {"find": "x"}}]) == 0


def test_word_count_missing_params_key():
    """操作 dict 缺 params 键 → params={},find 默认 '' → 贡献 0。"""
    h = _word()
    assert h._count_matches_in_text("hello", [{"type": SIMPLE}]) == 0


def test_word_count_empty_operations():
    """空操作列表 → 0。"""
    h = _word()
    assert h._count_matches_in_text("hello", []) == 0


# ---------------------------------------------------------------------------
# 多操作累加
# ---------------------------------------------------------------------------


def test_word_count_multiple_operations_summed():
    """多个操作的总匹配数应累加。"""
    h = _word()
    n = h._count_matches_in_text(
        "hello world 2024",
        [
            {"type": SIMPLE, "params": {"find": "hello"}},
            {"type": SIMPLE, "params": {"find": "o"}},  # 出现在 hello & world = 2
            {"type": REGEX, "params": {"pattern": r"\d{4}"}},
        ],
    )
    assert n == 1 + 2 + 1


# ===========================================================================
# ExcelHandler:同样覆盖(其 _count_matches_in_text 逻辑与 Word 完全一致,
# 但属独立实现,需分别测试以防止回归漂移)
# ===========================================================================


def test_excel_count_simple_multiple_matches():
    h = _excel()
    assert (
        h._count_matches_in_text(
            "hello hello world",
            [{"type": SIMPLE, "params": {"find": "hello"}}],
        )
        == 2
    )


def test_excel_count_case_insensitive_default():
    h = _excel()
    n = h._count_matches_in_text(
        "Hello HELLO hello",
        [{"type": SIMPLE, "params": {"find": "hello"}}],
    )
    assert n == 3


def test_excel_count_case_sensitive():
    h = _excel()
    n = h._count_matches_in_text(
        "Hello HELLO hello",
        [{"type": SIMPLE, "params": {"find": "Hello", "case_sensitive": True}}],
    )
    assert n == 1


def test_excel_count_regex_digits():
    h = _excel()
    assert h._count_matches_in_text("a1 b2", [{"type": REGEX, "params": {"pattern": r"\d"}}]) == 2


def test_excel_count_regex_ignore_case():
    h = _excel()
    n = h._count_matches_in_text(
        "Foo FOO foo",
        [{"type": REGEX, "params": {"pattern": "foo", "ignore_case": True}}],
    )
    assert n == 3


def test_excel_count_empty_find_skipped():
    h = _excel()
    assert h._count_matches_in_text("hello", [{"type": SIMPLE, "params": {"find": ""}}]) == 0


def test_excel_count_bad_regex_returns_zero():
    h = _excel()
    assert h._count_matches_in_text("abc", [{"type": REGEX, "params": {"pattern": "("}}]) == 0


def test_excel_count_unknown_op_type_ignored():
    h = _excel()
    assert h._count_matches_in_text("hello", [{"type": "bogus", "params": {"find": "x"}}]) == 0


def test_excel_count_empty_operations():
    h = _excel()
    assert h._count_matches_in_text("hello", []) == 0


def test_excel_count_multiple_operations_summed():
    h = _excel()
    n = h._count_matches_in_text(
        "hello world 2024",
        [
            {"type": SIMPLE, "params": {"find": "hello"}},
            {"type": REGEX, "params": {"pattern": r"\d{4}"}},
        ],
    )
    assert n == 2  # 1 + 1
