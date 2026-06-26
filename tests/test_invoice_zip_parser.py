from file_toolbox.core.invoice.parsers.zip_parser import parse_zip


def test_zip_prefers_xml_when_nested(zip_with_xml):
    """完整 ZIP:含 pdf+ofd+嵌套 zip(内 xml),应优先采信 xml。"""
    inv = parse_zip(zip_with_xml, source_file="full.zip")
    assert inv.invoice_number == "99990000000000000001"
    assert inv.parse_method == "xml"           # 优先级 xml > ofd > pdf
    assert inv.seller_name == "测试销售方有限公司"


def test_zip_xml_direct(zip_xml_only):
    """ZIP 直接含 XML。"""
    inv = parse_zip(zip_xml_only, source_file="xml_only.zip")
    assert inv.invoice_number == "99990000000000000001"
    assert inv.parse_method == "xml"


def test_zip_fallback_to_ofd(zip_ofd_only):
    """ZIP 只含 OFD,回退到 OFD。"""
    inv = parse_zip(zip_ofd_only, source_file="ofd_only.zip")
    assert inv.invoice_number == "99990000000000000002"
    assert inv.parse_method == "ofd"
