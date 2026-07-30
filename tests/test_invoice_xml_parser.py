from pathlib import Path

import pytest

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.parsers.xml_parser import (
    _normalize_tax_rate,
    _text,
    parse_xml,
)

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


def test_text_returns_empty_when_elem_none():
    """_text(elem=None, ...) → ''(行 13)。"""
    assert _text(None, "AnyTag") == ""


def test_text_returns_empty_when_child_missing():
    """_text:子元素缺失 → ''。"""
    import xml.etree.ElementTree as ET

    root = ET.fromstring("<root/>")
    assert _text(root, "Missing") == ""


def test_text_returns_empty_when_text_none():
    """_text:子元素存在但 text=None → ''。"""
    import xml.etree.ElementTree as ET

    root = ET.fromstring("<root><empty/></root>")
    assert _text(root, "empty") == ""


def test_text_strips_whitespace():
    """_text:strip 文本。"""
    import xml.etree.ElementTree as ET

    root = ET.fromstring("<root><v>  hello  </v></root>")
    assert _text(root, "v") == "hello"


# ---------------------------------------------------------------------------
# _normalize_tax_rate
# ---------------------------------------------------------------------------


def test_normalize_tax_rate_empty():
    """空串 → ''(行 24)。"""
    assert _normalize_tax_rate("") == ""
    assert _normalize_tax_rate("   ") == ""


def test_normalize_tax_rate_already_percent():
    """已含 % → 原样返回(行 26)。"""
    assert _normalize_tax_rate("13%") == "13%"
    assert _normalize_tax_rate("6.5%") == "6.5%"


def test_normalize_tax_rate_integer_percent():
    """0.13 → 13%(行 30-31,整数百分比)。"""
    assert _normalize_tax_rate("0.13") == "13%"
    assert _normalize_tax_rate("0.06") == "6%"


def test_normalize_tax_rate_non_integer_percent():
    """0.0625 → 6.25%(行 32,非整数百分比)。"""
    assert _normalize_tax_rate("0.0625") == "6.25%"


def test_normalize_tax_rate_value_error_returns_raw():
    """非数字(且无 %)→ ValueError → 原样返回(行 33-34)。"""
    assert _normalize_tax_rate("abc") == "abc"
    assert _normalize_tax_rate("免税") == "免税"


def test_normalize_tax_rate_decimal_rate():
    """0.130000 → 13%(多余的 0)。"""
    assert _normalize_tax_rate("0.130000") == "13%"


# ---------------------------------------------------------------------------
# _normalize_tax_rate:边界值(0 / 负数 / 掩码 / 全角)——锁定当前行为
# ---------------------------------------------------------------------------


def test_normalize_tax_rate_zero():
    """0 → 0%(红字/零税率发票)。"""
    assert _normalize_tax_rate("0") == "0%"


def test_normalize_tax_rate_negative():
    """负数税率(红字冲销发票)-0.13 → -13%。"""
    assert _normalize_tax_rate("-0.13") == "-13%"


def test_normalize_tax_rate_masked_passthrough():
    """掩码税率 ***% / 「不征税」原样透传(float 失败回退 raw)。"""
    assert _normalize_tax_rate("***%") == "***%"
    assert _normalize_tax_rate("不征税") == "不征税"


def test_normalize_tax_rate_fullwidth_percent_currently_raw():
    """全角 ％(U+FF05)当前**原样透传**(未归一为半角 %)。

    锁定当前行为:全角 ％ 出现在真实电子发票上,float('13％') 失败回退 raw。
    未来若新增全角归一逻辑,该测试应变红提醒有意更新。
    """
    assert _normalize_tax_rate("13％") == "13％"


# ---------------------------------------------------------------------------
# parse_xml:文件不存在 / 解析失败
# ---------------------------------------------------------------------------


def test_parse_xml_missing_file(tmp_path):
    """文件不存在 → UnsupportedFormatError。"""
    with pytest.raises(UnsupportedFormatError, match="文件不存在"):
        parse_xml(tmp_path / "nope.xml")


def test_parse_xml_parse_error(tmp_path):
    """非 XML 内容 → ParseError → UnsupportedFormatError(行 44-45)。"""
    f = tmp_path / "bad.xml"
    f.write_text("not xml <<", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError, match="XML 解析失败"):
        parse_xml(f)


# ---------------------------------------------------------------------------
# parse_xml:invoice_type 回退到 EInvoiceType(行 70-72)
# ---------------------------------------------------------------------------


def test_parse_xml_invoice_type_fallback_to_einvoicetype(tmp_path):
    """Header/InherentLabel 无 GeneralOrSpecialVAT → 回退 EInvoiceType.LabelName。"""
    f = tmp_path / "fallback.xml"
    f.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<EInvoice>
