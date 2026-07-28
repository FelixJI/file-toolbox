"""batch_rename 未覆盖分支补充测试。

覆盖行:
- 271-272: _add_date source=file,文件存在但 stat() 抛异常 → except 用 now()
- 299-300: _delete_chars suffix value 非数字 → except 返回原名
- 337: execute_rename PermissionError → 记入 errors
"""

from pathlib import Path

from file_toolbox.core.batch_rename import FileRenameService


def _svc() -> FileRenameService:
    return FileRenameService()


# ---------------------------------------------------------------------------
# _add_date:source=file 文件存在但 stat 抛异常(行 271-272)
# ---------------------------------------------------------------------------


def test_add_date_file_source_stat_exception_falls_back_to_now(tmp_path, monkeypatch):
    """文件存在但 stat() 抛异常 → except → 用 datetime.now()(行 271-272)。"""
    f = tmp_path / "x.txt"
    f.write_text("y")
    monkeypatch.setattr(Path, "stat", lambda self: (_ for _ in ()).throw(PermissionError("stat boom")))
    out = _svc()._add_date("f", {"format": "%Y", "source": "file"}, f)
    # 走 except,用 now() 的年份(4 位数字)
    assert out.startswith("f")
    assert out[1:].isdigit()


# ---------------------------------------------------------------------------
# _delete_chars:suffix value 非数字(行 299-300)
# ---------------------------------------------------------------------------


def test_delete_chars_suffix_non_numeric_returns_name():
    """suffix value 非数字 → ValueError → 返回原名(行 299-300)。"""
    svc = _svc()
    assert svc._delete_chars("abcdef", {"delete_type": "suffix", "value": "abc"}) == "abcdef"


def test_delete_chars_prefix_non_numeric_returns_name():
    """prefix value 非数字 → ValueError → 返回原名(行 291-292 已覆盖,补确认)。"""
    svc = _svc()
    assert svc._delete_chars("abcdef", {"delete_type": "prefix", "value": "xyz"}) == "abcdef"


# ---------------------------------------------------------------------------
# execute_rename:PermissionError(行 337)
# ---------------------------------------------------------------------------


def test_execute_rename_permission_error_recorded(tmp_path, monkeypatch):
    """rename 抛 PermissionError → 记入 errors '权限不足'(行 336-337)。"""
    src = tmp_path / "a.txt"
    src.write_text("x")
    dst = tmp_path / "b.txt"
    monkeypatch.setattr(Path, "rename", lambda self, other: (_ for _ in ()).throw(PermissionError("denied")))
    success, errors = _svc().execute_rename({src: dst})
    assert success == 0
    assert any("权限不足" in e for e in errors)
