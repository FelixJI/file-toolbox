"""InvoiceController 测试:纯 Python,不 import PySide6。

行为对齐 InvoiceTab 原 _dedupe_strategy / _format / _parse 状态串 / _export 历史 dict。
"""

from file_toolbox.core.invoice.dedupe import DEDUPE, KEEP_ALL, MARK
from file_toolbox.gui.controllers.invoice_controller import InvoiceController


def test_dedupe_strategy_from_index():
    """下拉框索引 0/1/2 → KEEP_ALL/DEDUPE/MARK 的实际字符串值。"""
    c = InvoiceController()
    assert c.dedupe_strategy(0) == KEEP_ALL == "keep_all"
    assert c.dedupe_strategy(1) == DEDUPE == "dedupe"
    assert c.dedupe_strategy(2) == MARK == "mark"


def test_format_from_radios():
    """单选按钮状态映射:json 优先于 both,均未选时默认 excel。"""
    c = InvoiceController()
    assert c.format(json_checked=False, both_checked=False) == "excel"
    assert c.format(json_checked=True, both_checked=False) == "json"
    assert c.format(json_checked=False, both_checked=True) == "both"
    # json 优先(与原 _format if 顺序一致)
    assert c.format(json_checked=True, both_checked=True) == "json"


def test_format_status():
    """状态串应含各计数值及原措辞分隔符。"""
    c = InvoiceController()
    status = c.format_status(invoice_count=12, duplicate_marked=3, dedupe_removed=2, failed=1)
    assert status == "成功 12 | 重复标记 3 | 去重移除 2 | 失败 1"
    # 关键数字逐一可见
    for n in ("12", "3", "2", "1"):
        assert n in status


def test_build_history_record():
    """历史 dict 键齐全,outputs 转 str 列表(Path 也应被 str 化)。"""
    from pathlib import Path

    c = InvoiceController()
    record = c.build_history_record(
        file_count=5,
        invoice_count=12,
        dedupe_strategy=MARK,
        fmt="excel",
        outputs=[Path("/tmp/发票结果.xlsx"), Path("/tmp/发票结果.json")],
    )
    assert set(record.keys()) == {
        "file_count",
        "invoice_count",
        "dedupe_strategy",
        "fmt",
        "outputs",
    }
    assert record["file_count"] == 5
    assert record["invoice_count"] == 12
    assert record["dedupe_strategy"] == MARK
    assert record["fmt"] == "excel"
    # outputs 全为 str(原行为:[str(w) for w in written])
    assert record["outputs"] == [
        str(Path("/tmp/发票结果.xlsx")),
        str(Path("/tmp/发票结果.json")),
    ]
    assert all(isinstance(w, str) for w in record["outputs"])
