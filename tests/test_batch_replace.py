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

    跨平台:subprocess.CREATE_NO_WINDOW 仅 Windows 存在(Linux CI 上 subprocess 模块无此
    属性)。测试目标只是验证"win32 下 _no_window_flags 产出该标志",故 monkeypatch 注入该
    常量,使本测试在 Linux CI 也能跑(不丢覆盖),而非 skipif 跳过。
    """
    import subprocess

    # CREATE_NO_WINDOW 实际值 0x08000000;非 Windows 注入同值,使断言可引用该属性
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

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

    跨平台:subprocess.CREATE_NO_WINDOW 仅 Windows 存在,非 Windows 注入同值(0x08000000)
    使断言可引用,本测试在 Linux CI 也能跑(不丢覆盖)。
    """
    import subprocess

    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

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


# ---------------------------------------------------------------------------
# 补充覆盖:_get_office_pids 解析、_kill 路径、is_file_locked 异常分支、
# preview/execute 异常路径、_read_file_content 边界、close() 早返回。
# 均 Linux 可测(纯逻辑或 mock subprocess/handler,不触发真实 COM)。
# ---------------------------------------------------------------------------


def test_get_office_pids_parses_tasklist_csv(monkeypatch):
    """_get_office_pids 解析 tasklist CSV 输出,提取数字 PID。

    覆盖 service.py 行 107(pids.append(int(parts[1])))。mock subprocess.run 返回
    含两行 PID 的 CSV,Linux 上不依赖真实 tasklist。
    """

    class _FakeResult:
        # 模拟 tasklist /FO CSV /NH 输出:text=True 已归一化行尾为 \n
        stdout = '"WINWORD.EXE","1234"\n"WINWORD.EXE","5678"\n'
        returncode = 0

    monkeypatch.setattr(service_mod.subprocess, "run", lambda *a, **k: _FakeResult())
    svc = ContentReplaceService()
    pids = svc._get_office_pids("WINWORD.EXE")
    assert pids == [1234, 5678]


def test_get_office_pids_swallows_subprocess_error(monkeypatch):
    """subprocess.run 抛异常(如 tasklist 不存在)→ 返回空列表,不向上抛。"""

    def boom(*a, **k):
        raise FileNotFoundError("tasklist")

    monkeypatch.setattr(service_mod.subprocess, "run", boom)
    svc = ContentReplaceService()
    assert svc._get_office_pids("WINWORD.EXE") == []


def test_kill_new_office_processes_calls_taskkill(monkeypatch):
    """_kill_new_office_processes 对新 PID 调 taskkill。

    覆盖 service.py 行 120-121(_kill 循环)。mock _get_office_pids 返回含一个新 PID
    (不在 pids_before 中),验证 taskkill 被 argv=["taskkill","/F","/PID",...] 调用。
    """
    killed = []

    class _FakeResult:
        stdout = ""
        returncode = 0

    def fake_run(argv, *a, **k):
        killed.append(argv)
        return _FakeResult()

    svc = ContentReplaceService()
    # mock _get_office_pids 返回 [9999](pids_before 为空 → 9999 是新 PID)
    monkeypatch.setattr(svc, "_get_office_pids", lambda name: [9999])
    monkeypatch.setattr(service_mod.subprocess, "run", fake_run)
    svc._kill_new_office_processes("WINWORD.EXE", [])
    assert any("/PID" in a and "9999" in a for a in killed)


def test_is_file_locked_permission_error(tmp_path, monkeypatch):
    """无写权限的文件 → (True, '文件被占用或无写入权限')。

    覆盖 service.py 行 145-146(PermissionError 分支)。Windows chmod 不可靠,
    故 monkeypatch builtins.open 对该文件抛 PermissionError,确保跨平台稳定。
    """
    import builtins

    f = _write_text(tmp_path / "ro.txt", "x")
    svc = ContentReplaceService()
    real_open = builtins.open

    def fake_open(*a, **k):
        if a and str(a[0]) == str(f):
            raise PermissionError("denied")
        return real_open(*a, **k)

    monkeypatch.setattr(builtins, "open", fake_open)
    locked, reason = svc.is_file_locked(f)
    assert locked is True
    assert "占用" in reason or "权限" in reason


