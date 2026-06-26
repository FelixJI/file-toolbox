import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_invoice_tab_instantiates(app):
    tab = InvoiceTab()
    assert tab is not None


def test_invoice_tab_has_table(app):
    tab = InvoiceTab()
    assert hasattr(tab, "_table")
    assert tab._table.columnCount() > 0
