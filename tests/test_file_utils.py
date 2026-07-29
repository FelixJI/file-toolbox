from datetime import UTC, datetime

from file_toolbox.common.file_utils import (
    expand_files,
    format_datetime,
    format_file_size,
    get_file_info,
)


def test_format_file_size_bytes():
    assert format_file_size(512) == "512 B"


def test_format_file_size_kb():
    assert format_file_size(2048) == "2.00 KB"


def test_format_file_size_negative():
    assert format_file_size(-1) == "未知"


def test_format_datetime_now_has_tz():
    s = format_datetime()
    assert "UTC" in s


def test_get_file_info_missing(tmp_path):
    info = get_file_info(tmp_path / "nope.txt")
    assert info["exists"] is False


def test_get_file_info_existing(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    info = get_file_info(f)
    assert info["exists"] is True
    assert info["size"] == 5
    assert info["suffix"] == ".txt"


def test_paths_create_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 重新导入以拿到 cwd 下的路径
    import importlib

    from file_toolbox.common import paths

    importlib.reload(paths)
    b = paths.get_backup_dir()
    h = paths.get_history_dir()
    assert b.exists() and h.exists()
    assert ".file_toolbox" in str(b)


def test_format_file_size_pb():
    """超过 TB → PB(行 18)。"""
    # 1024^5 = PB 范围
    assert format_file_size(1024**5) == "1.0 PB"


def test_format_file_size_mb_gb_tb():
    assert format_file_size(1024**2) == "1.00 MB"
    assert format_file_size(1024**3) == "1.00 GB"
    assert format_file_size(1024**4) == "1.00 TB"


def test_format_file_size_zero():
    assert format_file_size(0) == "0 B"


# ---------------------------------------------------------------------------
# format_datetime:str 分支(行 26-31)
# ---------------------------------------------------------------------------


def test_format_datetime_iso_string_with_tz():
    """ISO 字符串带 Z → 解析为带 tz(行 27)。"""
    s = format_datetime("2026-05-19T10:00:00Z")
    assert "2026-05-19 10:00:00" in s
    assert "UTC" in s


def test_format_datetime_iso_string_naive_adds_local_tz():
    """ISO 字符串无 tz → 加本地 tz(行 28-29)。"""
    s = format_datetime("2026-05-19T10:00:00")
    assert "2026-05-19 10:00:00" in s
    assert "UTC" in s


def test_format_datetime_invalid_string_returns_raw():
    """非法字符串 → 返回原串(行 30-31)。"""
    assert format_datetime("not a date") == "not a date"


def test_format_datetime_datetime_naive_adds_tz():
    """datetime 无 tz → astimezone 加本地 tz(行 32-33)。"""
    dt = datetime(2026, 5, 19, 10, 0, 0)
    s = format_datetime(dt)
    assert "2026-05-19 10:00:00" in s
    assert "UTC" in s


def test_format_datetime_datetime_with_tz_preserved():
    """datetime 带 tz → 保留(行 32 分支不进入)。"""
    dt = datetime(2026, 5, 19, 10, 0, 0, tzinfo=UTC)
    s = format_datetime(dt)
    assert "2026-05-19 10:00:00" in s


def test_format_datetime_custom_format():
    """自定义 fmt。"""
    s = format_datetime("2026-05-19T10:00:00", fmt="%Y/%m/%d")
    assert "2026/05/19" in s


# ---------------------------------------------------------------------------
# get_file_info:非 Path / stat 异常(行 52-53, 64-65)
# ---------------------------------------------------------------------------


def test_get_file_info_accepts_string_path(tmp_path):
    """传 str 而非 Path → 内部转换(行 52-53)。"""
    f = tmp_path / "a.txt"
    f.write_text("hello")
    info = get_file_info(str(f))
    assert info["exists"] is True
    assert info["size"] == 5


def test_get_file_info_stat_exception_recorded(tmp_path, monkeypatch):
    """stat 抛异常 → except 记 error(行 64-65)。"""
    from pathlib import Path

    f = tmp_path / "a.txt"
    f.write_text("x")
    monkeypatch.setattr(
        Path, "stat", lambda self, **kw: (_ for _ in ()).throw(PermissionError("boom"))
    )
    info = get_file_info(f)
    assert "error" in info
    assert "boom" in info["error"]


def test_get_file_info_directory_not_file(tmp_path):
    """目录 → is_file=False,size 保持 0。"""
    info = get_file_info(tmp_path)
    assert info["exists"] is True
    assert info["is_file"] is False
    assert info["size"] == 0


def test_get_file_info_suffix(tmp_path):
    """后缀提取。"""
    f = tmp_path / "archive.PDF"
    f.write_text("x")
    info = get_file_info(f)
    assert info["suffix"] == ".pdf"  # lower


# ---------------------------------------------------------------------------
# expand_files:显式 files + directory / 递归 / 去重保序
# ---------------------------------------------------------------------------


def test_expand_files_merges_files_and_directory_non_recursive(tmp_path):
    """显式 files + directory(非递归):合并两者,只取目录直接子文件。"""
    explicit = tmp_path / "explicit.txt"
    explicit.write_text("x")
    d = tmp_path / "d"
    d.mkdir()
    (d / "in_dir.txt").write_text("y")
    sub = d / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("z")  # 非递归不进子目录

    result = expand_files([explicit], d, recursive=False)
    names = [p.name for p in result]
    assert names[0] == "explicit.txt"  # files 在前
    assert "in_dir.txt" in names
    assert "nested.txt" not in names  # 非递归


def test_expand_files_recursive_descends(tmp_path):
    """recursive=True:递归纳入所有子文件。"""
    d = tmp_path / "d"
    d.mkdir()
    (d / "a.txt").write_text("a")
    sub = d / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("b")

    result = expand_files([], d, recursive=True)
    names = [p.name for p in result]
    assert "a.txt" in names
    assert "b.txt" in names


def test_expand_files_dedup_keeps_first_occurrence_order(tmp_path):
    """重复(resolve 后相同)→ 仅保留首次出现,保持原顺序。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    f2 = tmp_path / "b.txt"
    f2.write_text("y")
    # f1 重复出现:一次绝对、一次相对(均 resolve 到同一路径)
    result = expand_files([f1, f2, f1.resolve()], None, False)
    assert result == [f1, f2]  # 第三项被去重,顺序不变


def test_expand_files_no_directory_returns_explicit_only(tmp_path):
    """directory=None → 仅返回 files(去重后)。"""
    f1 = tmp_path / "a.txt"
    result = expand_files([f1], None, False)
    assert result == [f1]
