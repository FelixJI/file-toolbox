from pathlib import Path

from file_toolbox.core.invoice.service import InvoiceService


def _make_xml(num: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?><EInvoice>
<Header><InherentLabel><GeneralOrSpecialVAT><LabelName>增值税专用发票</LabelName></GeneralOrSpecialVAT></InherentLabel></Header>
<EInvoiceData>
  <SellerInformation><SellerName>销售{num}</SellerName><SellerIdNum>SID{num}</SellerIdNum><SellerAddr/><SellerTelNum/><SellerBankName/><SellerBankAccNum/></SellerInformation>
  <BuyerInformation><BuyerName>购买{num}</BuyerName><BuyerIdNum>BID{num}</BuyerIdNum><BuyerTelNum/><BuyerAddr/><BuyerBankName/><BuyerBankAccNum/></BuyerInformation>
  <BasicInformation><TotalAmWithoutTax>100.00</TotalAmWithoutTax><TotalTaxAm>13.00</TotalTaxAm><TotalTax-includedAmount>113.00</TotalTax-includedAmount><TotalTax-includedAmountInChinese>壹佰圆整</TotalTax-includedAmountInChinese><Drawer>测试</Drawer></BasicInformation>
</EInvoiceData>
<TaxSupervisionInfo><InvoiceNumber>{num}</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>
</EInvoice>""".encode("utf-8")


def _xml_file(tmp_path, num: str) -> Path:
    p = tmp_path / f"{num}.xml"
    p.write_bytes(_make_xml(num))
    return p


def test_service_parse_multiple(tmp_path):
    f1 = _xml_file(tmp_path, "111")
    f2 = _xml_file(tmp_path, "222")
    svc = InvoiceService()
    result = svc.parse_files([f1, f2])
    assert len(result.invoices) == 2
    assert result.failed == []


def test_service_failed_file_reported(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("not xml at all", encoding="utf-8")
    good = _xml_file(tmp_path, "333")
    svc = InvoiceService()
    result = svc.parse_files([good, bad])
    assert len(result.invoices) == 1
    assert len(result.failed) == 1
    assert result.failed[0].file == "bad.xml"


def test_service_dedupe_mark(tmp_path):
    # 同号两个文件
    z1 = _xml_file(tmp_path, "444")
    z2 = _xml_file(tmp_path, "444")
    svc = InvoiceService()
    result = svc.parse_files([z1, z2], dedupe_strategy="mark")
    assert len(result.invoices) == 2
    dup_count = sum(1 for i in result.invoices if i.is_duplicate)
    assert dup_count == 1


def test_service_export_excel_and_json(tmp_path):
    f1 = _xml_file(tmp_path, "555")
    svc = InvoiceService()
    result = svc.parse_files([f1])
    xlsx = tmp_path / "out.xlsx"
    jsn = tmp_path / "out.json"
    svc.export(result, xlsx, fmt="both", json_path=jsn)
    assert xlsx.exists()
    assert jsn.exists()
