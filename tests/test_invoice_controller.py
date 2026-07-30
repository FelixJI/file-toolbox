"""InvoiceController 测试:纯 Python,不 import PySide6。

行为对齐 InvoiceTab 原 _dedupe_strategy / _format / _parse 状态串。
build_history_record 已下沉 InvoiceService.export(见 test_invoice_service_history.py),
本控制器不再含该方法。
"""

from file_toolbox.core.invoice.dedupe import DEDUPE, KEEP_ALL, MARK
from file_toolbox.gui.controllers.invoice_controller import InvoiceController


def test_dedupe_strategy_from_index():
    """下拉框索引 0/1/2 → KEEP_ALL/DEDUPE/MARK 的实际字符串值。"""
    c = InvoiceController()
    assert c.dedupe_strategy(0) == KEEP_ALL == "keep_all"
    assert c.dedupe_strategy(1) == DEDUPE == "dedupe"
    assert c.dedupe_strategy(2) == MARK == "mark"


def test_dedupe_strategy_out_of_range_raises():
    """索引越界(含负数)应抛 IndexError。

    回归:旧实现 `self._DEDUPE_BY_INDEX[index]` 对负数走 Python 负索引,
    dedupe_strategy(-1) 静默返回 'mark'、(-2) 返回 'dedupe',与 docstring
    「越界抛 IndexError」承诺相悖(真实下拉框不会给负数,但契约应被锁定)。
    """
    import pytest

    c = InvoiceController()
    with pytest.raises(IndexError):
        c.dedupe_strategy(3)
    with pytest.raises(IndexError):
        c.dedupe_strategy(-1)  # 负数不应静默返回末位策略


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
