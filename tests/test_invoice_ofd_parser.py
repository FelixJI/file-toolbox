from file_toolbox.core.invoice.parsers.ofd_parser import parse_ofd


def test_parse_ofd_from_customdata(ofd_sample):
    inv = parse_ofd(ofd_sample, source_file="sample.ofd")
    # CustomData 提供的字段(最可靠)
    assert inv.invoice_number == "99990000000000000002"
    assert inv.seller_tax_id == "91SELLERTAXID00000X"
    assert inv.buyer_tax_id == "91BUYERTAXID00000Y"
    assert inv.amount_without_tax == "2000.00"
    assert inv.tax_amount == "260.00"
    assert inv.issue_date == "2026-05-19 10:00:00"
    assert inv.parse_method == "ofd"
    assert inv.source_file == "sample.ofd"


def test_parse_ofd_supplement_from_content(ofd_sample):
    inv = parse_ofd(ofd_sample, source_file="sample.ofd")
    # Content.xml 补全的字段
    assert inv.seller_name == "测试销售方有限公司"
    assert inv.buyer_name == "测试购买方有限公司"
    assert inv.amount_chinese == "贰仟贰佰陆拾圆整"


def test_parse_ofd_invoice_type_default(ofd_sample):
    inv = parse_ofd(ofd_sample, source_file="sample.ofd")
    # OFD 无显式发票类型标签时,从标题文本识别
    assert "电子发票" in inv.invoice_type or inv.invoice_type == ""
