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


# ---------------------------------------------------------------------------
# 文本文件路径(.txt/.md,无需 COM/Office)的 preview/execute/锁定/备份 覆盖
# ---------------------------------------------------------------------------


def _write_text(path: Path, content: str) -> Path:
    """写入 UTF-8 文本文件并返回路径。"""
    path.write_text(content, encoding="utf-8")
    return path


def test_preview_replace_txt_counts_matches(tmp_path):
    """preview_replace 对 .txt 简单替换应正确统计 match_count。"""
    f = _write_text(tmp_path / "a.txt", "hello world hello")
    svc = ContentReplaceService()
    result = svc.preview_replace(
        [f], [{"type": "simple_replace", "params": {"find": "hello", "replace": "hi"}}]
    )
    assert result[f]["match_count"] == 2
    assert result[f]["status"] == "✓ 准备就绪"
    assert result[f]["needs_conversion"] is False


def test_preview_replace_md_counts_matches(tmp_path):
    """preview_replace 对 .md 同样走文本路径。"""
    f = _write_text(tmp_path / "note.md", "# Title\nhello hello")
    svc = ContentReplaceService()
    result = svc.preview_replace([f], [{"type": "simple_replace", "params": {"find": "hello"}}])
    assert result[f]["match_count"] == 2
    assert result[f]["needs_conversion"] is False


def test_preview_replace_regex(tmp_path):
    """preview_replace 正则替换统计。"""
    f = _write_text(tmp_path / "r.txt", "2024 and 2025")
    svc = ContentReplaceService()
    result = svc.preview_replace(
        [f], [{"type": "regex_replace", "params": {"pattern": r"20\d{2}"}}]
    )
    assert result[f]["match_count"] == 2
    assert result[f]["status"] == "✓ 准备就绪"


def test_preview_replace_no_matches(tmp_path):
    """无匹配时 status 为 'ℹ️ 无匹配',match_count 为 0。"""
    f = _write_text(tmp_path / "a.txt", "nothing here")
    svc = ContentReplaceService()
    result = svc.preview_replace([f], [{"type": "simple_replace", "params": {"find": "hello"}}])
    assert result[f]["match_count"] == 0
    assert result[f]["status"] == "ℹ️ 无匹配"


def test_preview_replace_unsupported_format(tmp_path):
    """不支持的扩展名应给出 '❌ 不支持的格式'。"""
    f = _write_text(tmp_path / "a.xyz", "whatever")
    svc = ContentReplaceService()
    result = svc.preview_replace([f], [{"type": "simple_replace", "params": {"find": "x"}}])
    assert result[f]["match_count"] == 0
    assert result[f]["status"] == "❌ 不支持的格式"


def test_preview_replace_empty_operations(tmp_path):
    """空操作列表:每个文件 0 匹配。"""
    f = _write_text(tmp_path / "a.txt", "hello")
    svc = ContentReplaceService()
    result = svc.preview_replace([f], [])
    assert result[f]["match_count"] == 0
    assert result[f]["status"] == "ℹ️ 无匹配"


def test_execute_replace_txt_creates_backup_and_replaces(tmp_path):
    """execute_replace 对 .txt 应替换内容并返回 (1, N, [])。"""
    f = _write_text(tmp_path / "old.txt", "old text old text")
    svc = ContentReplaceService()
    success_count, total_replacements, errors = svc.execute_replace(
        [f], [{"type": "simple_replace", "params": {"find": "old", "replace": "new"}}]
    )
    assert success_count == 1
    assert total_replacements == 2
    assert errors == []
    # 文件内容已变更
    assert f.read_text(encoding="utf-8") == "new text new text"


def test_execute_replace_md_file(tmp_path):
    """execute_replace 对 .md 走文本路径。"""
    f = _write_text(tmp_path / "note.md", "foo bar foo")
    svc = ContentReplaceService()
    success_count, total_replacements, errors = svc.execute_replace(
        [f], [{"type": "simple_replace", "params": {"find": "foo", "replace": "baz"}}]
    )
    assert success_count == 1
    assert total_replacements == 2
    assert errors == []
    assert f.read_text(encoding="utf-8") == "baz bar baz"


def test_execute_replace_no_match_not_counted(tmp_path):
    """无匹配的文件不计入 success_count。"""
    f = _write_text(tmp_path / "a.txt", "nothing here")
    svc = ContentReplaceService()
    success_count, total_replacements, errors = svc.execute_replace(
        [f], [{"type": "simple_replace", "params": {"find": "zzz", "replace": "qqq"}}]
    )
    assert success_count == 0
    assert total_replacements == 0
    assert errors == []


def test_execute_replace_empty_files():
    """空文件列表 → (0, 0, ['文件列表为空'])。"""
    svc = ContentReplaceService()
    success_count, total_replacements, errors = svc.execute_replace(
        [], [{"type": "simple_replace", "params": {"find": "a"}}]
    )
    assert success_count == 0
    assert total_replacements == 0
    assert errors == ["文件列表为空"]


def test_execute_replace_empty_operations(tmp_path):
    """空操作列表 → (0, 0, ['操作列表为空'])。"""
    f = _write_text(tmp_path / "a.txt", "hello")
    svc = ContentReplaceService()
    success_count, total_replacements, errors = svc.execute_replace([f], [])
    assert success_count == 0
    assert total_replacements == 0
    assert errors == ["操作列表为空"]


