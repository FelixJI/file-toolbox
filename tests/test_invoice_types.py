from file_toolbox.core.invoice.types import (
    Invoice,
    LineItem,
    ParseResult,
    FailedFile,
)


def test_lineitem_defaults():
    item = LineItem(
        name="*交通运输设备*测试软管",
        spec="TEST-001",
        unit="根",
        quantity="2",
        unit_price="286",
        amount="572.00",
        tax_rate="13%",
        tax_amount="74.36",
    )
    assert item.name == "*交通运输设备*测试软管"
    assert item.spec == "TEST-001"


def test_invoice_defaults():
    inv = Invoice(
        invoice_number="12345678901234567890",
        invoice_type="增值税专用发票",
        issue_date="2026-05-19",
        seller_name="测试销售方有限公司",
        seller_tax_id="91TESTTAXID00000X",
        seller_addr="测试地址",
        seller_tel="010-12345678",
        seller_bank="测试银行支行",
        seller_account="0000000000000000000",
        buyer_name="测试购买方有限公司",
        buyer_tax_id="91BUYERTAXID00000Y",
        buyer_addr="测试购买方地址",
        buyer_tel="010-87654321",
        buyer_bank="测试买方银行",
        buyer_account="1111111111111111111",
        amount_without_tax="572.00",
        tax_amount="74.36",
        amount_with_tax="646.36",
        amount_chinese="陆佰肆拾陆圆叁角陆分",
        drawer="测试人",
        remark="测试备注",
    )
    assert inv.items == []
    assert inv.source_file == ""
    assert inv.parse_method == ""
    assert inv.is_duplicate is False


def test_parseresult_defaults():
    pr = ParseResult(invoices=[])
    assert pr.invoices == []
    assert pr.duplicates == []
    assert pr.failed == []


def test_failedfile():
    f = FailedFile(file="bad.zip", reason="损坏")
    assert f.file == "bad.zip"
    assert f.reason == "损坏"
