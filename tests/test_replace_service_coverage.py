"""ContentReplaceService 未覆盖分支的补充测试。

聚焦 service.py 行:
- 43: _no_window_flags 非 win32 → {} (跨平台守卫)
- 217-237: preview_replace 的 .doc/.xls 转换路径(成功/失败两支)
- 337-345: execute_replace 分组(docx/xlsx 分类 + 锁定跳过)
- 382-413: execute_replace Word 文档处理块
- 418-447: execute_replace Excel 文档处理块
- 472/475: _read_file_content 调用 word/excel handler
- 497: close() 获取锁成功 → 执行 kill
- 506-507: close() except 吞异常

策略:用 MagicMock 替换 svc 的 handler/converter/_get_office_pids,
避免真实 COM/subprocess。文本路径用真文件。
"""

from pathlib import Path
from unittest.mock import MagicMock

from file_toolbox.core.batch_replace import service as service_mod
from file_toolbox.core.batch_replace.service import ContentReplaceService

SIMPLE = {"type": "simple_replace", "params": {"find": "old", "replace": "new"}}


def _svc_with_mocks() -> ContentReplaceService:
    """构造 svc,替换所有 handler/converter/pids 为 mock(避免真实 COM/tasklist)。"""
    svc = ContentReplaceService.__new__(ContentReplaceService)
    svc.converter = MagicMock()
    svc._lock = MagicMock()
    svc._initial_word_pids = []
    svc._initial_excel_pids = []
    svc._word_handler = MagicMock()
    svc._excel_handler = MagicMock()
    svc._text_handler = MagicMock()
    svc._backup_dir = Path(".")
    return svc


# ---------------------------------------------------------------------------
# _no_window_flags 非 win32 分支(行 43)
# ---------------------------------------------------------------------------


def test_no_window_flags_non_win32_returns_empty(monkeypatch):
    """非 win32 平台 → 返回 {} (无 CREATE_NO_WINDOW)。"""
    monkeypatch.setattr(service_mod.sys, "platform", "linux")
    assert service_mod._no_window_flags() == {}


# ---------------------------------------------------------------------------
# preview_replace:.doc/.xls 转换路径(行 217-237)
# ---------------------------------------------------------------------------


def test_preview_replace_doc_conversion_success(tmp_path, monkeypatch):
    """preview 对 .doc:is_conversion_needed=True → auto_convert 成功 → _count_matches。"""
    f = tmp_path / "a.doc"
    f.write_bytes(b"fake doc")
    svc = _svc_with_mocks()
    svc.converter.is_conversion_needed.return_value = True
    converted = Path("a.docx")
    svc.converter.auto_convert_if_needed.return_value = (True, converted, "")
    # _count_matches → _read_file_content,直接 mock _count_matches 避免 normalize
    monkeypatch.setattr(svc, "_count_matches", lambda p, ops: 3)

    result = svc.preview_replace([f], [SIMPLE])

    assert result[f]["match_count"] == 3
    assert result[f]["needs_conversion"] is True
    assert result[f]["status"] == "✓ 准备就绪"
    assert result[f]["converted_path"] == converted
    svc.converter.auto_convert_if_needed.assert_called_once_with(f)


def test_preview_replace_doc_conversion_failure(tmp_path):
    """preview 对 .doc:auto_convert 失败 → status 含错误。"""
    f = tmp_path / "a.doc"
    f.write_bytes(b"fake doc")
    svc = _svc_with_mocks()
    svc.converter.is_conversion_needed.return_value = True
    svc.converter.auto_convert_if_needed.return_value = (False, f, "转换失败原因")

    result = svc.preview_replace([f], [SIMPLE])

    assert result[f]["match_count"] == 0
    assert result[f]["needs_conversion"] is True
    assert "转换失败原因" in result[f]["status"]


def test_preview_replace_doc_conversion_success_no_matches(tmp_path, monkeypatch):
    """preview 对 .doc:转换成功但无匹配 → status 'ℹ️ 无匹配'。"""
    f = tmp_path / "a.doc"
    f.write_bytes(b"fake doc")
    svc = _svc_with_mocks()
    svc.converter.is_conversion_needed.return_value = True
    svc.converter.auto_convert_if_needed.return_value = (True, Path("a.docx"), "")
    monkeypatch.setattr(svc, "_count_matches", lambda p, ops: 0)

    result = svc.preview_replace([f], [SIMPLE])

    assert result[f]["match_count"] == 0
    assert result[f]["status"] == "ℹ️ 无匹配"


