"""RenameController 测试:纯 Python(不 import PySide6)。

校验 OP_LABELS / op_label / format_history_line 与
原 rename_tab._OP_LABELS、_refresh_operation_list、_show_history 内联逻辑等价。
本控制器不含 build_history_record(已下沉 FileRenameService)。
"""

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


def test_format_history_line_missing_id_defaults_question():
    """缺 id 键 → '#?' 占位(锁定默认值,防回归改空串)。"""
    line = _c().format_history_line({"timestamp": "t"})
    assert line == "#? t  0 个文件"


def test_format_history_line_data_none_does_not_crash():
    """data 显式为 None(worker 写入 null)→ 不应 AttributeError 崩溃,计 0 个文件。

    回归:旧实现 record.get('data', {}) 仅在**缺键**时回退 {},data=None 时返回 None,
    随后 None.get('rename_map') 抛 AttributeError。
    """
    line = _c().format_history_line({"id": 1, "timestamp": "t", "data": None})
    assert line == "#1 t  0 个文件"
