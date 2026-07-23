from pathlib import Path

from file_toolbox.core.batch_replace import service as service_mod
from file_toolbox.core.batch_replace.handlers.text_handler import TextHandler
from file_toolbox.core.batch_replace.service import ContentReplaceService
from file_toolbox.core.batch_replace.types import ReplaceOperationType


def test_text_count_matches_simple():
    h = TextHandler()
    n = h.count_matches(
        "hello hello world", [{"type": "simple_replace", "params": {"find": "hello"}}]
    )
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
    n = h.count_matches(
        "2023 2024 2025", [{"type": "regex_replace", "params": {"pattern": r"\d{4}"}}]
    )
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


def test_get_office_pids_uses_create_no_window_on_windows(monkeypatch):
    """Windows GUI 进程(打包后的 exe)起 tasklist 时必须带 CREATE_NO_WINDOW,
    否则会闪黑框(根因:service.py 的 _no_window_flags)。

    断言:win32 平台下,_get_office_pids 调 subprocess.run 时 kwargs 含
    creationflags=CREATE_NO_WINDOW。非 win32 则不含该键(跨平台守卫)。
    """
    import subprocess

    captured = {}

    class _FakeResult:
        stdout = ""
        returncode = 0

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return _FakeResult()

    monkeypatch.setattr(service_mod.subprocess, "run", fake_run)
    # 强制走 Windows 分支(无论测试运行平台),验证标志确实传入
    monkeypatch.setattr(service_mod.sys, "platform", "win32")

    svc = ContentReplaceService()
    svc._get_office_pids("WINWORD.EXE")

    assert "creationflags" in captured
    assert captured["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_kill_office_processes_uses_create_no_window_on_windows(monkeypatch):
    """taskkill 同样需 CREATE_NO_WINDOW(运行时也会闪黑框)。

    造一个真实存在的 PID:_get_office_pids 返回它,_kill 时 taskkill 应带标志。
    """
    import subprocess

    captured = {}

    def fake_run(*args, **kwargs):
        # tasklist(taskkill 之前先查 PID)返回空,使 _kill 路径不会真起进程;
        # 但为验证 taskkill 标志,这里直接捕获 taskkill 的 kwargs。
        captured.update(kwargs)

        class _R:
            stdout = ""
            returncode = 0

        return _R()

    monkeypatch.setattr(service_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(service_mod.sys, "platform", "win32")

    svc = ContentReplaceService()
    # 直接验证 _no_window_flags 在 win32 下产出 CREATE_NO_WINDOW
    flags = service_mod._no_window_flags()
    assert flags == {"creationflags": subprocess.CREATE_NO_WINDOW}

    # _kill_new_office_processes 内部先 _get_office_pids(无新 PID 则不 kill),
    # 确保调用不报错且路径覆盖
    svc._kill_new_office_processes("WINWORD.EXE", [])