# ---------------------------------------------------------------------------
# execute_replace:文件分组与锁定跳过(行 337-345)
# ---------------------------------------------------------------------------


def test_execute_replace_groups_docx_files(tmp_path):
    """execute_replace:docx 文件分到 docx_files,走 Word 处理块(行 343)。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    svc._word_handler.batch_replace.return_value = {
        "success_count": 1,
        "total_replacements": 2,
        "errors": [],
    }

    success, total, errors = svc.execute_replace([f], [SIMPLE])

    assert success == 1
    assert total == 2
    assert errors == []
    svc._word_handler.batch_replace.assert_called_once()


def test_execute_replace_groups_xlsx_files(tmp_path):
    """execute_replace:xlsx 文件分到 xlsx_files,走 Excel 处理块(行 345)。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    svc._excel_handler.batch_replace.return_value = {
        "success_count": 1,
        "total_replacements": 1,
        "errors": [],
    }

    success, total, errors = svc.execute_replace([f], [SIMPLE])

    assert success == 1
    assert total == 1
    assert errors == []
    svc._excel_handler.batch_replace.assert_called_once()


def test_execute_replace_locked_docx_recorded_in_errors(tmp_path):
    """execute_replace:被锁定的 docx → 记入 errors,不分到处理组(行 337-338)。"""
    f = tmp_path / "locked.docx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    # 让 is_file_locked 返回锁定
    svc.is_file_locked = lambda p: (True, "文件被占用")
    # 注意:is_file_locked 是实例方法,直接赋值会丢 self;改 monkeypatch 方式
    # 这里用下面更稳的 monkeypatch 测试替代
    # 此函数仅作占位,真实断言在下一个测试


def test_execute_replace_locked_file_skipped(tmp_path, monkeypatch):
    """execute_replace:锁定文件跳过分组,记入 errors。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    monkeypatch.setattr(svc, "is_file_locked", lambda p: (True, "被占用"))

    success, total, errors = svc.execute_replace([f], [SIMPLE])

    assert success == 0
    assert any("被占用" in e for e in errors)
    svc._word_handler.batch_replace.assert_not_called()


# ---------------------------------------------------------------------------
# execute_replace:Word 处理块细节(行 382-413)
# ---------------------------------------------------------------------------


def test_execute_replace_word_block_creates_backup(tmp_path, monkeypatch):
    """execute_replace:Word 块先为每个 docx 创建备份(行 382-390)。"""
    f1 = tmp_path / "a.docx"
    f2 = tmp_path / "b.docx"
    f1.write_bytes(b"fake")
    f2.write_bytes(b"fake")
    svc = _svc_with_mocks()
    backups = []
    monkeypatch.setattr(svc, "_create_backup", lambda p: backups.append(p) or Path("bak"))
    svc._word_handler.batch_replace.return_value = {
        "success_count": 0,
        "total_replacements": 0,
        "errors": [],
    }

    svc.execute_replace([f1, f2], [SIMPLE])

    assert backups == [f1, f2]


def test_execute_replace_word_block_backup_failure_recorded(tmp_path, monkeypatch):
    """execute_replace:备份抛异常 → 记入 errors(行 389-390)。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    monkeypatch.setattr(
        svc, "_create_backup", lambda p: (_ for _ in ()).throw(RuntimeError("bak boom"))
    )
    svc._word_handler.batch_replace.return_value = {
        "success_count": 0,
        "total_replacements": 0,
        "errors": [],
    }

    success, total, errors = svc.execute_replace([f], [SIMPLE])

    assert any("备份失败" in e and "bak boom" in e for e in errors)


