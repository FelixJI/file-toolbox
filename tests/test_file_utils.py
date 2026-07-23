
from file_toolbox.common.file_utils import format_datetime, format_file_size, get_file_info


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
