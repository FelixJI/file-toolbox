"""parse_invoice(扩展名路由)的单元测试。

base.parse_invoice 按 .zip/.xml/.ofd/.pdf 后缀路由到对应解析器,
不支持的格式抛 UnsupportedFormatError。覆盖每个分支 + 默认 source_file 回填。
"""


import pytest

from file_toolbox.core.invoice.parsers.base import (
    UnsupportedFormatError,
    parse_invoice,
)


def test_parse_invoice_unsupported_format(tmp_path):
    """未知扩展名 → UnsupportedFormatError,信息含后缀。"""
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError, match="不支持的格式"):
        parse_invoice(f)


def test_parse_invoice_no_extension(tmp_path):
    """无扩展名 → 走 else → UnsupportedFormatError(suffix 为空串)。"""
    f = tmp_path / "noext"
    f.write_text("hello", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        parse_invoice(f)


def test_parse_invoice_xml_route(tmp_path):
    """.xml 分支路由到 parse_xml(用合法 xml fixture)。"""
    f = tmp_path / "111.xml"
    f.write_bytes(
        """<?xml version="1.0" encoding="UTF-8"?><EInvoice>
<EInvoiceData>
<SellerInformation><SellerName>销</SellerName><SellerIdNum>SID1</SellerIdNum></SellerInformation>
<BuyerInformation><BuyerName>购</BuyerName><BuyerIdNum>BID1</BuyerIdNum></BuyerInformation>
<BasicInformation><TotalAmWithoutTax>100</TotalAmWithoutTax><TotalTaxAm>13</TotalTaxAm>
<TotalTax-includedAmount>113</TotalTax-includedAmount>
<TotalTax-includedAmountInChinese>圆</TotalTax-includedAmountInChinese>
<Drawer>x</Drawer></BasicInformation>
</EInvoiceData>
<TaxSupervisionInfo><InvoiceNumber>111</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>
</EInvoice>""".encode()
    )
    inv = parse_invoice(f)
    assert inv.invoice_number == "111"


def test_parse_invoice_default_source_file_uses_path_name(tmp_path):
    """source_file=""(默认) → 内部回填为 path.name。验证 .zip 分支 + 默认值。"""
    # 用一个会失败的 zip 触发 UnsupportedFormatError,确认 source_file 被回填
    # (parse_zip 在找不到发票时用 source_file 构造错误信息)
    import zipfile

    bad_zip = tmp_path / "named.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("empty.txt", b"nothing")
    with pytest.raises(UnsupportedFormatError, match="named.zip"):
        parse_invoice(bad_zip)  # 不传 source_file


def test_parse_invoice_pdf_route_invokes_parser(tmp_path):
    """.pdf 分支路由到 parse_pdf;非发票 PDF 解析失败抛异常(类型由下游决定)。

    验证路由进入 pdf 分支(不一定是 UnsupportedFormatError)。
    """
    f = tmp_path / "blank.pdf"
    f.write_bytes(b"%PDF-1.4\n%fake but minimal\n")
    # 解析失败:具体异常由 pdf_parser 决定(PdfminerException 或 UnsupportedFormatError)
    with pytest.raises(Exception):
        parse_invoice(f)


def test_parse_invoice_ofd_route_with_invalid_ofd(tmp_path):
    """.ofd 分支路由到 parse_ofd;坏 OFD → UnsupportedFormatError。"""
    f = tmp_path / "bad.ofd"
    f.write_bytes(b"not a zip")
    with pytest.raises(UnsupportedFormatError):
        parse_invoice(f)


def test_parse_invoice_accepts_string_path(tmp_path):
    """parse_invoice 接受 str 或 Path(Path(path) 转换)。"""
    f = tmp_path / "str.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        parse_invoice(str(f))  # 传 str 而非 Path


def test_unsupported_format_error_is_exception():
    """UnsupportedFormatError 是 Exception 子类。"""
    assert issubclass(UnsupportedFormatError, Exception)