<Header><InherentLabel><EInvoiceType><LabelName>特殊发票类型</LabelName></EInvoiceType></InherentLabel></Header>
<EInvoiceData>
<SellerInformation><SellerName>销</SellerName><SellerIdNum>SID</SellerIdNum></SellerInformation>
<BuyerInformation><BuyerName>购</BuyerName><BuyerIdNum>BID</BuyerIdNum></BuyerInformation>
<BasicInformation><TotalAmWithoutTax>1</TotalAmWithoutTax><TotalTaxAm>1</TotalTaxAm>
<TotalTax-includedAmount>2</TotalTax-includedAmount>
<TotalTax-includedAmountInChinese>圆</TotalTax-includedAmountInChinese>
<Drawer>x</Drawer></BasicInformation>
</EInvoiceData>
<TaxSupervisionInfo><InvoiceNumber>123</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>
</EInvoice>""",
        encoding="utf-8",
    )
    inv = parse_xml(f)
    assert inv.invoice_type == "特殊发票类型"


def test_parse_xml_invoice_type_empty_when_no_header(tmp_path):
    """无 Header → invoice_type=''。"""
    f = tmp_path / "noheader.xml"
    f.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<EInvoice>
<EInvoiceData>
<SellerInformation><SellerName>销</SellerName><SellerIdNum>SID</SellerIdNum></SellerInformation>
<BuyerInformation><BuyerName>购</BuyerName><BuyerIdNum>BID</BuyerIdNum></BuyerInformation>
<BasicInformation><TotalAmWithoutTax>1</TotalAmWithoutTax><TotalTaxAm>1</TotalTaxAm>
<TotalTax-includedAmount>2</TotalTax-includedAmount>
<TotalTax-includedAmountInChinese>圆</TotalTax-includedAmountInChinese>
<Drawer>x</Drawer></BasicInformation>
</EInvoiceData>
<TaxSupervisionInfo><InvoiceNumber>123</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>
</EInvoice>""",
        encoding="utf-8",
    )
    inv = parse_xml(f)
    assert inv.invoice_type == ""


def test_parse_xml_no_data_section(tmp_path):
    """无 EInvoiceData → seller/buyer/basic 全空,不崩。"""
    f = tmp_path / "nodata.xml"
    f.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<EInvoice>
<TaxSupervisionInfo><InvoiceNumber>123</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>
</EInvoice>""",
        encoding="utf-8",
    )
    inv = parse_xml(f)
    assert inv.invoice_number == "123"
    assert inv.seller_name == ""
    assert inv.items == []


def test_parse_xml_items_with_decimal_tax_rate(tmp_path):
    """明细行税率 0.0625 → 6.25%(覆盖 _normalize_tax_rate 非整数分支,行 32)。"""
    f = tmp_path / "decimal_tax.xml"
    f.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<EInvoice>
<EInvoiceData>
<SellerInformation><SellerName>销</SellerName><SellerIdNum>SID</SellerIdNum></SellerInformation>
<BuyerInformation><BuyerName>购</BuyerName><BuyerIdNum>BID</BuyerIdNum></BuyerInformation>
<BasicInformation><TotalAmWithoutTax>1</TotalAmWithoutTax><TotalTaxAm>1</TotalTaxAm>
<TotalTax-includedAmount>2</TotalTax-includedAmount>
<TotalTax-includedAmountInChinese>圆</TotalTax-includedAmountInChinese>
<Drawer>x</Drawer></BasicInformation>
<IssuItemInformation>
<ItemName>品</ItemName><SpecMod/><MeaUnits>件</MeaUnits><Quantity>1</Quantity>
<UnPrice>10</UnPrice><Amount>10</Amount><TaxRate>0.0625</TaxRate><ComTaxAm>0.625</ComTaxAm>
</IssuItemInformation>
</EInvoiceData>
<TaxSupervisionInfo><InvoiceNumber>123</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>
</EInvoice>""",
        encoding="utf-8",
    )
    inv = parse_xml(f)
    assert len(inv.items) == 1
    assert inv.items[0].tax_rate == "6.25%"


def test_parse_xml_items_with_text_tax_rate(tmp_path):
    """明细行税率文本(如'免税')→ _normalize_tax_rate 原样(行 33-34)。"""
    f = tmp_path / "text_tax.xml"
    f.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<EInvoice>
<EInvoiceData>
<SellerInformation><SellerName>销</SellerName><SellerIdNum>SID</SellerIdNum></SellerInformation>
<BuyerInformation><BuyerName>购</BuyerName><BuyerIdNum>BID</BuyerIdNum></BuyerInformation>
<BasicInformation><TotalAmWithoutTax>1</TotalAmWithoutTax><TotalTaxAm>0</TotalTaxAm>
<TotalTax-includedAmount>1</TotalTax-includedAmount>
<TotalTax-includedAmountInChinese>圆</TotalTax-includedAmountInChinese>
<Drawer>x</Drawer></BasicInformation>
<IssuItemInformation>
<ItemName>品</ItemName><SpecMod/><MeaUnits>件</MeaUnits><Quantity>1</Quantity>
<UnPrice>10</UnPrice><Amount>10</Amount><TaxRate>免税</TaxRate><ComTaxAm>0</ComTaxAm>
</IssuItemInformation>
</EInvoiceData>
<TaxSupervisionInfo><InvoiceNumber>123</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>
</EInvoice>""",
        encoding="utf-8",
    )
    inv = parse_xml(f)
    assert inv.items[0].tax_rate == "免税"


def test_parse_xml_default_source_file(tmp_path):
    """不传 source_file → 用 path.name。"""
    f = tmp_path / "named.xml"
    f.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<EInvoice>
<EInvoiceData>
<SellerInformation><SellerName>销</SellerName><SellerIdNum>SID</SellerIdNum></SellerInformation>
<BuyerInformation><BuyerName>购</BuyerName><BuyerIdNum>BID</BuyerIdNum></BuyerInformation>
<BasicInformation><TotalAmWithoutTax>1</TotalAmWithoutTax><TotalTaxAm>1</TotalTaxAm>
<TotalTax-includedAmount>2</TotalTax-includedAmount>
<TotalTax-includedAmountInChinese>圆</TotalTax-includedAmountInChinese>
<Drawer>x</Drawer></BasicInformation>
</EInvoiceData>
<TaxSupervisionInfo><InvoiceNumber>123</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>
</EInvoice>""",
        encoding="utf-8",
    )
    inv = parse_xml(f)
    assert inv.source_file == "named.xml"
