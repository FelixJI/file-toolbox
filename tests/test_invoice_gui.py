"""发票识别 Tab GUI 测试:表格结构、格式/去重策略映射等纯 UI 逻辑。

不触发真实文件解析或网络,仅校验控件状态与映射逻辑。
UI 由 generated/ui_invoice_dialog.py(Ui_InvoiceDialog)构建,本测试验证接入正确。
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from file_toolbox.core.invoice.dedupe import DEDUPE, KEEP_ALL, MARK  # noqa: E402
from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab  # noqa: E402
from file_toolbox.gui.generated.ui_invoice_dialog import HEADERS  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(app):
    return InvoiceTab()


def test_invoice_tab_has_expected_table_headers(tab):
    """表格应预置 8 列业务表头,列数与表头一致。"""
    assert tab.ui.table.columnCount() == len(HEADERS)
    headers = [
        tab.ui.table.horizontalHeaderItem(i).text() for i in range(tab.ui.table.columnCount())
    ]
    assert headers == HEADERS


def test_invoice_tab_starts_empty(tab):
    """新建 Tab 表格应无数据行。"""
    assert tab.ui.table.rowCount() == 0


def test_format_defaults_to_excel(tab):
    """默认选中 Excel,且切换单选后 _format() 反映新选择。"""
    assert tab._format() == "excel"
    tab.ui.rb_json.setChecked(True)
    assert tab._format() == "json"
    tab.ui.rb_both.setChecked(True)
    assert tab._format() == "both"


def test_dedupe_strategy_maps_combo_index(tab):
    """去重策略下拉框索引应映射到 KEEP_ALL/DEDUPE/MARK。"""
    for idx, expected in enumerate([KEEP_ALL, DEDUPE, MARK]):
        tab.ui.cmb_dedupe.setCurrentIndex(idx)
        assert tab._dedupe_strategy() == expected


def test_format_radio_group_is_mutually_exclusive(tab):
    """三个格式单选按钮应互斥:选中 JSON 会取消 Excel。"""
    tab.ui.rb_excel.setChecked(True)
    tab.ui.rb_json.setChecked(True)
    assert tab.ui.rb_json.isChecked()
    assert tab.ui.rb_excel.isChecked() is False