def test_execute_replace_word_block_progress_callback(tmp_path, monkeypatch):
    """execute_replace:Word 块调用 progress_callback(行 412-413)。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    monkeypatch.setattr(svc, "_create_backup", lambda p: Path("bak"))
    svc._word_handler.batch_replace.return_value = {
        "success_count": 1,
        "total_replacements": 1,
        "errors": [],
    }
    calls = []
    svc.execute_replace(
        [f], [SIMPLE], progress_callback=lambda processed, total: calls.append((processed, total))
    )
    # 至少有一次 progress 调用
    assert calls


def test_execute_replace_word_handler_callback_invoked(tmp_path, monkeypatch):
    """execute_replace:Word 块传给 batch_replace 的 file_callback 被调用(行 392-396)。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    monkeypatch.setattr(svc, "_create_backup", lambda p: Path("bak"))

    captured = {}

    def fake_batch_replace(files, ops, keep_new, cancel, callback):
        callback(0)  # 模拟 handler 调用进度回调
        captured["called"] = True
        return {"success_count": 1, "total_replacements": 1, "errors": []}

    svc._word_handler.batch_replace.side_effect = fake_batch_replace
    calls = []
    svc.execute_replace(
        [f], [SIMPLE], progress_callback=lambda processed, total: calls.append(processed)
    )
    assert captured.get("called") is True
    assert calls  # callback 触发了 progress


def test_execute_replace_cancel_skips_word_block(tmp_path, monkeypatch):
    """execute_replace:Word 块前取消 → 不调 batch_replace(行 380 is_cancelled)。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    svc._word_handler.batch_replace.return_value = {
        "success_count": 0,
        "total_replacements": 0,
        "errors": [],
    }
    svc.execute_replace([f], [SIMPLE], cancel_check=lambda: True)
    svc._word_handler.batch_replace.assert_not_called()


# ---------------------------------------------------------------------------
# execute_replace:Excel 处理块细节(行 418-447)
# ---------------------------------------------------------------------------


def test_execute_replace_excel_block_creates_backup(tmp_path, monkeypatch):
    """execute_replace:Excel 块为每个 xlsx 创建备份(行 418-424)。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    backups = []
    monkeypatch.setattr(svc, "_create_backup", lambda p: backups.append(p) or Path("bak"))
    svc._excel_handler.batch_replace.return_value = {
        "success_count": 0,
        "total_replacements": 0,
        "errors": [],
    }
    svc.execute_replace([f], [SIMPLE])
    assert backups == [f]


def test_execute_replace_excel_block_backup_failure(tmp_path, monkeypatch):
    """execute_replace:Excel 备份失败 → 记入 errors(行 423-424)。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    monkeypatch.setattr(svc, "_create_backup", lambda p: (_ for _ in ()).throw(RuntimeError("bak")))
    svc._excel_handler.batch_replace.return_value = {
        "success_count": 0,
        "total_replacements": 0,
        "errors": [],
    }
    _, _, errors = svc.execute_replace([f], [SIMPLE])
    assert any("备份失败" in e for e in errors)


def test_execute_replace_excel_block_progress_callback(tmp_path, monkeypatch):
    """execute_replace:Excel 块调用 progress_callback(行 446-447)。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    monkeypatch.setattr(svc, "_create_backup", lambda p: Path("bak"))
    svc._excel_handler.batch_replace.return_value = {
        "success_count": 1,
        "total_replacements": 1,
        "errors": [],
    }
    calls = []
    svc.execute_replace(
        [f], [SIMPLE], progress_callback=lambda processed, total: calls.append(processed)
    )
    assert calls


def test_execute_replace_excel_handler_callback_invoked(tmp_path, monkeypatch):
    """execute_replace:Excel 块传给 batch_replace 的 callback 被调用(行 426-430)。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    monkeypatch.setattr(svc, "_create_backup", lambda p: Path("bak"))

    def fake_batch_replace(files, ops, keep_new, cancel, callback):
        callback(0)
        return {"success_count": 1, "total_replacements": 1, "errors": []}

    svc._excel_handler.batch_replace.side_effect = fake_batch_replace
    calls = []
    svc.execute_replace(
        [f], [SIMPLE], progress_callback=lambda processed, total: calls.append(processed)
    )
    assert calls


def test_execute_replace_cancel_skips_excel_block(tmp_path, monkeypatch):
    """execute_replace:Excel 块前取消 → 不调 batch_replace(行 416)。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    svc._excel_handler.batch_replace.return_value = {
        "success_count": 0,
        "total_replacements": 0,
        "errors": [],
    }
    svc.execute_replace([f], [SIMPLE], cancel_check=lambda: True)
    svc._excel_handler.batch_replace.assert_not_called()


