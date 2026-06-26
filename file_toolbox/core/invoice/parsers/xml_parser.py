"""XML 发票解析(<EInvoice> SWEI3200 schema)。"""

import xml.etree.ElementTree as ET
from pathlib import Path

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.types import Invoice, LineItem


def _text(elem: ET.Element | None, tag: str) -> str:
    """安全取子元素文本,缺失返回空串。"""
    if elem is None:
        return ""
    child = elem.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _normalize_tax_rate(raw: str) -> str:
    """0.130000 -> 13% ; 0.06 -> 6% ; 已是百分号或空则原样返回。"""
    raw = raw.strip()
    if not raw:
        return ""
    if "%" in raw:
        return raw
    try:
        rate = float(raw)
        pct = round(rate * 100, 4)
        if pct == int(pct):
            return f"{int(pct)}%"
        return f"{pct}%"
    except ValueError:
        return raw


def parse_xml(path: Path, source_file: str = "") -> Invoice:
    """解析 XML 发票文件。"""
    path = Path(path)
    if not path.exists():
        raise UnsupportedFormatError(f"文件不存在: {path}")
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise UnsupportedFormatError(f"XML 解析失败: {e}") from e
    root = tree.getroot()

    header = root.find("Header")
    data = root.find("EInvoiceData")
    tax_info = root.find("TaxSupervisionInfo")

    seller = data.find("SellerInformation") if data is not None else None
    buyer = data.find("BuyerInformation") if data is not None else None
    basic = data.find("BasicInformation") if data is not None else None

    remark = ""
    addl = data.find("AdditionalInformation") if data is not None else None
    if addl is not None:
        remark = _text(addl, "Remark")

    # 发票类型:取 InherentLabel/GeneralOrSpecialVAT 或 EInvoiceType 的 LabelName
    invoice_type = ""
    if header is not None:
        labels = header.find("InherentLabel")
        if labels is not None:
            vat = labels.find("GeneralOrSpecialVAT")
            if vat is not None:
                invoice_type = _text(vat, "LabelName")
            if not invoice_type:
                eit = labels.find("EInvoiceType")
                if eit is not None:
                    invoice_type = _text(eit, "LabelName")

    items: list[LineItem] = []
    if data is not None:
        for item_elem in data.findall("IssuItemInformation"):
            items.append(
                LineItem(
                    name=_text(item_elem, "ItemName"),
                    spec=_text(item_elem, "SpecMod"),
                    unit=_text(item_elem, "MeaUnits"),
                    quantity=_text(item_elem, "Quantity"),
                    unit_price=_text(item_elem, "UnPrice"),
                    amount=_text(item_elem, "Amount"),
                    tax_rate=_normalize_tax_rate(_text(item_elem, "TaxRate")),
                    tax_amount=_text(item_elem, "ComTaxAm"),
                )
            )

    return Invoice(
        invoice_number=_text(tax_info, "InvoiceNumber"),
        invoice_type=invoice_type,
        issue_date=_text(tax_info, "IssueTime"),
        seller_name=_text(seller, "SellerName"),
        seller_tax_id=_text(seller, "SellerIdNum"),
        seller_addr=_text(seller, "SellerAddr"),
        seller_tel=_text(seller, "SellerTelNum"),
        seller_bank=_text(seller, "SellerBankName"),
        seller_account=_text(seller, "SellerBankAccNum"),
        buyer_name=_text(buyer, "BuyerName"),
        buyer_tax_id=_text(buyer, "BuyerIdNum"),
        buyer_addr=_text(buyer, "BuyerAddr"),
        buyer_tel=_text(buyer, "BuyerTelNum"),
        buyer_bank=_text(buyer, "BuyerBankName"),
        buyer_account=_text(buyer, "BuyerBankAccNum"),
        amount_without_tax=_text(basic, "TotalAmWithoutTax"),
        tax_amount=_text(basic, "TotalTaxAm"),
        amount_with_tax=_text(basic, "TotalTax-includedAmount"),
        amount_chinese=_text(basic, "TotalTax-includedAmountInChinese"),
        drawer=_text(basic, "Drawer"),
        remark=remark,
        items=items,
        source_file=source_file or path.name,
        parse_method="xml",
    )
