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
# format_file_size:精确边界 + 多次除法浮点累积(锁定正确舍入,防 off-by-one / 漂移)
# ---------------------------------------------------------------------------


def test_format_file_size_exact_1023_bytes_boundary():
    """1023 应落在 B 档(未越 1024),不被提前进位到 KB。循环条件 size < 1024.0 的边界。"""
    assert format_file_size(1023) == "1023 B"


def test_format_file_size_exact_1024_promotes_to_kb():
    """1024 恰好越界 → 进位为 1.00 KB(< 严格小于,1024 不满足则除以 1024)。"""
    assert format_file_size(1024) == "1.00 KB"


def test_format_file_size_multi_division_accumulation_5mb():
    """5 MiB 需两次 /1024,验证多次除法后浮点累积不破坏精确舍入(5.00 而非 4.99/5.01)。"""
    assert format_file_size(1024 * 1024 * 5) == "5.00 MB"


def test_format_file_size_multi_division_accumulation_1_5gb():
    """1.5 GiB 需三次 /1024,小数 .50 不因累积漂移成 .49/.51。"""
    assert format_file_size(int(1.5 * 1024**3)) == "1.50 GB"


def test_format_file_size_pb_overflow_keeps_pb_unit():
    """远超 1024 PB 仍格式化为 PB 档(循环走完所有单位后落到 return PB 分支)。"""
    out = format_file_size(1024**5 * 3)
    assert out.endswith(" PB")
    assert out.startswith("3.0")


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
# format_datetime:tz 后缀精确文本(锁定 offset_str 拼接与 Z 解析为 +00:00)
# ---------------------------------------------------------------------------


def test_format_datetime_aware_utc_exact_bracket():
    """带 tz 的 UTC datetime → 后缀精确为 [UTC+0000](%z 输出无冒号 +0000)。"""
    dt = datetime(2026, 5, 19, 10, 0, 0, tzinfo=UTC)
    assert format_datetime(dt) == "2026-05-19 10:00:00 [UTC+0000]"


def test_format_datetime_aware_offset_exact_bracket():
    """带非零 offset(+08:00)→ 后缀 [UTC+0800]。"""
    from datetime import timedelta, timezone

    dt = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    assert format_datetime(dt) == "2026-05-19 10:00:00 [UTC+0800]"


def test_format_datetime_z_suffix_parsed_as_utc():
    """ISO 串带 'Z' → 解析为 +00:00,后缀 [UTC+0000](证明 Z 被解析,而非走 fallback)。"""
    assert format_datetime("2026-05-19T10:00:00Z") == "2026-05-19 10:00:00 [UTC+0000]"


def test_format_datetime_invalid_string_has_no_bracket():
    """非法字符串 fallback 返回原串,且**无** [UTC] 括号(区分「解析成功」与「原样返回」)。"""
    out = format_datetime("not a date")
    assert out == "not a date"
    assert "[" not in out


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


# ---------------------------------------------------------------------------
# expand_files:空输入 / 空目录 / 完整顺序(显式全部先于目录文件)
# ---------------------------------------------------------------------------


def test_expand_files_all_empty_returns_empty(tmp_path):
    """files=[] + directory=None → [](边界)。"""
    assert expand_files([], None, False) == []


def test_expand_files_empty_directory_returns_explicit_only(tmp_path):
    """目录存在但无文件 → 仅返回显式 files。"""
    d = tmp_path / "empty"
    d.mkdir()
    explicit = tmp_path / "e.txt"
    explicit.write_text("x")
    assert expand_files([explicit], d, False) == [explicit]


def test_expand_files_explicit_all_precede_directory_files(tmp_path):
    """多个显式 files 全部排在目录文件之前(锁定「先 files 后 directory」顺序)。"""
    e1 = tmp_path / "e1.txt"
    e2 = tmp_path / "e2.txt"
    e1.write_text("1")
    e2.write_text("2")
    d = tmp_path / "d"
    d.mkdir()
    (d / "d1.txt").write_text("d")
    (d / "d2.txt").write_text("d")
    result = expand_files([e1, e2], d, False)
    names = [p.name for p in result]
    assert names[:2] == ["e1.txt", "e2.txt"]
    assert set(names[2:]) == {"d1.txt", "d2.txt"}
