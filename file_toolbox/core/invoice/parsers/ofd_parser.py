"""OFD 发票解析(ZIP 内 XML)。OFD.xml CustomData 优先,Content.xml 补充。

OFD 是 ZIP 包,本质是「XML 压缩封装」,字段可靠度近似 XML。
本版:CustomData(结构化键值)为主,Content.xml 的 TextCode 文本补充买卖方名称/大写金额等。
"""

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.types import Invoice

OFD_NS = "{http://www.ofdspec.org/2016}"


def _read_zip_member(zf: zipfile.ZipFile, name: str) -> str:
    """读 zip 内某成员文本,不存在返回空串。"""
    try:
        return zf.read(name).decode("utf-8", errors="replace")
    except KeyError:
        return ""


def _parse_custom_data(ofd_xml: str) -> dict[str, str]:
    """从 OFD.xml 的 CustomData 提取键值。返回 {name: value}。"""
    result: dict[str, str] = {}
    if not ofd_xml:
        return result
    try:
        root = ET.fromstring(ofd_xml)
    except ET.ParseError:
        return result
    for cd in root.iter(f"{OFD_NS}CustomData"):
        name = cd.get("Name", "")
        if name and cd.text:
            result[name] = cd.text.strip()
    return result


def _parse_content_texts(content_xml: str) -> list[str]:
    """从 Content.xml 提取所有 TextCode 文本,返回文本列表。"""
    texts: list[str] = []
    if not content_xml:
        return texts
    try:
        root = ET.fromstring(content_xml)
    except ET.ParseError:
        return texts
    for tc in root.iter(f"{OFD_NS}TextCode"):
        if tc.text:
            texts.append(tc.text.strip())
    return texts


def _extract_amount_chinese(texts: list[str]) -> str:
    """从文本里找大写金额(含 圆/元/角/分/整 的中文串)。"""
    for t in texts:
        if any(k in t for k in ("圆", "元", "角", "分", "整")) and any(
            "\u4e00" <= c <= "\u9fa5" for c in t
        ):
            return t
    return ""


def _extract_party_names(texts: list[str]) -> tuple[str, str]:
    """从'名称:'标签提取买卖方名称。第一个=销售方,第二个=购买方。"""
    hits = [t.split("名称:", 1)[1].strip() for t in texts if "名称:" in t]
    seller_name = hits[0] if len(hits) >= 1 else ""
    buyer_name = hits[1] if len(hits) >= 2 else ""
    return seller_name, buyer_name


def parse_ofd(path: Path, source_file: str = "") -> Invoice:
    """解析 OFD 发票文件。"""
    path = Path(path)
    if not path.exists():
        raise UnsupportedFormatError(f"文件不存在: {path}")
    try:
        with zipfile.ZipFile(path, "r") as zf:
            ofd_xml = _read_zip_member(zf, "OFD.xml")
            # 找 Content.xml:优先 Doc_0/Pages/Page_0/,回退到任意 Content.xml
            content_xml = _read_zip_member(zf, "Doc_0/Pages/Page_0/Content.xml")
            if not content_xml:
                for name in zf.namelist():
                    if name.endswith("Content.xml"):
                        content_xml = _read_zip_member(zf, name)
                        break
    except zipfile.BadZipFile as e:
        raise UnsupportedFormatError(f"OFD 不是有效 ZIP: {e}") from e

    if not ofd_xml:
        raise UnsupportedFormatError("OFD 缺少 OFD.xml")

    custom = _parse_custom_data(ofd_xml)
    texts = _parse_content_texts(content_xml)

    seller_name, buyer_name = _extract_party_names(texts)
    amount_chinese = _extract_amount_chinese(texts)

    return Invoice(
        invoice_number=custom.get("发票号码", ""),
        invoice_type="电子发票",
        issue_date=custom.get("开票日期", ""),
        seller_name=seller_name or custom.get("销售方名称", ""),
        seller_tax_id=custom.get("销售方纳税人识别号", ""),
        seller_addr=custom.get("销售方地址", ""),
        seller_tel=custom.get("销售方电话", ""),
        seller_bank=custom.get("销售方开户行", ""),
        seller_account=custom.get("销售方账号", ""),
        buyer_name=buyer_name or custom.get("购买方名称", ""),
        buyer_tax_id=custom.get("购买方纳税人识别号", ""),
        buyer_addr=custom.get("购买方地址", ""),
        buyer_tel=custom.get("购买方电话", ""),
        buyer_bank=custom.get("购买方开户行", ""),
        buyer_account=custom.get("购买方账号", ""),
        amount_without_tax=custom.get("合计金额", ""),
        tax_amount=custom.get("合计税额", ""),
        amount_with_tax=custom.get("价税合计", ""),
        amount_chinese=amount_chinese,
        drawer=custom.get("开票人", ""),
        remark=custom.get("备注", ""),
        items=[],  # OFD 明细行坐标聚类复杂,本版 CustomData 无明细,留空(PDF 路径处理明细)
        source_file=source_file or path.name,
        parse_method="ofd",
    )
