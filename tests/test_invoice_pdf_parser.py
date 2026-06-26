from file_toolbox.core.invoice.parsers.pdf_parser import parse_pdf


def test_parse_pdf_invoice_number(pdf_sample):
    inv = parse_pdf(pdf_sample, source_file="sample.pdf")
    assert inv.invoice_number == "99990000000000000003"
    assert inv.parse_method == "pdf"
    assert inv.source_file == "sample.pdf"


def test_parse_pdf_parties(pdf_sample):
    inv = parse_pdf(pdf_sample, source_file="sample.pdf")
    assert inv.seller_name == "测试销售方有限公司"
    assert inv.seller_tax_id == "91SELLERTAXID00000X"
    assert inv.buyer_name == "测试购买方有限公司"
    assert inv.buyer_tax_id == "91BUYERTAXID00000Y"


def test_parse_pdf_items_with_empty_spec(pdf_sample):
    inv = parse_pdf(pdf_sample, source_file="sample.pdf")
    assert len(inv.items) == 3
    assert inv.items[0].name == "*交通运输设备*测试品甲"
    assert inv.items[0].spec == "TEST-001"
    assert inv.items[0].quantity == "2"
    assert inv.items[0].amount == "1000.00"
    assert inv.items[0].tax_rate == "13%"
    # 第二条规格为空(验证空单元格不错位)
    assert inv.items[1].name == "*交通运输设备*无规格品"
    assert inv.items[1].spec == ""
    assert inv.items[1].quantity == "3"
    # 第三条(有规格)
    assert inv.items[2].spec == "C-3"


def test_parse_pdf_totals(pdf_sample):
    inv = parse_pdf(pdf_sample, source_file="sample.pdf")
    assert inv.amount_without_tax == "1350.00"
    assert inv.tax_amount == "175.50"
    assert inv.amount_with_tax == "1525.50"
