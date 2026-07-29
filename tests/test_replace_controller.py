"""ReplaceController 测试:纯 Python(不 import PySide6)。

校验 format_op_label / format_history_line 与原 replace_tab._refresh_op_list、
_show_history 内联逻辑等价。本控制器不含 build_history_record(已下沉
ContentReplaceService)。
"""

from file_toolbox.gui.controllers.replace_controller import ReplaceController


def _c() -> ReplaceController:
    return ReplaceController()


# ---------- format_op_label ----------


def test_format_op_label_simple_replace():
    """simple_replace:'替换: <find> -> <replace>'。"""
    op = {"type": "simple_replace", "params": {"find": "旧", "replace": "新"}}
    assert _c().format_op_label(op) == "替换: '旧' -> '新'"


def test_format_op_label_regex_replace():
    """regex_replace:'正则: /<pattern>/ -> <replace>'。"""
    op = {"type": "regex_replace", "params": {"pattern": r"\d+", "replace": "X"}}
    assert _c().format_op_label(op) == r"正则: /\d+/ -> 'X'"


def test_format_op_label_missing_params_defaults_empty():
    """缺失 params 键不报错,回退空串。"""
    assert _c().format_op_label({"type": "simple_replace", "params": {}}) == "替换: '' -> ''"


# ---------- format_history_line ----------


def test_format_history_line_shape():
    """与原 replace_tab._show_history 内联一致:'#<id> <ts[:19]>  <files[:1]>'。"""
    record = {
        "id": 5,
        "timestamp": "2026-07-29T09:00:00.000",
        "data": {"files": ["/tmp/a.docx", "/tmp/b.docx"]},
    }
    assert _c().format_history_line(record) == "#5 2026-07-29T09:00:00  ['/tmp/a.docx']"


def test_format_history_line_empty_files():
    record = {"id": 1, "timestamp": "t", "data": {"files": []}}
    assert _c().format_history_line(record) == "#1 t  []"