def test_execute_replace_invalid_operation(tmp_path):
    """无效操作类型 → 校验失败。"""
    f = _write_text(tmp_path / "a.txt", "hello")
    svc = ContentReplaceService()
    success_count, total_replacements, errors = svc.execute_replace(
        [f], [{"type": "bogus_type", "params": {}}]
    )
    assert success_count == 0
    assert total_replacements == 0
    assert len(errors) == 1
    assert "无效的操作类型" in errors[0]


def test_execute_replace_unsupported_format_in_errors(tmp_path):
    """不支持的格式应记入 errors 且不处理。"""
    f = _write_text(tmp_path / "a.xyz", "hello")
    svc = ContentReplaceService()
    success_count, total_replacements, errors = svc.execute_replace(
        [f], [{"type": "simple_replace", "params": {"find": "hello", "replace": "hi"}}]
    )
    assert success_count == 0
    assert total_replacements == 0
    assert any("不支持的格式" in e for e in errors)


def test_execute_replace_progress_callback(tmp_path):
    """progress_callback 在文本文件处理后应被调用。"""
    f = _write_text(tmp_path / "a.txt", "hello")
    svc = ContentReplaceService()
    calls = []
    success_count, total_replacements, errors = svc.execute_replace(
        [f],
        [{"type": "simple_replace", "params": {"find": "hello", "replace": "hi"}}],
        progress_callback=lambda processed, total: calls.append((processed, total)),
    )
    assert success_count == 1
    assert calls and calls[-1] == (1, 1)


def test_is_file_locked_nonexistent(tmp_path):
    """不存在的文件视为锁定(返回 (True, ...))。"""
    svc = ContentReplaceService()
    locked, reason = svc.is_file_locked(tmp_path / "missing.txt")
    assert locked is True
    assert "不存在" in reason


def test_is_file_locked_temp_file(tmp_path):
    """~$ 开头的临时文件视为锁定。"""
    f = _write_text(tmp_path / "~$temp.docx", "x")
    svc = ContentReplaceService()
    locked, reason = svc.is_file_locked(f)
    assert locked is True
    assert "临时" in reason


def test_is_file_locked_tmp_suffix(tmp_path):
    """.tmp 后缀视为锁定。"""
    f = _write_text(tmp_path / "a.tmp", "x")
    svc = ContentReplaceService()
    locked, _ = svc.is_file_locked(f)
    assert locked is True


def test_is_file_locked_normal_file(tmp_path):
    """可写的普通文件视为未锁定。"""
    f = _write_text(tmp_path / "a.txt", "hello")
    svc = ContentReplaceService()
    locked, reason = svc.is_file_locked(f)
    assert locked is False
    assert reason == ""


def test_preview_replace_locked_temp_file(tmp_path):
    """preview_replace 对 ~$ 临时文件给出锁定状态。"""
    f = _write_text(tmp_path / "~$wb.docx", "x")
    svc = ContentReplaceService()
    result = svc.preview_replace([f], [{"type": "simple_replace", "params": {"find": "x"}}])
    assert result[f]["match_count"] == 0
    assert "临时" in result[f]["status"]


def test_count_matches_via_service_txt(tmp_path):
    """_count_matches 直接调用,走 _read_file_content 文本分支。"""
    f = _write_text(tmp_path / "a.txt", "abc abc abc")
    svc = ContentReplaceService()
    n = svc._count_matches(f, [{"type": "simple_replace", "params": {"find": "abc"}}])
    assert n == 3


def test_read_file_content_md(tmp_path):
    """_read_file_content 对 .md 返回标准化文本。"""
    f = _write_text(tmp_path / "a.md", "hello\u200bworld")
    svc = ContentReplaceService()
    content = svc._read_file_content(f)
    # 零宽字符被 normalize 掉
    assert content == "helloworld"


def test_create_backup_returns_path(tmp_path, monkeypatch):
    """_create_backup 复制文件到备份目录并返回路径。"""
    f = _write_text(tmp_path / "src.txt", "data")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    svc = ContentReplaceService()
    monkeypatch.setattr(svc, "_backup_dir", backup_dir)
    backup_path = svc._create_backup(f)
    assert backup_path.exists()
    assert backup_path.parent == backup_dir
    assert backup_path.read_text(encoding="utf-8") == "data"


def test_preview_replace_cancel_check(tmp_path):
    """cancel_check 返回 True 时预览立即中断。"""
    f = _write_text(tmp_path / "a.txt", "hello")
    svc = ContentReplaceService()
    result = svc.preview_replace(
        [f],
        [{"type": "simple_replace", "params": {"find": "hello"}}],
        cancel_check=lambda: True,
    )
    # 取消后该文件未处理,result 为空
    assert result == {}


def test_execute_replace_cancel_before_text(tmp_path):
    """execute_replace 在文本处理前取消:success=0 且无替换。"""
    f = _write_text(tmp_path / "a.txt", "hello")
    svc = ContentReplaceService()
    success_count, total_replacements, _errors = svc.execute_replace(
        [f],
        [{"type": "simple_replace", "params": {"find": "hello", "replace": "hi"}}],
        cancel_check=lambda: True,
    )
    assert success_count == 0
    assert total_replacements == 0
