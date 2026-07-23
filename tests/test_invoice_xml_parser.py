from pathlib import Path

import pytest

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.parsers.xml_parser import parse_xml

FIXTURES = Path(__file__).parent / "fixtures" / "invoice"


def test_parse_xml_basic_fields():
    inv = parse_xml(FIXTURES / "sample_einvoice.xml", source_file="sample.xml")
    assert inv.invoice_number == "99990000000000000001"
    assert inv.invoice_type == "增值税专用发票"
    assert inv.issue_date == "2026-05-19"
    assert inv.seller_name == "测试销售方有限公司"
    assert inv.seller_tax_id == "91SELLERTAXID00000X"
    assert inv.seller_bank == "测试销售方银行支行"
    assert inv.seller_account == "0000000000000000001"
    assert inv.buyer_name == "测试购买方有限公司"
    assert inv.buyer_tax_id == "91BUYERTAXID00000Y"
    assert inv.amount_without_tax == "1000.00"
    assert inv.tax_amount == "130.00"
    assert inv.amount_with_tax == "1130.00"
    assert inv.amount_chinese == "壹仟壹佰叁拾圆整"
    assert inv.drawer == "测试开票人"
    assert inv.remark == "测试备注内容"
    assert inv.parse_method == "xml"
    assert inv.source_file == "sample.xml"


def test_parse_xml_items_with_empty_spec():
    inv = parse_xml(FIXTURES / "sample_einvoice.xml", source_file="sample.xml")
    assert len(inv.items) == 2
    item0 = inv.items[0]
    assert item0.name == "*交通运输设备*测试软管甲"
    assert item0.spec == "TEST-001"
    assert item0.unit == "根"
    assert item0.quantity == "2"
    assert item0.unit_price == "500"
    assert item0.amount == "1000.00"
    assert item0.tax_rate == "13%"  # 0.130000 归一化
    assert item0.tax_amount == "130.00"
    # 第二条规格/单位为空
    item1 = inv.items[1]
    assert item1.name == "*交通运输设备*无规格测试品"
    assert item1.spec == ""  # 空标签 normalize 为 ""
    assert item1.unit == ""


def test_parse_xml_invalid_raises():
    with pytest.raises(UnsupportedFormatError):
        parse_xml(FIXTURES / "notexist.xml")