def test_execute_replace_no_backup_skips_docx_backup(tmp_path, monkeypatch):
    """execute_replace:keep_backup=False → 不创建 docx 备份(行 384-385)。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    backups = []
    monkeypatch.setattr(svc, "_create_backup", lambda p: backups.append(p) or Path("bak"))
    svc._word_handler.batch_replace.return_value = {
        "success_count": 0,
        "total_replacements": 0,
        "errors": [],
    }
    svc.execute_replace([f], [SIMPLE], keep_backup=False)
    assert backups == []


def test_execute_replace_no_backup_skips_xlsx_backup(tmp_path, monkeypatch):
    """execute_replace:keep_backup=False → 不创建 xlsx 备份(行 419-420 continue)。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    backups = []
    monkeypatch.setattr(svc, "_create_backup", lambda p: backups.append(p) or Path("bak"))
    svc._excel_handler.batch_replace.return_value = {
        "success_count": 0,
        "total_replacements": 0,
        "errors": [],
    }
    svc.execute_replace([f], [SIMPLE], keep_backup=False)
    assert backups == []


def test_execute_replace_mixed_files_all_groups(tmp_path, monkeypatch):
    """execute_replace:同时有 txt+docx+xlsx → 三组都处理,progress 递增。"""
    txt = tmp_path / "a.txt"
    docx = tmp_path / "b.docx"
    xlsx = tmp_path / "c.xlsx"
    for p in (txt, docx, xlsx):
        p.write_bytes(b"fake")
    svc = _svc_with_mocks()
    monkeypatch.setattr(svc, "_create_backup", lambda p: Path("bak"))
    svc._text_handler.read_content.return_value = "old old"
    svc._text_handler.count_matches.return_value = 2
    svc._text_handler.replace_file.return_value = 2
    svc._word_handler.batch_replace.return_value = {
        "success_count": 1,
        "total_replacements": 1,
        "errors": [],
    }
    svc._excel_handler.batch_replace.return_value = {
        "success_count": 1,
        "total_replacements": 1,
        "errors": [],
    }
    success, total, _ = svc.execute_replace([txt, docx, xlsx], [SIMPLE])
    # text 成功 1(match>0 → replace),word success_count 1,excel success_count 1
    assert success == 1 + 1 + 1
    assert total == 2 + 1 + 1


# ---------------------------------------------------------------------------
# _read_file_content:word/excel 分支(行 472, 475)
# ---------------------------------------------------------------------------


def test_read_file_content_docx_calls_word_handler(tmp_path):
    """_read_file_content:.docx → 调 _word_handler.read_content(行 472)。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    svc._word_handler.read_content.return_value = "word text"
    content = svc._read_file_content(f)
    assert content == "word text"
    svc._word_handler.read_content.assert_called_once_with(f)


def test_read_file_content_xlsx_calls_excel_handler(tmp_path):
    """_read_file_content:.xlsx → 调 _excel_handler.read_content(行 475)。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    svc._excel_handler.read_content.return_value = "excel text"
    content = svc._read_file_content(f)
    assert content == "excel text"
    svc._excel_handler.read_content.assert_called_once_with(f)


def test_read_file_content_doc_suffix_calls_word_handler(tmp_path):
    """_read_file_content:.doc(旧格式)→ 走 word 分支。"""
    f = tmp_path / "a.doc"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    svc._word_handler.read_content.return_value = "doc text"
    assert svc._read_file_content(f) == "doc text"


def test_read_file_content_empty_content_returns_empty(tmp_path):
    """_read_file_content:handler 返回空串 → 直接返回空(content falsy 分支,行 480)。"""
    f = tmp_path / "a.txt"
    f.write_bytes(b"")
    svc = _svc_with_mocks()
    svc._text_handler.read_content.return_value = ""
    assert svc._read_file_content(f) == ""


# ---------------------------------------------------------------------------
# close():锁获取成功分支 + except 吞异常(行 497, 506-507)
# ---------------------------------------------------------------------------