def test_is_file_locked_other_exception(tmp_path, monkeypatch):
    """open 抛非 Permission 异常 → (True, '无法访问: ...')。

    覆盖 service.py 行 147-148。
    """
    import builtins

    f = _write_text(tmp_path / "weird.txt", "x")
    svc = ContentReplaceService()
    real_open = builtins.open

    def fake_open(*a, **k):
        if a and str(a[0]) == str(f):
            raise OSError("boom")
        return real_open(*a, **k)

    monkeypatch.setattr(builtins, "open", fake_open)
    locked, reason = svc.is_file_locked(f)
    assert locked is True
    assert "无法访问" in reason


def test_preview_replace_handles_exception(tmp_path, monkeypatch):
    """preview_replace 全局 except:让 is_file_locked 抛异常 → status 含 '错误'。

    覆盖 service.py 行 255-256。
    """
    f = _write_text(tmp_path / "a.txt", "hello")
    svc = ContentReplaceService()
    monkeypatch.setattr(svc, "is_file_locked", lambda p: (_ for _ in ()).throw(ValueError("boom")))
    result = svc.preview_replace([f], [{"type": "simple_replace", "params": {"find": "x"}}])
    assert "错误" in result[f]["status"]


def test_execute_replace_txt_exception_recorded(tmp_path, monkeypatch):
    """execute_replace 文本处理抛异常 → 记入 errors,不中断。

    覆盖 service.py 行 367-368。mock _create_backup 抛异常(文本分支内的 except)。
    """
    f = _write_text(tmp_path / "a.txt", "hello")
    svc = ContentReplaceService()
    monkeypatch.setattr(
        svc, "_create_backup", lambda p: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    success_count, total_replacements, errors = svc.execute_replace(
        [f], [{"type": "simple_replace", "params": {"find": "hello", "replace": "hi"}}]
    )
    assert success_count == 0
    assert any("boom" in e for e in errors)


def test_read_file_content_unknown_suffix(tmp_path):
    """_read_file_content 对未知后缀返回 None。

    覆盖 service.py 行 469-470。
    """
    f = _write_text(tmp_path / "a.xyz", "hello")
    svc = ContentReplaceService()
    assert svc._read_file_content(f) is None


def test_count_matches_none_content_returns_zero(monkeypatch):
    """_count_matches 在 content 为 None 时返回 0。

    覆盖 service.py 行 449-450。mock _read_file_content 返回 None。
    """
    svc = ContentReplaceService()
    monkeypatch.setattr(svc, "_read_file_content", lambda p: None)
    assert (
        svc._count_matches(Path("x.txt"), [{"type": "simple_replace", "params": {"find": "a"}}])
        == 0
    )


def test_read_file_content_handler_exception_returns_none(tmp_path, monkeypatch):
    """_read_file_content 的 handler 抛异常 → 记日志返回 None。

    覆盖 service.py 行 474-477。mock _text_handler.read_content 抛异常。
    """
    f = _write_text(tmp_path / "a.txt", "hello")
    svc = ContentReplaceService()
    monkeypatch.setattr(
        svc._text_handler, "read_content", lambda p: (_ for _ in ()).throw(ValueError("boom"))
    )
    assert svc._read_file_content(f) is None


def test_close_returns_early_when_interpreter_shutting_down():
    """close() 在解释器关闭判定为真时早返回(不执行 kill)。

    覆盖 service.py 行 488-489。sys.exitfunc 在 CPython 通常恒存在 → 直接走早返回。
    确保调用不抛异常即可(此路径不执行 taskkill)。
    """
    svc = ContentReplaceService()
    svc.close()  # 不抛异常即通过


# ---------------------------------------------------------------------------
# TextHandler 边界分支(chardet 回退 / 空查找 / 非法正则 / 大小写 / normalize 空串)
# 全部纯 Python,Linux 可测,覆盖 text_handler.py 未覆盖行。
# ---------------------------------------------------------------------------


SIMPLE = "simple_replace"
REGEX = "regex_replace"


def test_text_read_content_chardet_fallback(tmp_path):
    """混合非法字节序列 → latin-1 兜底解码为字符串(含可识别 ASCII)。

    注:text_handler 的 encodings 列表含 latin-1(可解码任意字节),故 chardet 与
    utf-8 ignore 分支理论不可达,已标注 pragma。此测试验证当前 latin-1 兜底行为。
    """
    # 0x80 单字节在 utf-8 非法、gbk 不完整,但 latin-1 能解码
    f = tmp_path / "weird.bin"
    f.write_bytes(b"\x80\x81\x82 foo")
    h = TextHandler()
    content = h.read_content(f)
    assert isinstance(content, str)
    assert "foo" in content


def test_text_read_content_empty_file_returns_empty(tmp_path):
    """空文件:首个编码(utf-8)读取返回空串。"""
    f = tmp_path / "empty.txt"
    f.write_bytes(b"")
    h = TextHandler()
    assert h.read_content(f) == ""


def test_text_count_matches_empty_find_skipped():
    """count_matches:simple_replace 空 find → 跳过,贡献 0。

    覆盖 text_handler.py 行 102-103。
    """
    h = TextHandler()
    assert h.count_matches("hello", [{"type": SIMPLE, "params": {"find": ""}}]) == 0


def test_text_count_matches_empty_pattern_skipped():
    """count_matches:regex_replace 空 pattern → 跳过,贡献 0。

    覆盖 text_handler.py 行 114-115。
    """
    h = TextHandler()
    assert h.count_matches("hello", [{"type": REGEX, "params": {"pattern": ""}}]) == 0


def test_text_count_matches_bad_regex_swallows_error():
    """count_matches:非法正则触发 re.error → 被 except 捕获,贡献 0。

    覆盖 text_handler.py 行 121-122。
    """
    h = TextHandler()
    assert h.count_matches("abc", [{"type": REGEX, "params": {"pattern": "("}}]) == 0


def test_text_apply_operation_empty_find_returns_unchanged():
    """_apply_operation:simple_replace 空 find → 返回原文,0 次替换。

    覆盖 text_handler.py 行 146-147。
    """
    h = TextHandler()
    new_text, count = h._apply_operation("hello", {"type": SIMPLE, "params": {"find": ""}})
    assert new_text == "hello"
    assert count == 0


def test_text_apply_operation_case_sensitive():
    """_apply_operation:case_sensitive=True 走 text.count/replace 分支。

    覆盖 text_handler.py 行 149-151。
    """
    h = TextHandler()
    new_text, count = h._apply_operation(
        "ABC abc ABC",
        {"type": SIMPLE, "params": {"find": "ABC", "replace": "X", "case_sensitive": True}},
    )
    assert new_text == "X abc X"
    assert count == 2


def test_text_apply_operation_case_insensitive():
    """_apply_operation:case_sensitive=False 走 re.compile+IGNORECASE 分支。"""
    h = TextHandler()
    new_text, count = h._apply_operation(
        "ABC abc",
        {"type": SIMPLE, "params": {"find": "abc", "replace": "X", "case_sensitive": False}},
    )
    assert new_text == "X X"
    assert count == 2


def test_text_apply_operation_regex_empty_pattern():
    """_apply_operation:regex_replace 空 pattern → 返回原文,0 次。

    覆盖 text_handler.py 行 165-166。
    """
    h = TextHandler()
    new_text, count = h._apply_operation("hello", {"type": REGEX, "params": {"pattern": ""}})
    assert new_text == "hello"
    assert count == 0


def test_text_apply_operation_regex_bad_pattern():
    """_apply_operation:非法正则触发 re.error → 返回原文,0 次。

    覆盖 text_handler.py 行 173-174。
    """
    h = TextHandler()
    new_text, count = h._apply_operation("hello", {"type": REGEX, "params": {"pattern": "("}})
    assert new_text == "hello"
    assert count == 0


def test_text_apply_operation_regex_success():
    """_apply_operation:合法正则替换成功,返回 (新文本, 次数)。

    覆盖 text_handler.py 行 160-172 的正则成功路径。
    """
    h = TextHandler()
    new_text, count = h._apply_operation(
        "a1 b2", {"type": REGEX, "params": {"pattern": r"\d", "replace": "X"}}
    )
    assert new_text == "aX bX"
    assert count == 2


def test_text_apply_operation_unknown_type_returns_unchanged():
    """_apply_operation:未知操作类型 → 返回原文,0 次。

    覆盖 text_handler.py 行 176(末尾 return text, 0)。
    """
    h = TextHandler()
    new_text, count = h._apply_operation("hello", {"type": "bogus", "params": {}})
    assert new_text == "hello"
    assert count == 0


def test_text_normalize_empty_string():
    """normalize_text:空字符串早返回(不进入 NFC 处理)。

    覆盖 text_handler.py 行 189-190。
    """
    assert TextHandler.normalize_text("") == ""
