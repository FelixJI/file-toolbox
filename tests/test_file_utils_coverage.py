"""common/file_utils 未覆盖分支补充测试。

覆盖行:
- 18: format_file_size PB(超大)
- 26-31: format_datetime str 分支(iso 成功带/不带 tz、解析失败)
- 32-33: format_datetime datetime 无 tz
- 52-53: get_file_info 非 Path 输入
- 64-65: get_file_info stat 异常
"""

from datetime import UTC, datetime

from file_toolbox.common.file_utils import format_datetime, format_file_size, get_file_info

# ---------------------------------------------------------------------------
# format_file_size:PB(行 18)
# ---------------------------------------------------------------------------


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
