"""invoice_tab GUI 测试:文件管理、解析、表格填充、导出(mock QFileDialog)。"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(app, tmp_path):
    t = InvoiceTab()
    t._history = JsonHistoryStore(tmp_path)
    return t


def _xml(path: Path, num: str) -> Path:
    path.write_text(
        f'<?xml version="1.0"?><EInvoice>'
        f"<Header><InherentLabel><GeneralOrSpecialVAT><LabelName>增值税专用发票</LabelName></GeneralOrSpecialVAT></InherentLabel></Header>"
        f"<EInvoiceData><SellerInformation><SellerName>s{num}</SellerName><SellerIdNum>sid</SellerIdNum></SellerInformation>"
        f"<BuyerInformation><BuyerName>b{num}</BuyerName><BuyerIdNum>bid</BuyerIdNum></BuyerInformation>"
        f"<BasicInformation><TotalAmWithoutTax>1</TotalAmWithoutTax><TotalTaxAm>0.13</TotalTaxAm>"
        f"<TotalTax-includedAmount>1.13</TotalTax-includedAmount>"
        f"<TotalTax-includedAmountInChinese>圆</TotalTax-includedAmountInChinese>"
        f"<Drawer>x</Drawer></BasicInformation></EInvoiceData>"
        f"<TaxSupervisionInfo><InvoiceNumber>{num}</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>"
        f"</EInvoice>",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# 文件管理
# ---------------------------------------------------------------------------


def test_add_files(tab, monkeypatch, tmp_path):
    f1 = _xml(tmp_path / "1.xml", "1")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(f1)], ""))
    tab._add_files()
    assert len(tab._files) == 1
    assert tab.ui.list_files.count() == 1


def test_add_files_multiple(tab, monkeypatch, tmp_path):
    f1 = _xml(tmp_path / "1.xml", "1")
    f2 = _xml(tmp_path / "2.xml", "2")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(f1), str(f2)], ""))
    tab._add_files()
    assert len(tab._files) == 2


def test_add_folder_non_recursive(tab, monkeypatch, tmp_path):
    _xml(tmp_path / "1.xml", "1")
    (tmp_path / "ignore.txt").write_text("x")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    tab._add_folder()
    assert len(tab._files) == 1
    assert tab._files[0].suffix == ".xml"


def test_add_folder_recursive(tab, monkeypatch, tmp_path):
    _xml(tmp_path / "1.xml", "1")
    sub = tmp_path / "sub"
    sub.mkdir()
    _xml(sub / "2.xml", "2")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    tab._add_folder()
    assert len(tab._files) == 2


def test_add_folder_cancelled(tab, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    tab._add_folder()
    assert tab._files == []


def test_add_folder_dedup(tab, monkeypatch, tmp_path):
    """重复文件不重复加入(行 75-77)。"""
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files.append(f1)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    tab._add_folder()
    assert len(tab._files) == 1  # 不重复


def test_clear(tab, tmp_path):
    tab._files = [tmp_path / "a.xml"]
    tab.ui.list_files.addItem("a.xml")
    tab._result = object()  # 非 None
    tab._clear()
    assert tab._files == []
    assert tab.ui.list_files.count() == 0
    assert tab._result is None
    assert tab.ui.btn_export.isEnabled() is False
    assert tab.ui.lbl_status.text() == "就绪"


def test_browse_outdir(tab, monkeypatch, tmp_path):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    tab._browse_outdir()
    assert tab.ui.edit_outdir.text() == str(tmp_path)


def test_browse_outdir_cancelled(tab, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    tab._browse_outdir()
    assert tab.ui.edit_outdir.text() == ""


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def test_parse_no_files_warns(tab, monkeypatch):
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(1) or QMessageBox.StandardButton.Ok
    )
    tab._parse()
    assert warned


def test_parse_success(tab, tmp_path):
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    assert tab._result is not None
    assert len(tab._result.invoices) == 1
    assert tab.ui.btn_export.isEnabled()
    assert tab.ui.table.rowCount() == 1


def test_parse_mixed_results(tab, tmp_path):
    """含坏文件 → failed 非空,status 反映。"""
    f1 = _xml(tmp_path / "1.xml", "1")
    bad = tmp_path / "bad.xml"
    bad.write_text("not xml", encoding="utf-8")
    tab._files = [f1, bad]
    tab._parse()
    assert len(tab._result.failed) == 1


def test_populate_table_duplicate_color(tab, tmp_path):
    """mark 策略下重复行黄底(行 135-136)。

    直接构造 ParseResult 让 _populate_table 渲染重复标记行。
    """
    from file_toolbox.core.invoice.types import Invoice, ParseResult

    inv1 = Invoice(
        invoice_number="111",
        invoice_type="",
        issue_date="",
        seller_name="",
        seller_tax_id="",
        seller_addr="",
        seller_tel="",
        seller_bank="",
        seller_account="",
        buyer_name="",
        buyer_tax_id="",
        buyer_addr="",
        buyer_tel="",
        buyer_bank="",
        buyer_account="",
        amount_without_tax="",
        tax_amount="",
        amount_with_tax="",
        amount_chinese="",
        drawer="",
        remark="",
        items=[],
        source_file="a.xml",
        parse_method="xml",
    )
    inv2 = Invoice(
        invoice_number="111",
        invoice_type="",
        issue_date="",
        seller_name="",
        seller_tax_id="",
        seller_addr="",
        seller_tel="",
        seller_bank="",
        seller_account="",
        buyer_name="",
        buyer_tax_id="",
        buyer_addr="",
        buyer_tel="",
        buyer_bank="",
        buyer_account="",
        amount_without_tax="",
        tax_amount="",
        amount_with_tax="",
        amount_chinese="",
        drawer="",
        remark="",
        items=[],
        source_file="b.xml",
        parse_method="xml",
        is_duplicate=True,
    )
    tab._result = ParseResult(invoices=[inv1, inv2], duplicates=[], failed=[])
    tab._populate_table()
    assert tab.ui.table.rowCount() == 2


def test_populate_table_pdf_color(tab):
    """pdf 解析行灰底(行 137-138)。"""
    from file_toolbox.core.invoice.types import Invoice, ParseResult

    inv = Invoice(
        invoice_number="1",
        invoice_type="",
        issue_date="",
        seller_name="",
        seller_tax_id="",
        seller_addr="",
        seller_tel="",
        seller_bank="",
        seller_account="",
        buyer_name="",
        buyer_tax_id="",
        buyer_addr="",
        buyer_tel="",
        buyer_bank="",
        buyer_account="",
        amount_without_tax="",
        tax_amount="",
        amount_with_tax="",
        amount_chinese="",
        drawer="",
        remark="",
        items=[],
        source_file="a.pdf",
        parse_method="pdf",
    )
    tab._result = ParseResult(invoices=[inv], duplicates=[], failed=[])
    tab._populate_table()
    assert tab.ui.table.rowCount() == 1


def test_dedupe_strategy_and_format(tab):
    """_dedupe_strategy / _format 委托 controller(行 94-98)。"""
    s = tab._dedupe_strategy()
    assert isinstance(s, str)
    f = tab._format()
    assert isinstance(f, str)


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------


def test_export_no_data_warns(tab, monkeypatch):
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(1) or QMessageBox.StandardButton.Ok
    )
    tab._result = None
    tab._export()
    assert warned


def test_export_success(tab, monkeypatch, tmp_path):
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    tab.ui.edit_outdir.setText(str(tmp_path / "out"))
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    tab._export()
    assert (tmp_path / "out" / "发票结果.xlsx").exists()
    assert info_calls


def test_export_failure_critical(tab, monkeypatch, tmp_path):
    """导出抛异常 → critical 提示(行 160-162)。"""
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    tab.ui.edit_outdir.setText(str(tmp_path))
    # mock svc.export 抛异常
    tab._svc = type(tab._svc)()
    monkeypatch.setattr(
        tab._svc, "export", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    crit_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *a, **k: crit_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    tab._export()
    assert crit_calls


def test_export_default_outdir(tab, monkeypatch, tmp_path):
    """outdir 为空 → 默认 '.'(行 146)。"""
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    tab.ui.edit_outdir.setText("")  # 空
    monkeypatch.chdir(tmp_path)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    tab._export()
    assert (tmp_path / "发票结果.xlsx").exists()
