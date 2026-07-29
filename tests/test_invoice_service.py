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
</EInvoice>""".encode()


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


# --- 新增可选 progress_callback / cancel_check(子项 4.1)---


def test_service_parse_progress_callback_invoked(tmp_path):
    """progress_callback 每文件后调用一次,(idx+1, total) 形状正确。"""
    f1 = _xml_file(tmp_path, "101")
    f2 = _xml_file(tmp_path, "102")
    f3 = _xml_file(tmp_path, "103")
    svc = InvoiceService()
    seen = []
    result = svc.parse_files([f1, f2, f3], progress_callback=lambda c, t: seen.append((c, t)))
    assert len(result.invoices) == 3
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_service_parse_progress_callback_skips_when_none(tmp_path):
    """progress_callback=None(默认)行为不变,不报错。"""
    f1 = _xml_file(tmp_path, "111")
    svc = InvoiceService()
    result = svc.parse_files([f1])  # 默认 progress_callback=None
    assert len(result.invoices) == 1


def test_service_parse_cancel_returns_partial(tmp_path):
    """cancel_check 返回 True 时在下一文件前中断,返回已解析的部分结果。"""
    f1 = _xml_file(tmp_path, "201")
    f2 = _xml_file(tmp_path, "202")
    f3 = _xml_file(tmp_path, "203")

    calls = {"n": 0}

    def cancel_check() -> bool:
        calls["n"] += 1
        # 第 2 次检查(即准备处理第 2 个文件前)取消
        return calls["n"] >= 2

    svc = InvoiceService()
    result = svc.parse_files([f1, f2, f3], cancel_check=cancel_check)
    # 仅解析了第 1 个文件
    assert len(result.invoices) == 1
    assert result.invoices[0].invoice_number == "201"


def test_service_parse_cancel_with_progress(tmp_path):
    """取消与进度回调可共存:进度只到取消点。"""
    files = [_xml_file(tmp_path, str(n)) for n in range(301, 306)]  # 5 个

    progress = []

    def cancel_check() -> bool:
        return len(progress) >= 3  # 收到 3 次进度后取消

    svc = InvoiceService()
    result = svc.parse_files(
        files,
        progress_callback=lambda c, t: progress.append((c, t)),
        cancel_check=cancel_check,
    )
    assert len(result.invoices) == 3
    assert progress == [(1, 5), (2, 5), (3, 5)]
