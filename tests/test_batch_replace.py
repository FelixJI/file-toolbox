from pathlib import Path

from file_toolbox.core.batch_replace.handlers.text_handler import TextHandler
from file_toolbox.core.batch_replace.types import ReplaceOperationType
from file_toolbox.core.batch_replace.service import ContentReplaceService


def test_text_count_matches_simple():
    h = TextHandler()
    n = h.count_matches("hello hello world", [{"type": "simple_replace", "params": {"find": "hello"}}])
    assert n == 2


def test_text_count_matches_case_insensitive():
    h = TextHandler()
    n = h.count_matches("Hello HELLO", [{"type": "simple_replace", "params": {"find": "hello"}}])
    assert n == 2


def test_text_count_matches_case_sensitive():
    h = TextHandler()
    n = h.count_matches(
        "Hello HELLO",
        [{"type": "simple_replace", "params": {"find": "Hello", "case_sensitive": True}}],
    )
    assert n == 1


def test_text_count_matches_regex():
    h = TextHandler()
    n = h.count_matches("2023 2024 2025", [{"type": "regex_replace", "params": {"pattern": r"\d{4}"}}])
    assert n == 3


def test_text_replace_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    h = TextHandler()
    count = h.replace_file(
        f, [{"type": "simple_replace", "params": {"find": "hello", "replace": "hi"}}]
    )
    assert count == 1
    assert f.read_text(encoding="utf-8") == "hi world"


def test_text_normalize_strips_zero_width():
    assert TextHandler.normalize_text("a\u200bb") == "ab"


def test_text_read_multiple_encodings(tmp_path):
    f = tmp_path / "gbk.txt"
    f.write_bytes("你好".encode("gbk"))
    h = TextHandler()
    assert "你好" in h.read_content(f)


def test_replace_operation_type_enum():
    assert ReplaceOperationType.SIMPLE_REPLACE.value == "simple_replace"
    assert ReplaceOperationType.REGEX_REPLACE.value == "regex_replace"


def test_service_operation_types():
    svc = ContentReplaceService()
    types = svc.get_operation_types()
    assert "simple_replace" in types
    assert "regex_replace" in types


def test_service_is_supported():
    svc = ContentReplaceService()
    assert svc.is_supported_file(Path("a.docx")) is True
    assert svc.is_supported_file(Path("a.xlsx")) is True
    assert svc.is_supported_file(Path("a.txt")) is True
    assert svc.is_supported_file(Path("a.xyz")) is False


def test_service_validate_empty_find():
    svc = ContentReplaceService()
    ok, msg = svc._validate_params({"type": "simple_replace", "params": {"find": ""}}, 0)
    assert ok is False


def test_service_validate_bad_regex():
    svc = ContentReplaceService()
    ok, msg = svc._validate_params({"type": "regex_replace", "params": {"pattern": "("}}, 0)
    assert ok is False
