"""xml_parser 内部辅助函数与边界的补充测试。

覆盖行:
- 13: _text(elem=None) → ""
- 24, 26: _normalize_tax_rate 空 / 含 %
- 30-32: 非整数百分比(如 0.0625 → 6.25%)
- 33-34: ValueError → 原样返回
- 70-72: invoice_type 回退到 EInvoiceType
- 文件不存在 / 非 XML 解析失败
"""

import pytest

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.parsers.xml_parser import (
    _normalize_tax_rate,
    _text,
    parse_xml,
)

# ---------------------------------------------------------------------------
# _text 辅助函数
# ---------------------------------------------------------------------------


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
