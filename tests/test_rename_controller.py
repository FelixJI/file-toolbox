"""RenameController 测试:纯 Python(不 import PySide6)。

校验 OP_LABELS / op_label / summarize_rename / format_history_line 与
原 rename_tab._OP_LABELS、_refresh_operation_list、_show_history 内联逻辑等价。
本控制器不含 build_history_record(已下沉 FileRenameService)。
"""

from pathlib import Path

from file_toolbox.core.batch_rename import OperationType
from file_toolbox.gui.controllers.rename_controller import RenameController


def _c() -> RenameController:
    return RenameController()


# ---------- op_label / OP_LABELS ----------


def test_op_labels_covers_all_operation_types():
    """OP_LABELS 覆盖全部 7 种 OperationType(与原 rename_tab._OP_LABELS 一致)。"""
    labels = RenameController.OP_LABELS
    for ot in OperationType:
        assert ot.value in labels
    assert len(labels) == len(list(OperationType))


def test_op_label_known_type():
    assert _c().op_label(OperationType.ADD_PREFIX.value) == "添加前缀"
    assert _c().op_label("regex_replace") == "正则替换"


def test_op_label_unknown_type_falls_back():
    """未知 type 回退为该 type 字符串本身。"""
    assert _c().op_label("bogus") == "bogus"


def test_op_label_non_str_coerced():
    """非 str 入参被 str() 化后查表(未知则回退其字符串)。"""
    assert _c().op_label(None) == "None"


# ---------- summarize_rename ----------


def test_summarize_rename_counts_ready():
    """就绪 = 状态含 '准备'(与 rename_tab._execute 的 ready 过滤一致)。"""
    result = {
        Path("a.txt"): (Path("a_new.txt"), "✓ 准备就绪"),
        Path("b.txt"): (Path("b.txt"), "⚠️ 文件名冲突"),
        Path("c.txt"): (Path("c_new.txt"), "✓ 准备就绪"),
    }
    count, text = _c().summarize_rename(result)
    assert count == 2
    assert "2" in text


def test_summarize_rename_none_ready():
    result = {Path("a.txt"): (Path("a.txt"), "⚠️ 文件名冲突")}
    count, _ = _c().summarize_rename(result)
    assert count == 0


# ---------- format_history_line ----------


def test_format_history_line_shape():
    """与原 rename_tab._show_history 内联格式一致:'#<id> <ts[:19]>  <n> 个文件'。"""
    record = {
        "id": 7,
        "timestamp": "2026-07-29T12:34:56.789",
        "data": {"rename_map": {"a": "b", "c": "d"}},
    }
    line = _c().format_history_line(record)
    assert line == "#7 2026-07-29T12:34:56  2 个文件"


def test_format_history_line_empty_map():
    record = {"id": 1, "timestamp": "t", "data": {"rename_map": {}}}
    assert _c().format_history_line(record) == "#1 t  0 个文件"
