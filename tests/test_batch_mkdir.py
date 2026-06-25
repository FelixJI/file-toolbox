from pathlib import Path

from file_toolbox.core.batch_mkdir import (
    ConflictStrategy,
    FolderCreatorService,
)


def _svc():
    return FolderCreatorService()


def test_parse_valid_table():
    text = "部门A\t项目1\n部门A\t项目2"
    r = _svc().parse_excel_table_data(text)
    assert r.valid
    assert ("部门A", "项目1") in r.folder_structure
    assert ("部门A", "项目2") in r.folder_structure


def test_parse_empty_text():
    r = _svc().parse_excel_table_data("   ")
    assert r.valid is False


def test_parse_no_tab():
    r = _svc().parse_excel_table_data("noseparator")
    assert r.valid is False
    assert "Tab" in r.error_message


def test_parse_detects_invalid_chars():
    text = "a*b\tc"
    r = _svc().parse_excel_table_data(text)
    assert len(r.invalid_folders) > 0


def test_parse_inherits_empty_cell_from_prev_row():
    text = "部门A\t项目1\n\t项目2"
    r = _svc().parse_excel_table_data(text)
    assert ("部门A", "项目2") in r.folder_structure


def test_build_folder_paths(tmp_path):
    svc = _svc()
    items = svc.build_folder_paths(tmp_path, [("a", "b"), ("a", "c")])
    assert len(items) == 2
    assert items[0].path == tmp_path / "a" / "b"
    assert items[0].exists is False


def test_create_folders_merge(tmp_path):
    svc = _svc()
    items = svc.build_folder_paths(tmp_path, [("x", "y")])
    result = svc.create_folders(items, ConflictStrategy.MERGE)
    assert result.success
    assert result.created_count == 1
    assert (tmp_path / "x" / "y").is_dir()


def test_create_folders_skip_existing(tmp_path):
    svc = _svc()
    items = svc.build_folder_paths(tmp_path, [("x")])
    result = svc.create_folders(items, ConflictStrategy.SKIP)
    assert result.created_count == 1
    # 第二次,已存在
    items2 = svc.build_folder_paths(tmp_path, [("x")])
    result2 = svc.create_folders(items2, ConflictStrategy.SKIP)
    assert result2.skipped_count == 1
    assert result2.created_count == 0


def test_replace_special_chars():
    assert _svc().replace_special_chars("a*b:c") == "a_b_c"


def test_remove_special_chars():
    assert _svc().remove_special_chars("a*b:c") == "abc"


def test_validate_folder_name():
    svc = _svc()
    assert svc.validate_folder_name("good") is True
    assert svc.validate_folder_name("ba*d") is False
    assert svc.validate_folder_name("") is False