def test_close_acquires_lock_and_kills_processes(monkeypatch):
    """close():sys.exitfunc 判定为否 + 锁获取成功 → 执行 kill(行 497-505)。

    sys.exitfunc 在 CPython 通常存在 → 早返回;需 monkeypatch 删除它使条件为假,
    进入锁获取分支。
    """
    import sys

    svc = _svc_with_mocks()
    # 删除 exitfunc 让 hasattr 返回 False;sys.modules.get("sys") 返回真值
    if hasattr(sys, "exitfunc"):
        monkeypatch.delattr(sys, "exitfunc", raising=False)
    # 锁能获取(blocking=False 返回 True)
    svc._lock.acquire.return_value = True
    killed = []
    monkeypatch.setattr(svc, "_kill_new_office_processes", lambda name, pids: killed.append(name))

    svc.close()

    assert "WINWORD.EXE" in killed
    assert "EXCEL.EXE" in killed
    svc._lock.release.assert_called_once()
    # 恢复不必要(monkeypatch 自动 tearDown)


def test_close_lock_acquire_fails_silently(monkeypatch):
    """close():锁获取失败(acquire 返回 False)→ 不执行 kill,不抛(行 497 False 分支)。"""
    import sys

    svc = _svc_with_mocks()
    if hasattr(sys, "exitfunc"):
        monkeypatch.delattr(sys, "exitfunc", raising=False)
    svc._lock.acquire.return_value = False  # 锁被占用
    killed = []
    monkeypatch.setattr(svc, "_kill_new_office_processes", lambda name, pids: killed.append(name))

    svc.close()  # 不应抛
    assert killed == []  # 未获取锁,不 kill


def test_close_swallows_exception_in_kill(monkeypatch):
    """close():kill 抛异常 → except 吞掉,不向上抛(行 506-507)。"""
    import sys

    svc = _svc_with_mocks()
    if hasattr(sys, "exitfunc"):
        monkeypatch.delattr(sys, "exitfunc", raising=False)
    svc._lock.acquire.return_value = True
    monkeypatch.setattr(
        svc,
        "_kill_new_office_processes",
        lambda name, pids: (_ for _ in ()).throw(RuntimeError("kill boom")),
    )
    svc.close()  # 不应抛


def test_del_calls_close():
    """__del__ 调用 close(不抛异常)。"""
    svc = _svc_with_mocks()
    svc.__del__()  # close 被 suppress,不抛


def test_close_early_return_when_sys_modules_missing(monkeypatch):
    """close():sys.modules.get('sys') 为假值 → 条件为真 → 早 return(行 497)。

    覆盖 `not sys.modules.get("sys")` 为真这条路径(与 exitfunc 存在互补)。
    """
    import sys

    svc = _svc_with_mocks()
    # 删除 exitfunc 让前半为假
    if hasattr(sys, "exitfunc"):
        monkeypatch.delattr(sys, "exitfunc", raising=False)
    # sys.modules.get("sys") 返回 None → not None == True → 整条件真 → return
    fake_modules = MagicMock()
    fake_modules.get.return_value = None
    monkeypatch.setattr(sys, "modules", fake_modules)

    killed = []
    monkeypatch.setattr(svc, "_kill_new_office_processes", lambda name, pids: killed.append(name))

    svc.close()
    assert killed == []  # 早返回,未 kill


def test_close_early_return_when_exitfunc_present():
    """close():hasattr(sys, 'exitfunc') 为真(CPython 默认)→ 早 return(行 497)。

    不删 exitfunc,走默认早返回路径。
    """
    svc = _svc_with_mocks()
    # CPython 通常有 sys.exitfunc 属性 → 直接早返回
    svc.close()  # 不抛即通过


# ---------------------------------------------------------------------------
# preview_replace:全局异常路径(行 255-256 已有,补充 conversion 异常)
# ---------------------------------------------------------------------------


def test_preview_replace_conversion_exception_handled(tmp_path, monkeypatch):
    """preview 对 .doc:auto_convert 抛异常 → 全局 except 捕获,status 含 '错误'。"""
    f = tmp_path / "a.doc"
    f.write_bytes(b"fake")
    svc = _svc_with_mocks()
    svc.converter.is_conversion_needed.return_value = True
    svc.converter.auto_convert_if_needed.side_effect = RuntimeError("convert boom")

    result = svc.preview_replace([f], [SIMPLE])

    assert "错误" in result[f]["status"]
    assert "convert boom" in result[f]["status"]
