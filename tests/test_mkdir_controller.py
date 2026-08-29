"""MkdirController 测试:纯 Python,无 Qt 依赖。

验证结构收集、非法字符校验、TSV 粘贴解析与原 mkdir_tab 内联逻辑一致。
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


def test_collect_structures_empty_rows_returns_empty():
    """rows=[] → 空结构(边界)。"""
    assert _controller().collect_structures([]) == []


def test_collect_structures_all_empty_cells_row_skipped():
    """整行全空单元格 → 该行被跳过(不产生空 tuple)。"""
    rows = [["  ", ""], ["a", "b"]]
    assert _controller().collect_structures(rows) == [("a", "b")]


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


# ---------- parse_tsv_grid(粘贴输入解析) ----------


def test_parse_tsv_grid_basic():
    """Excel 选区复制:Tab 分列、换行分行。"""
    assert _controller().parse_tsv_grid("项目A\t文档\n项目B") == [
        ["项目A", "文档"],
        ["项目B"],
    ]


def test_parse_tsv_grid_normalizes_line_endings():
    """CRLF / CR 均归一为 \\n 分行。"""
    assert _controller().parse_tsv_grid("a\tb\r\nc") == [["a", "b"], ["c"]]
    assert _controller().parse_tsv_grid("a\rb") == [["a"], ["b"]]


def test_parse_tsv_grid_strips_trailing_blank_lines():
    """复制操作通常带尾随换行;末尾空行不是结构的一部分。"""
    assert _controller().parse_tsv_grid("a\tb\n") == [["a", "b"]]
    assert _controller().parse_tsv_grid("a\n\n\n") == [["a"]]


def test_parse_tsv_grid_keeps_interior_blank_lines():
    """中间空行保留(锯齿网格由调用方逐行填充;空行在结构收集中被跳过)。"""
    assert _controller().parse_tsv_grid("a\n\nb") == [["a"], [""], ["b"]]


def test_parse_tsv_grid_empty_text():
    assert _controller().parse_tsv_grid("") == []
    assert _controller().parse_tsv_grid("\n\n") == []


def test_parse_tsv_grid_single_cell():
    """无 Tab 无换行:单格文本 → 1x1 网格。"""
    assert _controller().parse_tsv_grid("项目A") == [["项目A"]]


# ---------- level_header(扩列时的列头) ----------


def test_level_header_matches_ui_columns():
    """1-3 级与 .ui 中既有列头一致,保证扩列后风格统一。"""
    controller = _controller()
    assert controller.level_header(1) == "一级文件夹"
    assert controller.level_header(2) == "二级文件夹"
    assert controller.level_header(3) == "三级文件夹"


def test_level_header_beyond_ten_uses_digits():
    """超过十级退回阿拉伯数字,不硬造"十一"等组合。"""
    assert _controller().level_header(11) == "11级文件夹"
