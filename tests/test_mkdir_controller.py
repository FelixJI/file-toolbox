"""MkdirController 测试:纯 Python,无 Qt 依赖。

验证结构收集、非法字符校验与原 mkdir_tab 内联逻辑一致。
build_history_record 已下沉 FolderCreatorService.create_folders(见
test_mkdir_service_history.py),本控制器不再含该方法。
"""

from file_toolbox.core.batch_mkdir import FolderCreatorService
from file_toolbox.gui.controllers.mkdir_controller import MkdirController


def _controller():
    return MkdirController(FolderCreatorService())


# ---------- collect_structures ----------


def test_collect_structures_tab_aware():
    """多级行:每行非空 strip 后组成一个元组。"""
    rows = [
        ["项目A", "文档", "草稿"],
        ["项目B", "图片"],
    ]
    result = _controller().collect_structures(rows)
    assert result == [
        ("项目A", "文档", "草稿"),
        ("项目B", "图片"),
    ]


def test_collect_structures_single_level():
    rows = [["项目A"], ["项目B"]]
    result = _controller().collect_structures(rows)
    assert result == [("项目A",), ("项目B",)]


def test_collect_structures_skips_empty_rows():
    """整行无非空单元格(空串或纯空白)则跳过该行。"""
    rows = [
        ["项目A"],
        ["", "  "],
        ["项目B"],
    ]
    result = _controller().collect_structures(rows)
    assert result == [("项目A",), ("项目B",)]


def test_collect_structures_strips_cells():
    """单元格前后空白被 strip。"""
    rows = [["  项目A  ", " 文档 "]]
    result = _controller().collect_structures(rows)
    assert result == [("项目A", "文档")]


# ---------- find_invalid_names ----------


def test_find_invalid_names():
    """validate_folder_name 拒绝 \\ / : * ? " < > |(Windows 非法字符)。"""
    structures = [("in/valid", "va:lid?name", "good")]
    result = _controller().find_invalid_names(structures)
    # "in/valid" 含 /, "va:lid?name" 含 : 和 ?,"good" 合法
    assert "in/valid" in result
    assert "va:lid?name" in result
    assert "good" not in result


def test_find_invalid_names_all_invalid_chars():
    """逐一验证每个非法字符都被拒绝。"""
    invalid_chars = '\\/:*?"<>|'
    controller = _controller()
    for ch in invalid_chars:
        assert controller._svc.validate_folder_name(f"a{ch}b") is False


def test_find_invalid_names_dedup():
    """重复的非法名只出现一次,顺序保持。"""
    structures = [
        ("a*b", "c"),
        ("a*b", "d?e"),
        ("d?e",),
    ]
    result = _controller().find_invalid_names(structures)
    assert result == ["a*b", "d?e"]


def test_find_invalid_names_empty():
    assert _controller().find_invalid_names([]) == []
    assert _controller().find_invalid_names([("good", "ok")]) == []
