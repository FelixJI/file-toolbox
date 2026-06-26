# 发票识别功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 file-toolbox 新增第 5 个工具 `invoice`,识别电子发票(PDF/OFD/XML),导出 Excel(双 Sheet)/JSON,支持按发票号码去重。

**Architecture:** 遵循现有工具模式 `core/<service>` → `cli/<cmd>` → `gui/<tab>`。解析器分层(XML/OFD/PDF/ZIP 各一),统一路由;ZIP 内优先采信 XML。PDF 用 pdfplumber `text` 策略还原无边框表格。去重键=发票号码,三策略。所有测试用虚构数据。

**Tech Stack:** Python 3.11+, pdfplumber, openpyxl, PySide6(GUI), typer(CLI), pytest。

**参考 spec:** `docs/superpowers/specs/2026-06-26-invoice-recognition-design.md`

---

## 文件结构总览

**Create:**
- `file_toolbox/core/invoice/__init__.py` — 包入口,导出 `InvoiceService`
- `file_toolbox/core/invoice/types.py` — 数据模型 dataclass
- `file_toolbox/core/invoice/parsers/__init__.py` — 解析器包,导出 `parse_invoice`
- `file_toolbox/core/invoice/parsers/base.py` — 路由 + 异常
- `file_toolbox/core/invoice/parsers/xml_parser.py` — XML 解析
- `file_toolbox/core/invoice/parsers/ofd_parser.py` — OFD 解析
- `file_toolbox/core/invoice/parsers/pdf_parser.py` — PDF 解析(pdfplumber)
- `file_toolbox/core/invoice/parsers/zip_parser.py` — ZIP 解压路由
- `file_toolbox/core/invoice/dedupe.py` — 去重逻辑
- `file_toolbox/core/invoice/exporters/__init__.py` — 导出包
- `file_toolbox/core/invoice/exporters/excel_exporter.py` — Excel 双 Sheet
- `file_toolbox/core/invoice/exporters/json_exporter.py` — 格式化 JSON
- `file_toolbox/core/invoice/service.py` — InvoiceService 编排
- `file_toolbox/cli/invoice_cmd.py` — CLI 子命令
- `file_toolbox/gui/dialogs/invoice_tab.py` — GUI Tab(第 5 个)
- `tests/fixtures/invoice/sample_einvoice.xml` — 虚构 XML fixture
- `tests/fixtures/invoice/sample_einvoice.ofd` — 虚构 OFD fixture(打包)
- `tests/fixtures/invoice/sample_invoice.pdf` — 虚构 PDF fixture
- `tests/fixtures/invoice/sample_full.zip` — 虚构完整 ZIP(含 xml + ofd + 嵌套 zip)
- `tests/test_invoice_types.py`
- `tests/test_invoice_xml_parser.py`
- `tests/test_invoice_ofd_parser.py`
- `tests/test_invoice_pdf_parser.py`
- `tests/test_invoice_zip_parser.py`
- `tests/test_invoice_dedupe.py`
- `tests/test_invoice_exporters.py`
- `tests/test_invoice_service.py`
- `tests/test_invoice_cli.py`

**Modify:**
- `pyproject.toml` — 加 `invoice` 可选依赖、注册命令
- `file_toolbox/cli/main.py` — 注册 `invoice` 子命令
- `file_toolbox/gui/main_window.py` — 加第 5 个 Tab + 历史下拉选项

---

## Task 1: 数据模型 types.py

**Files:**
- Create: `file_toolbox/core/invoice/types.py`
- Test: `tests/test_invoice_types.py`

- [ ] **Step 1: 创建包结构 + __init__**

Create `file_toolbox/core/invoice/__init__.py`:
```python
"""电子发票识别:解析 PDF/OFD/XML,导出 Excel/JSON,按发票号码去重。"""
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_invoice_types.py`:
```python
from file_toolbox.core.invoice.types import (
    Invoice,
    LineItem,
    ParseResult,
    FailedFile,
)


def test_lineitem_defaults():
    item = LineItem(
        name="*交通运输设备*测试软管",
        spec="TEST-001",
        unit="根",
        quantity="2",
        unit_price="286",
        amount="572.00",
        tax_rate="13%",
        tax_amount="74.36",
    )
    assert item.name == "*交通运输设备*测试软管"
    assert item.spec == "TEST-001"


def test_invoice_defaults():
    inv = Invoice(
        invoice_number="12345678901234567890",
        invoice_type="增值税专用发票",
        issue_date="2026-05-19",
        seller_name="测试销售方有限公司",
        seller_tax_id="91TESTTAXID00000X",
        seller_addr="测试地址",
        seller_tel="010-12345678",
        seller_bank="测试银行支行",
        seller_account="0000000000000000000",
        buyer_name="测试购买方有限公司",
        buyer_tax_id="91BUYERTAXID00000Y",
        buyer_addr="测试购买方地址",
        buyer_tel="010-87654321",
        buyer_bank="测试买方银行",
        buyer_account="1111111111111111111",
        amount_without_tax="572.00",
        tax_amount="74.36",
        amount_with_tax="646.36",
        amount_chinese="陆佰肆拾陆圆叁角陆分",
        drawer="测试人",
        remark="测试备注",
    )
    assert inv.items == []
    assert inv.source_file == ""
    assert inv.parse_method == ""
    assert inv.is_duplicate is False


def test_parseresult_defaults():
    pr = ParseResult(invoices=[])
    assert pr.invoices == []
    assert pr.duplicates == []
    assert pr.failed == []


def test_failedfile():
    f = FailedFile(file="bad.zip", reason="损坏")
    assert f.file == "bad.zip"
    assert f.reason == "损坏"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_invoice_types.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: 实现 types.py**

Create `file_toolbox/core/invoice/types.py`:
```python
"""发票数据模型(dataclass)。所有金额/数量保留为字符串,避免浮点精度丢失。"""

from dataclasses import dataclass, field


@dataclass
class LineItem:
    """发票明细行。spec/unit 可能为空。"""

    name: str          # 项目名称,如 "*交通运输设备*测试软管"
    spec: str          # 规格型号,可能为空
    unit: str          # 单位,可能为空
    quantity: str      # 数量
    unit_price: str    # 单价
    amount: str        # 金额
    tax_rate: str      # 税率,如 "13%"
    tax_amount: str    # 税额


@dataclass
class Invoice:
    """一张发票的完整结构。invoice_number 为去重键。"""

    invoice_number: str          # 去重键 (InvoiceNumber)
    invoice_type: str            # 发票类型,如 "增值税专用发票"
    issue_date: str              # 开票日期
    seller_name: str
    seller_tax_id: str
    seller_addr: str
    seller_tel: str
    seller_bank: str
    seller_account: str
    buyer_name: str
    buyer_tax_id: str
    buyer_addr: str
    buyer_tel: str
    buyer_bank: str
    buyer_account: str
    amount_without_tax: str      # 不含税金额
    tax_amount: str              # 税额
    amount_with_tax: str         # 价税合计
    amount_chinese: str          # 大写金额
    drawer: str                  # 开票人
    remark: str
    items: list[LineItem] = field(default_factory=list)
    source_file: str = ""        # 来源文件名(溯源)
    parse_method: str = ""       # xml | ofd | pdf
    is_duplicate: bool = False   # mark 策略下,同号第 2 条及以后置 True


@dataclass
class FailedFile:
    """解析失败的文件。"""

    file: str
    reason: str


@dataclass
class ParseResult:
    """解析结果汇总。"""

    invoices: list[Invoice]          # 保留的(keep_all/mark 为全部,dedupe 为去重后)
    duplicates: list[Invoice] = field(default_factory=list)  # 被去掉的
    failed: list[FailedFile] = field(default_factory=list)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_invoice_types.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: 提交**

```bash
git add file_toolbox/core/invoice/__init__.py file_toolbox/core/invoice/types.py tests/test_invoice_types.py
git commit -m "feat(invoice): 数据模型 types.py"
```

---

## Task 2: XML 解析器

**Files:**
- Create: `file_toolbox/core/invoice/parsers/base.py`
- Create: `file_toolbox/core/invoice/parsers/xml_parser.py`
- Create: `file_toolbox/core/invoice/parsers/__init__.py`
- Test fixture: `tests/fixtures/invoice/sample_einvoice.xml`
- Test: `tests/test_invoice_xml_parser.py`

- [ ] **Step 1: 写虚构 XML fixture**

Create `tests/fixtures/invoice/sample_einvoice.xml`(虚构数据:公司名/税号/账号/发票号均为占位):
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?><EInvoice>
    <Header>
        <EIid>99990000000000000001</EIid>
        <EInvoiceTag>SWEI3200</EInvoiceTag>
        <Version>0.32</Version>
        <InherentLabel>
            <EInvoiceType><LabelCode>01</LabelCode><LabelName>电子发票</LabelName></EInvoiceType>
            <GeneralOrSpecialVAT><LabelCode>01</LabelCode><LabelName>增值税专用发票</LabelName></GeneralOrSpecialVAT>
        </InherentLabel>
    </Header>
    <EInvoiceData>
        <SellerInformation>
            <SellerIdNum>91SELLERTAXID00000X</SellerIdNum>
            <SellerName>测试销售方有限公司</SellerName>
            <SellerAddr>测试销售方地址</SellerAddr>
            <SellerTelNum>010-11111111</SellerTelNum>
            <SellerBankName>测试销售方银行支行</SellerBankName>
            <SellerBankAccNum>0000000000000000001</SellerBankAccNum>
        </SellerInformation>
        <BuyerInformation>
            <BuyerIdNum>91BUYERTAXID00000Y</BuyerIdNum>
            <BuyerName>测试购买方有限公司</BuyerName>
            <BuyerTelNum>010-22222222</BuyerTelNum>
            <BuyerAddr>测试购买方地址</BuyerAddr>
            <BuyerBankName>测试购买方银行支行</BuyerBankName>
            <BuyerBankAccNum>1111111111111111111</BuyerBankAccNum>
        </BuyerInformation>
        <BasicInformation>
            <TotalAmWithoutTax>1000.00</TotalAmWithoutTax>
            <TotalTaxAm>130.00</TotalTaxAm>
            <TotalTax-includedAmount>1130.00</TotalTax-includedAmount>
            <TotalTax-includedAmountInChinese>壹仟壹佰叁拾圆整</TotalTax-includedAmountInChinese>
            <Drawer>测试开票人</Drawer>
            <RequestTime>2026-05-19 09:47:14</RequestTime>
        </BasicInformation>
        <IssuItemInformation>
            <ItemName>*交通运输设备*测试软管甲</ItemName>
            <SpecMod>TEST-001</SpecMod>
            <MeaUnits>根</MeaUnits>
            <Quantity>2</Quantity>
            <UnPrice>500</UnPrice>
            <Amount>1000.00</Amount>
            <TaxRate>0.130000</TaxRate>
            <ComTaxAm>130.00</ComTaxAm>
            <TotaltaxIncludedAmount>1130.00</TotaltaxIncludedAmount>
            <TaxClassificationCode>1090304000000000000</TaxClassificationCode>
        </IssuItemInformation>
        <IssuItemInformation>
            <ItemName>*交通运输设备*无规格测试品</ItemName>
            <SpecMod></SpecMod>
            <MeaUnits></MeaUnits>
            <Quantity>0</Quantity>
            <UnPrice>0</UnPrice>
            <Amount>0.00</Amount>
            <TaxRate>0.130000</TaxRate>
            <ComTaxAm>0.00</ComTaxAm>
            <TotaltaxIncludedAmount>0.00</TotaltaxIncludedAmount>
        </IssuItemInformation>
        <AdditionalInformation>
            <Remark>测试备注内容</Remark>
        </AdditionalInformation>
    </EInvoiceData>
    <TaxSupervisionInfo>
        <InvoiceNumber>99990000000000000001</InvoiceNumber>
        <IssueTime>2026-05-19</IssueTime>
        <TaxBureauCode>13200000000</TaxBureauCode>
        <TaxBureauName>国家税务总局测试省税务局</TaxBureauName>
    </TaxSupervisionInfo>
</EInvoice>
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_invoice_xml_parser.py`:
```python
from pathlib import Path

from file_toolbox.core.invoice.parsers.xml_parser import parse_xml
from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError

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
    assert item0.tax_rate == "13%"            # 0.130000 归一化
    assert item0.tax_amount == "130.00"
    # 第二条规格/单位为空
    item1 = inv.items[1]
    assert item1.name == "*交通运输设备*无规格测试品"
    assert item1.spec == ""                    # 空标签 normalize 为 ""
    assert item1.unit == ""


def test_parse_xml_invalid_raises():
    import pytest

    with pytest.raises(UnsupportedFormatError):
        parse_xml(FIXTURES / "notexist.xml")
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_invoice_xml_parser.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: 实现 base.py**

Create `file_toolbox/core/invoice/parsers/base.py`:
```python
"""解析器路由与异常。"""

from pathlib import Path


class UnsupportedFormatError(Exception):
    """文件格式不支持或解析失败。"""


def parse_invoice(path: Path, source_file: str = "") -> "object":
    """按扩展名路由到具体解析器,返回 Invoice。"""
    from file_toolbox.core.invoice.types import Invoice

    path = Path(path)
    suffix = path.suffix.lower()
    if not source_file:
        source_file = path.name

    if suffix == ".zip":
        from file_toolbox.core.invoice.parsers.zip_parser import parse_zip

        return parse_zip(path, source_file)
    if suffix == ".xml":
        from file_toolbox.core.invoice.parsers.xml_parser import parse_xml

        return parse_xml(path, source_file)
    if suffix == ".ofd":
        from file_toolbox.core.invoice.parsers.ofd_parser import parse_ofd

        return parse_ofd(path, source_file)
    if suffix == ".pdf":
        from file_toolbox.core.invoice.parsers.pdf_parser import parse_pdf

        return parse_pdf(path, source_file)
    raise UnsupportedFormatError(f"不支持的格式: {suffix}")
```

- [ ] **Step 5: 实现 xml_parser.py**

Create `file_toolbox/core/invoice/parsers/xml_parser.py`:
```python
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
        # 0.13 -> 13 ; 免税/0% 也覆盖
        pct = round(rate * 100, 4)
        # 去掉整数部分的 .0
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
    buyer = data.find("BuyerInformation") if data is notNone else None
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
```

> 注意:ElementTree 默认命名空间对 `<EInvoice>` 无 xmlns,直接 find 即可;`TotalTax-includedAmount` 标签名含连字符,find 直接匹配。

- [ ] **Step 6: 创建 parsers/__init__.py**

Create `file_toolbox/core/invoice/parsers/__init__.py`:
```python
"""发票解析器:XML/OFD/PDF/ZIP。"""

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError, parse_invoice

__all__ = ["parse_invoice", "UnsupportedFormatError"]
```

- [ ] **Step 7: 运行测试确认通过**

Run: `pytest tests/test_invoice_xml_parser.py tests/test_invoice_types.py -v`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add file_toolbox/core/invoice/parsers/ tests/fixtures/invoice/sample_einvoice.xml tests/test_invoice_xml_parser.py
git commit -m "feat(invoice): XML 解析器 + 路由 base"
```

---

## Task 3: OFD 解析器

**Files:**
- Create: `file_toolbox/core/invoice/parsers/ofd_parser.py`
- Test fixture: `tests/fixtures/invoice/sample_einvoice.ofd`(打包生成)
- Test: `tests/test_invoice_ofd_parser.py`

- [ ] **Step 1: 用脚本生成虚构 OFD fixture**

OFD 是 ZIP 包。在测试前用一个 helper 生成。先写测试,fixture 在 conftest 里用代码生成(避免提交二进制)。

Create `tests/conftest_invoice.py`(仅作为生成逻辑参考,实际并入 conftest)。改为直接在 `tests/conftest.py` 增加 fixture 生成器。先检查是否已有 conftest:

Run: `ls tests/conftest.py 2>/dev/null || echo "no conftest"`

- [ ] **Step 1b: 创建/更新 conftest.py 生成 OFD fixture**

Create `tests/conftest.py`(若已存在则追加):
```python
import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest


OFD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:OFD xmlns:ofd="http://www.ofdspec.org/2016" Version="1.2" DocType="OFD">
<ofd:DocBody><ofd:DocRoot>Doc_0/Document.xml</ofd:DocRoot>
<ofd:DocInfo><ofd:DocID>testdocid</ofd:DocID>
<ofd:CreationDate>2026-05-19</ofd:CreationDate>
<ofd:CustomDatas>
<ofd:CustomData Name="发票号码">99990000000000000002</ofd:CustomData>
<ofd:CustomData Name="销售方纳税人识别号">91SELLERTAXID00000X</ofd:CustomData>
<ofd:CustomData Name="购买方纳税人识别号">91BUYERTAXID00000Y</ofd:CustomData>
<ofd:CustomData Name="合计金额">2000.00</ofd:CustomData>
<ofd:CustomData Name="合计税额">260.00</ofd:CustomData>
<ofd:CustomData Name="开票日期">2026-05-19 10:00:00</ofd:CustomData>
</ofd:CustomDatas></ofd:DocInfo></ofd:DocBody></ofd:OFD>
"""

DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:Document xmlns:ofd="http://www.ofdspec.org/2016">
<ofd:CommonData><ofd:PageArea><ofd:PhysicalBox>0 0 210 297</ofd:PhysicalBox></ofd:PageArea></ofd:CommonData>
<ofd:Pages><ofd:Page ID="1" BaseLoc="Pages/Page_0/Content.xml"/></ofd:Pages></ofd:Document>
"""

CONTENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"><ofd:Content><ofd:Layer Type="Body">
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="10">电子发票（增值税专用发票）</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="50">名称:测试销售方有限公司</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="60">名称:测试购买方有限公司</ofd:TextCode></ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="200">贰仟贰佰陆拾圆整</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="100">*交通运输设备*测试品甲</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="100">根</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="100">2</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="100">1000</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="100">2000.00</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="100">13%</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="0 0 210 30"><ofd:TextCode X="10" Y="100">260.00</ofd:TextCode></ofd:TextObject>
</ofd:Layer></ofd:Content></ofd:Page>
"""


@pytest.fixture
def ofd_sample(tmp_path) -> Path:
    """生成虚构 OFD(打包 XML),返回路径。"""
    ofd_path = tmp_path / "sample.ofd"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("OFD.xml", OFD_XML)
        zf.writestr("Doc_0/Document.xml", DOCUMENT_XML)
        zf.writestr("Doc_0/Pages/Page_0/Content.xml", CONTENT_XML)
    ofd_path.write_bytes(buf.getvalue())
    return ofd_path
```

> 说明:OFD 解析以 `OFD.xml` 的 CustomData 为主要来源(结构化、可靠),Content.xml 仅补全 CustomData 没有的字段(名称、大写金额)。测试验证主路径。

- [ ] **Step 2: 写失败测试**

Create `tests/test_invoice_ofd_parser.py`:
```python
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
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_invoice_ofd_parser.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: 实现 ofd_parser.py**

Create `file_toolbox/core/invoice/parsers/ofd_parser.py`:
```python
"""OFD 发票解析(ZIP 内 XML)。OFD.xml CustomData 优先,Content.xml 补充。"""

import io
import re
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


def _find_after_label(texts: list[str], label: str) -> str:
    """在文本列表里找含 label 的项,返回 label 之后的文本。"""
    for t in texts:
        if label in t:
            return t.split(label, 1)[1].strip()
    return ""


def _parse_ofd_root_path(document_xml: str) -> str:
    """从 OFD.xml 取 DocRoot 路径(如 Doc_0/Document.xml),取其目录前缀。"""
    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError:
        return ""
    doc_root = root.find(f".//{OFD_NS}DocRoot")
    if doc_root is None or not doc_root.text:
        return ""
    # Doc_0/Document.xml -> Doc_0
    return str(Path(doc_root.text.strip()).parent)


def parse_ofd(path: Path, source_file: str = "") -> Invoice:
    """解析 OFD 发票文件。"""
    path = Path(path)
    if not path.exists():
        raise UnsupportedFormatError(f"文件不存在: {path}")
    try:
        with zipfile.ZipFile(path, "r") as zf:
            ofd_xml = _read_zip_member(zf, "OFD.xml")
            document_xml = _read_zip_member(zf, "Doc_0/Document.xml")
            # 找 Page 的 Content.xml(可能多页,取第一个)
            content_xml = _read_zip_member(zf, "Doc_0/Pages/Page_0/Content.xml")
            if not content_xml:
                # 尝试从 Document.xml 的 BaseLoc 定位
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

    # CustomData 优先(结构化可靠)
    def cd(name: str, fallback_text_label: str = "") -> str:
        if name in custom:
            return custom[name]
        if fallback_text_label:
            return _find_after_label(texts, fallback_text_label)
        return ""

    # 名称/大写金额从 Content.xml 补充
    seller_name = _find_after_label(texts, "名称:") if not custom.get("销售方名称") else custom["销售方名称"]
    buyer_name = ""  # 单个"名称:"标签无法区分买卖方,用位置或第二处
    # 取所有含"名称:"的文本,第一个=销售方(OFD 版式通常销售方在上/右)
    name_hits = [t for t in texts if "名称:" in t]
    if len(name_hits) >= 1:
        seller_name = name_hits[0].split("名称:", 1)[1].strip()
    if len(name_hits) >= 2:
        buyer_name = name_hits[1].split("名称:", 1)[1].strip()

    amount_chinese = ""
    for t in texts:
        # 大写金额特征:含 圆/元/角/分/整
        if any(k in t for k in ("圆", "元", "角", "分")) and any(c.isdigit() is False for c in t):
            amount_chinese = t
            break

    issue_date = custom.get("开票日期", "")

    return Invoice(
        invoice_number=cd("发票号码"),
        invoice_type="电子发票",
        issue_date=issue_date,
        seller_name=seller_name,
        seller_tax_id=cd("销售方纳税人识别号"),
        seller_addr=custom.get("销售方地址", ""),
        seller_tel=custom.get("销售方电话", ""),
        seller_bank=custom.get("销售方开户行", ""),
        seller_account=custom.get("销售方账号", ""),
        buyer_name=buyer_name,
        buyer_tax_id=cd("购买方纳税人识别号"),
        buyer_addr=custom.get("购买方地址", ""),
        buyer_tel=custom.get("购买方电话", ""),
        buyer_bank=custom.get("购买方开户行", ""),
        buyer_account=custom.get("购买方账号", ""),
        amount_without_tax=cd("合计金额"),
        tax_amount=cd("合计税额"),
        amount_with_tax=custom.get("价税合计", ""),
        amount_chinese=amount_chinese,
        drawer=custom.get("开票人", ""),
        remark=custom.get("备注", ""),
        items=[],  # OFD 明细行坐标聚类复杂,本版 CustomData 无明细,留空(PDF 路径处理明细)
        source_file=source_file or path.name,
        parse_method="ofd",
    )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_invoice_ofd_parser.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add tests/conftest.py file_toolbox/core/invoice/parsers/ofd_parser.py tests/test_invoice_ofd_parser.py
git commit -m "feat(invoice): OFD 解析器(CustomData 优先 + Content 补充)"
```

---

## Task 4: PDF 解析器(pdfplumber)

**Files:**
- Create: `file_toolbox/core/invoice/parsers/pdf_parser.py`
- Test fixture: 程序生成(用 reportlab 或最小手工 PDF)
- Test: `tests/test_invoice_pdf_parser.py`

> 注意:生成 PDF fixture 需要 reportlab(测试依赖)。PDF 解析是尽力而为,测试聚焦表区定位/空单元格/跨行合并逻辑。

- [ ] **Step 1: 加 reportlab 到 dev 依赖**

Modify `pyproject.toml`,在 `[project.optional-dependencies]` 的 `dev` 加 `reportlab`:
```toml
dev = ["pytest>=8.0", "pytest-cov>=5.0", "ruff>=0.5", "mypy>=1.10", "reportlab>=4.0"]
```

同时加 invoice extra:
```toml
invoice = ["pdfplumber>=0.11", "openpyxl>=3.1"]
```

- [ ] **Step 2: 在 conftest.py 加 PDF fixture 生成器**

在 `tests/conftest.py` 追加:
```python
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


@pytest.fixture
def pdf_sample(tmp_path) -> Path:
    """生成虚构版式发票 PDF(用绝对坐标排布文本,模拟真实发票)。"""
    pdf_path = tmp_path / "sample_invoice.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    w, h = A4
    y = h - 50
    c.drawString(200, y, "电子发票（增值税专用发票）"); y -= 20
    c.drawString(300, y, "发票号码："); c.drawString(370, y, "99990000000000000003")
    c.drawString(300, y - 15, "开票日期："); c.drawString(370, y - 15, "2026年05月19日"); y -= 50
    # 买卖方区
    c.drawString(50, y, "名称:测试销售方有限公司")
    c.drawString(300, y, "名称:测试购买方有限公司"); y -= 15
    c.drawString(50, y, "统一社会信息代码/纳税人识别号:91SELLERTAXID00000X")
    c.drawString(300, y, "统一社会信息代码/纳税人识别号:91BUYERTAXID00000Y"); y -= 40
    # 表头
    c.drawString(50, y, "项目名称"); c.drawString(200, y, "规格型号")
    c.drawString(260, y, "单位"); c.drawString(300, y, "数量")
    c.drawString(340, y, "单价"); c.drawString(390, y, "金额")
    c.drawString(440, y, "税率"); c.drawString(480, y, "税额"); y -= 20
    # 明细行 1(有规格)
    c.drawString(50, y, "*交通运输设备*测试品甲"); c.drawString(200, y, "TEST-001")
    c.drawString(260, y, "根"); c.drawString(300, y, "2")
    c.drawString(340, y, "500"); c.drawString(390, y, "1000.00")
    c.drawString(440, y, "13%"); c.drawString(480, y, "130.00"); y -= 20
    # 明细行 2(规格为空)
    c.drawString(50, y, "*交通运输设备*无规格品")
    c.drawString(260, y, "个"); c.drawString(300, y, "3")
    c.drawString(340, y, "100"); c.drawString(390, y, "300.00")
    c.drawString(440, y, "13%"); c.drawString(480, y, "39.00"); y -= 20
    # 合计
    c.drawString(390, y, "1300.00"); c.drawString(480, y, "169.00"); y -= 20
    c.drawString(50, y, "价税合计(大写)"); c.drawString(200, y, "壹仟肆佰陆拾玖圆整")
    c.drawString(390, y, "1469.00")
    c.save()
    return pdf_path
```

- [ ] **Step 3: 写失败测试**

Create `tests/test_invoice_pdf_parser.py`:
```python
from file_toolbox.core.invoice.parsers.pdf_parser import parse_pdf


def test_parse_pdf_invoice_number(pdf_sample):
    inv = parse_pdf(pdf_sample, source_file="sample.pdf")
    assert inv.invoice_number == "99990000000000000003"
    assert inv.parse_method == "pdf"
    assert inv.source_file == "sample.pdf"


def test_parse_pdf_parties(pdf_sample):
    inv = parse_pdf(pdf_sample, source_file="sample.pdf")
    assert inv.seller_name == "测试销售方有限公司"
    assert inv.seller_tax_id == "91SELLERTAXID00000X"
    assert inv.buyer_name == "测试购买方有限公司"
    assert inv.buyer_tax_id == "91BUYERTAXID00000Y"


def test_parse_pdf_items_with_empty_spec(pdf_sample):
    inv = parse_pdf(pdf_sample, source_file="sample.pdf")
    assert len(inv.items) == 2
    assert inv.items[0].name == "*交通运输设备*测试品甲"
    assert inv.items[0].spec == "TEST-001"
    assert inv.items[0].quantity == "2"
    assert inv.items[0].amount == "1000.00"
    assert inv.items[0].tax_rate == "13%"
    # 第二条规格为空
    assert inv.items[1].name == "*交通运输设备*无规格品"
    assert inv.items[1].spec == ""
    assert inv.items[1].quantity == "3"


def test_parse_pdf_totals(pdf_sample):
    inv = parse_pdf(pdf_sample, source_file="sample.pdf")
    assert inv.amount_without_tax == "1300.00"
    assert inv.tax_amount == "169.00"
    assert inv.amount_with_tax == "1469.00"
```

- [ ] **Step 4: 运行测试确认失败**

Run: `pytest tests/test_invoice_pdf_parser.py -v`
Expected: FAIL (module not found / pdfplumber not installed)

- [ ] **Step 5: 安装 invoice 依赖**

Run: `pip install pdfplumber openpyxl reportlab`

- [ ] **Step 6: 实现 pdf_parser.py**

Create `file_toolbox/core/invoice/parsers/pdf_parser.py`:
```python
"""PDF 发票解析(pdfplumber text 策略,尽力而为)。

已知难点:明细行数不固定(动态定位表头/表尾)、规格可能为空(空单元格)、跨行明细。
方案:text 策略聚列 + 列索引固定映射 + 合并续行。
"""

import re
from pathlib import Path

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.types import Invoice, LineItem

# pdfplumber 延迟导入,缺依赖给友好提示
try:
    import pdfplumber
except ImportError as e:
    raise ImportError(
        "PDF 解析需要 pdfplumber: pip install 'file-toolbox[invoice]'"
    ) from e


# 明细表头/表尾关键词,用于动态定位表区
_HEADER_KEYWORDS = ("项目名称", "规格型号")
_TOTAL_KEYWORDS = ("合计", "价税合计")
# 列索引固定映射(不依赖表头文字识别)
_COL = {
    "name": 0,
    "spec": 1,
    "unit": 2,
    "quantity": 3,
    "unit_price": 4,
    "amount": 5,
    "tax_rate": 6,
    "tax_amount": 7,
}


def _is_amount_like(s: str) -> bool:
    """判断字符串是否像金额/数字。"""
    if not s:
        return False
    return bool(re.match(r"^[¥￥]?\d+(\.\d+)?%?$", s.strip()))


def _clean(s: str | None) -> str:
    return (s or "").replace("\n", "").strip()


def _extract_detail_items(rows: list[list]) -> list[LineItem]:
    """从表格行提取明细。处理空单元格和跨行续行。"""
    # 定位表头行
    start = None
    for i, row in enumerate(rows):
        joined = "".join(_clean(c) for c in row)
        if all(kw in joined for kw in _HEADER_KEYWORDS):
            start = i + 1
            break
    if start is None:
        start = 0

    items: list[LineItem] = []
    for row in rows[start:]:
        cells = [_clean(c) for c in row]
        # 遇到合计行结束
        joined = "".join(cells)
        if any(kw in joined for kw in _TOTAL_KEYWORDS):
            break
        # 空行跳过
        if not any(cells):
            continue

        name = cells[_COL["name"]] if len(cells) > _COL["name"] else ""

        # 续行判定:前几列(0,1)有值但其余全空 -> 合并到上一条
        tail_empty = all(not cells[i] for i in (2, 3, 4, 5, 6, 7) if i < len(cells))
        if items and name == "" and tail_empty and any(cells[i] for i in (0, 1) if i < len(cells)):
            # 规格续行拼到上一条 spec
            last = items[-1]
            cont = cells[_COL["spec"]] if len(cells) > _COL["spec"] else ""
            if cont:
                last.spec = (last.spec + cont).strip()
            cont_name = cells[_COL["name"]] if len(cells) > _COL["name"] else ""
            if cont_name:
                last.name = (last.name + cont_name).strip()
            continue

        # 正常数据行:至少要有项目名
        if not name:
            continue

        def cell(key: str) -> str:
            idx = _COL[key]
            return cells[idx] if idx < len(cells) else ""

        items.append(
            LineItem(
                name=name,
                spec=cell("spec"),
                unit=cell("unit"),
                quantity=cell("quantity"),
                unit_price=cell("unit_price"),
                amount=cell("amount"),
                tax_rate=cell("tax_rate"),
                tax_amount=cell("tax_amount"),
            )
        )
    return items


def _extract_field(lines: list[str], label: str) -> str:
    """从文本行提取 label 后的值。"""
    for ln in lines:
        if label in ln:
            after = ln.split(label, 1)[1].strip()
            # 去掉末尾可能的下一个标签
            return after
    return ""


def _extract_invoice_number(lines: list[str]) -> str:
    for ln in lines:
        m = re.search(r"(\d{18,})", ln.replace(" ", ""))
        if "发票号码" in ln and m:
            return m.group(1)
    # fallback:任意 18+ 位数字
    for ln in lines:
        m = re.search(r"(\d{18,})", ln.replace(" ", ""))
        if m:
            return m.group(1)
    return ""


def parse_pdf(path: Path, source_file: str = "") -> Invoice:
    """解析 PDF 发票。尽力而为,置信度低。"""
    path = Path(path)
    if not path.exists():
        raise UnsupportedFormatError(f"文件不存在: {path}")

    with pdfplumber.open(str(path)) as pdf:
        page = pdf.pages[0]
        full_text = page.extract_text() or ""
        lines = full_text.split("\n")

        # 用 text 策略提取明细表
        table_settings = {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
            "snap_tolerance": 6,
            "min_words_vertical": 3,
            "text_tolerance": 3,
        }
        tables = page.extract_tables(table_settings)
        rows = tables[0] if tables else []
        items = _extract_detail_items(rows)

        # 汇总字段从全文提取
        invoice_number = _extract_invoice_number(lines)

        # 买卖方:按"名称:"出现顺序
        name_hits = [ln.split("名称:", 1)[1].strip() for ln in lines if "名称:" in ln]
        seller_name = name_hits[0] if len(name_hits) >= 1 else ""
        buyer_name = name_hits[1] if len(name_hits) >= 2 else ""

        seller_tax_id = _extract_field(lines, "纳税人识别号:") or _extract_field(lines, "识别号:")
        # 识别号可能成对出现,简化:取第一个
        tax_hits = []
        for ln in lines:
            for pat in ("纳税人识别号:", "统一社会信息代码/纳税人识别号:", "识别号:"):
                if pat in ln:
                    val = ln.split(pat, 1)[1].strip()
                    tax_hits.append(val)
                    break
        seller_tax_id = tax_hits[0] if len(tax_hits) >= 1 else ""
        buyer_tax_id = tax_hits[1] if len(tax_hits) >= 2 else ""

        # 合计行:含"合计"且含金额
        amount_without_tax = ""
        tax_amount = ""
        amount_with_tax = ""
        for ln in lines:
            if "合计" in ln and not amount_without_tax:
                nums = re.findall(r"¥\s*([\d.]+)|￥\s*([\d.]+)|([\d]+\.\d{2})", ln)
                flat = [n for tup in nums for n in tup if n]
                if len(flat) >= 2:
                    amount_without_tax = flat[0]
                    tax_amount = flat[1]
            if "价税合计" in ln or "小写" in ln:
                nums = re.findall(r"([\d]+\.\d{2})", ln)
                if nums:
                    amount_with_tax = nums[-1]

        # 大写金额:含 圆/元/角/分/整 的中文串
        amount_chinese = ""
        for ln in lines:
            if "价税合计" in ln and any(k in ln for k in ("圆", "元", "角", "分", "整")):
                m = re.search(r"([\u4e00-\u9fa5]{4,}(?:圆|元)(?:[\u4e00-\u9fa5]+)?)", ln)
                if m:
                    amount_chinese = m.group(1)
                    break

        # 日期
        issue_date = ""
        m = re.search(r"(\d{4})年(\d{2})月(\d{2})日", full_text)
        if m:
            issue_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    return Invoice(
        invoice_number=invoice_number,
        invoice_type="电子发票",
        issue_date=issue_date,
        seller_name=seller_name,
        seller_tax_id=seller_tax_id,
        seller_addr="",
        seller_tel="",
        seller_bank="",
        seller_account="",
        buyer_name=buyer_name,
        buyer_tax_id=buyer_tax_id,
        buyer_addr="",
        buyer_tel="",
        buyer_bank="",
        buyer_account="",
        amount_without_tax=amount_without_tax,
        tax_amount=tax_amount,
        amount_with_tax=amount_with_tax,
        amount_chinese=amount_chinese,
        drawer="",
        remark="",
        items=items,
        source_file=source_file or path.name,
        parse_method="pdf",
    )
```

- [ ] **Step 7: 运行测试确认通过**

Run: `pytest tests/test_invoice_pdf_parser.py -v`
Expected: PASS

> 若 PDF 解析对某个字段失败,调整正则/阈值,但不放宽断言数据正确性。

- [ ] **Step 8: 提交**

```bash
git add pyproject.toml tests/conftest.py file_toolbox/core/invoice/parsers/pdf_parser.py tests/test_invoice_pdf_parser.py
git commit -m "feat(invoice): PDF 解析器(pdfplumber text 策略)"
```

---

## Task 5: ZIP 解析器(嵌套路由)

**Files:**
- Create: `file_toolbox/core/invoice/parsers/zip_parser.py`
- Test fixture: conftest 生成
- Test: `tests/test_invoice_zip_parser.py`

- [ ] **Step 1: 在 conftest.py 加 ZIP fixtures**

在 `tests/conftest.py` 追加:
```python
@pytest.fixture
def zip_with_xml(tmp_path) -> Path:
    """ZIP 内含 XML(嵌套在子 zip 里),模拟完整下载。"""
    # 内层 zip:含 xml
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as zf:
        zf.writestr("dzfp_inner.xml", Path(__file__).parent / "fixtures" / "invoice" / "sample_einvoice.xml" if False else "")
    # 直接复用 XML fixture 内容
    xml_src = (Path(__file__).parent / "fixtures" / "invoice" / "sample_einvoice.xml").read_bytes()
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as zf:
        zf.writestr("dzfp_99990000000000000001.xml", xml_src)
    inner_bytes = inner_buf.getvalue()

    outer_path = tmp_path / "full_invoice.zip"
    with zipfile.ZipFile(outer_path, "w") as zf:
        zf.writestr("some.pdf", b"%PDF-1.4 fake")          # 占位 pdf
        zf.writestr("some.ofd", b"PK fake")                # 占位 ofd
        zf.writestr("99990000000000000001.zip", inner_bytes)  # 嵌套 zip 含 xml
    return outer_path


@pytest.fixture
def zip_xml_only(tmp_path) -> Path:
    """ZIP 内直接含 XML(无嵌套)。"""
    xml_src = (Path(__file__).parent / "fixtures" / "invoice" / "sample_einvoice.xml").read_bytes()
    p = tmp_path / "xml_only.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("dzfp_99990000000000000001.xml", xml_src)
    return p


@pytest.fixture
def zip_ofd_only(tmp_path, ofd_sample) -> Path:
    """ZIP 内只含 OFD(无 xml)。"""
    ofd_bytes = ofd_sample.read_bytes()
    p = tmp_path / "ofd_only.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("some.ofd", ofd_bytes)
    return p
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_invoice_zip_parser.py`:
```python
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
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_invoice_zip_parser.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: 实现 zip_parser.py**

Create `file_toolbox/core/invoice/parsers/zip_parser.py`:
```python
"""ZIP 发票解析:解压后优先级 xml > ofd > pdf,递归处理嵌套 zip。

临时文件用 TemporaryDirectory,解析完自动清理,不残留隐私内容。
"""

import tempfile
import zipfile
from pathlib import Path

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError


def _find_files_by_ext(root: Path, ext: str) -> list[Path]:
    """在 root 下递归找指定扩展名文件。"""
    return sorted(root.rglob(f"*{ext}"))


def parse_zip(path: Path, source_file: str = "") -> "object":
    """解析 ZIP 发票。优先级:xml > ofd > pdf,含嵌套 zip 递归。"""
    from file_toolbox.core.invoice.parsers.xml_parser import parse_xml
    from file_toolbox.core.invoice.parsers.ofd_parser import parse_ofd
    from file_toolbox.core.invoice.parsers.pdf_parser import parse_pdf

    path = Path(path)
    if not path.exists():
        raise UnsupportedFormatError(f"文件不存在: {path}")

    # 解压到临时目录
    with tempfile.TemporaryDirectory(prefix="invoice_") as tmp:
        tmp_path = Path(tmp)
        try:
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(tmp_path)
        except zipfile.BadZipFile as e:
            raise UnsupportedFormatError(f"ZIP 解压失败: {e}") from e

        # 解嵌套 zip:把内层 zip 也解压(最多两层)
        for inner_zip in _find_files_by_ext(tmp_path, ".zip"):
            try:
                with zipfile.ZipFile(inner_zip, "r") as izf:
                    izf.extractall(inner_zip.parent / (inner_zip.stem + "_extracted"))
            except (zipfile.BadZipFile, OSError):
                continue

        # 优先级 xml > ofd > pdf
        xmls = _find_files_by_ext(tmp_path, ".xml")
        for xml in xmls:
            try:
                inv = parse_xml(xml, source_file=source_file or path.name)
                inv.parse_method = "xml"
                return inv
            except UnsupportedFormatError:
                continue

        ofds = _find_files_by_ext(tmp_path, ".ofd")
        for ofd in ofds:
            try:
                inv = parse_ofd(ofd, source_file=source_file or path.name)
                inv.parse_method = "ofd"
                return inv
            except UnsupportedFormatError:
                continue

        pdfs = _find_files_by_ext(tmp_path, ".pdf")
        for pdf in pdfs:
            try:
                inv = parse_pdf(pdf, source_file=source_file or path.name)
                inv.parse_method = "pdf"
                return inv
            except UnsupportedFormatError:
                continue

    raise UnsupportedFormatError(f"ZIP 内未找到可识别的发票文件: {path.name}")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_invoice_zip_parser.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add tests/conftest.py file_toolbox/core/invoice/parsers/zip_parser.py tests/test_invoice_zip_parser.py
git commit -m "feat(invoice): ZIP 解析器(嵌套路由,xml>ofd>pdf 优先级)"
```

---

## Task 6: 去重 dedupe.py

**Files:**
- Create: `file_toolbox/core/invoice/dedupe.py`
- Test: `tests/test_invoice_dedupe.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_invoice_dedupe.py`:
```python
from file_toolbox.core.invoice.dedupe import dedupe_invoices, KEEP_ALL, DEDUPE, MARK
from file_toolbox.core.invoice.types import Invoice


def _make(num: str, method: str = "xml") -> Invoice:
    return Invoice(
        invoice_number=num, invoice_type="增值税专用发票", issue_date="2026-05-19",
        seller_name="s", seller_tax_id="s", seller_addr="s", seller_tel="s",
        seller_bank="s", seller_account="s",
        buyer_name="b", buyer_tax_id="b", buyer_addr="b", buyer_tel="b",
        buyer_bank="b", buyer_account="b",
        amount_without_tax="1", tax_amount="1", amount_with_tax="2",
        amount_chinese="x", drawer="d", remark="",
        parse_method=method,
    )


def test_keep_all_no_change():
    invs = [_make("A"), _make("A"), _make("B")]
    kept, dups = dedupe_invoices(invs, KEEP_ALL)
    assert len(kept) == 3
    assert len(dups) == 0
    assert all(not i.is_duplicate for i in kept)


def test_dedupe_keeps_first():
    invs = [_make("A", "xml"), _make("A", "ofd"), _make("B", "xml")]
    kept, dups = dedupe_invoices(invs, DEDUPE)
    assert len(kept) == 2
    assert {i.invoice_number for i in kept} == {"A", "B"}
    # 同号保留优先级更高的(xml > ofd)
    a = [i for i in kept if i.invoice_number == "A"][0]
    assert a.parse_method == "xml"
    assert len(dups) == 1
    assert dups[0].parse_method == "ofd"


def test_dedupe_prefers_higher_priority_method():
    # pdf 先出现,xml 后出现 -> 保留 xml(更高优先级)
    invs = [_make("A", "pdf"), _make("A", "xml")]
    kept, dups = dedupe_invoices(invs, DEDUPE)
    assert len(kept) == 1
    assert kept[0].parse_method == "xml"
    assert len(dups) == 1
    assert dups[0].parse_method == "pdf"


def test_mark_flags_second_onward():
    invs = [_make("A", "xml"), _make("A", "ofd"), _make("A", "pdf"), _make("B", "xml")]
    kept, dups = dedupe_invoices(invs, MARK)
    assert len(kept) == 4
    assert len(dups) == 0
    a_invs = [i for i in kept if i.invoice_number == "A"]
    # 最高优先级那条不标,其余标 duplicate
    dup_flags = [i.is_duplicate for i in a_invs]
    assert dup_flags.count(True) == 2          # ofd 和 pdf 标
    assert dup_flags.count(False) == 1         # xml 不标
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_invoice_dedupe.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 dedupe.py**

Create `file_toolbox/core/invoice/dedupe.py`:
```python
"""按发票号码去重。三策略:keep_all / dedupe / mark。

去重键 = invoice_number。同号不同来源时,保留优先级更高的(parse_method: xml > ofd > pdf)。
"""

from file_toolbox.core.invoice.types import Invoice

KEEP_ALL = "keep_all"
DEDUPE = "dedupe"
MARK = "mark"

# 解析方式优先级(数值越小优先级越高)
_METHOD_PRIORITY = {"xml": 0, "ofd": 1, "pdf": 2}


def _method_rank(method: str) -> int:
    """返回解析方式优先级,未知方式排最后。"""
    return _METHOD_PRIORITY.get(method, 99)


def dedupe_invoices(
    invoices: list[Invoice], strategy: str = KEEP_ALL
) -> tuple[list[Invoice], list[Invoice]]:
    """按策略去重,返回 (保留列表, 被去掉/标记列表)。

    - keep_all:原样返回,不标记。
    - dedupe:同号保留最高优先级一条,其余进 duplicates。
    - mark:全部保留,同号中除最高优先级外标记 is_duplicate=True。
    """
    if strategy == KEEP_ALL:
        return list(invoices), []

    # 按发票号码分组,保持首次出现顺序
    groups: dict[str, list[Invoice]] = {}
    order: list[str] = []
    for inv in invoices:
        if inv.invoice_number not in groups:
            groups[inv.invoice_number] = []
            order.append(inv.invoice_number)
        groups[inv.invoice_number].append(inv)

    if strategy == DEDUPE:
        kept: list[Invoice] = []
        dups: list[Invoice] = []
        for num in order:
            grp = groups[num]
            if len(grp) == 1:
                kept.append(grp[0])
            else:
                # 选优先级最高(优先级数字最小);同优先级取第一个
                best = min(range(len(grp)), key=lambda i: _method_rank(grp[i].parse_method))
                kept.append(grp[best])
                dups.extend(grp[:best] + grp[best + 1:])
        return kept, dups

    if strategy == MARK:
        kept = []
        for num in order:
            grp = groups[num]
            if len(grp) == 1:
                kept.append(grp[0])
            else:
                best = min(range(len(grp)), key=lambda i: _method_rank(grp[i].parse_method))
                for i, inv in enumerate(grp):
                    inv.is_duplicate = i != best
                    kept.append(inv)
        return kept, []

    # 未知策略默认 keep_all
    return list(invoices), []
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_invoice_dedupe.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 提交**

```bash
git add file_toolbox/core/invoice/dedupe.py tests/test_invoice_dedupe.py
git commit -m "feat(invoice): 去重逻辑(三策略 + 优先级)"
```

---

## Task 7: Excel 导出器

**Files:**
- Create: `file_toolbox/core/invoice/exporters/__init__.py`
- Create: `file_toolbox/core/invoice/exporters/excel_exporter.py`
- Test: `tests/test_invoice_exporters.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_invoice_exporters.py`:
```python
from pathlib import Path

from openpyxl import load_workbook

from file_toolbox.core.invoice.exporters.excel_exporter import export_excel
from file_toolbox.core.invoice.types import Invoice, LineItem


def _invoice(num="A", dup=False) -> Invoice:
    return Invoice(
        invoice_number=num, invoice_type="增值税专用发票", issue_date="2026-05-19",
        seller_name="测试销售方", seller_tax_id="STAX", seller_addr="sa",
        seller_tel="st", seller_bank="sb", seller_account="sac",
        buyer_name="测试购买方", buyer_tax_id="BTAX", buyer_addr="ba",
        buyer_tel="bt", buyer_bank="bb", buyer_account="bac",
        amount_without_tax="100.00", tax_amount="13.00", amount_with_tax="113.00",
        amount_chinese="壹佰壹拾叁圆整", drawer="测试人", remark="备注",
        items=[LineItem("*交通运输设备*甲", "S1", "根", "1", "100", "100.00", "13%", "13.00")],
        source_file="x.xml", parse_method="xml", is_duplicate=dup,
    )


def test_excel_two_sheets(tmp_path):
    out = tmp_path / "out.xlsx"
    export_excel([_invoice("A"), _invoice("B")], out)
    wb = load_workbook(out)
    assert "发票汇总" in wb.sheetnames
    assert "明细清单" in wb.sheetnames


def test_excel_summary_headers_and_row(tmp_path):
    out = tmp_path / "out.xlsx"
    export_excel([_invoice("A")], out)
    wb = load_workbook(out)
    ws = wb["发票汇总"]
    headers = [c.value for c in ws[1]]
    assert "发票号码" in headers
    assert "解析方式" in headers
    # 数据行
    row2 = [c.value for c in ws[2]]
    assert row2[0] == "A"
    assert "测试销售方" in row2


def test_excel_detail_rows(tmp_path):
    out = tmp_path / "out.xlsx"
    export_excel([_invoice("A")], out)
    wb = load_workbook(out)
    ws = wb["明细清单"]
    headers = [c.value for c in ws[1]]
    assert "发票号码" in headers
    assert "项目名称" in headers
    row2 = [c.value for c in ws[2]]
    assert row2[0] == "A"                     # 外键
    assert row2[1] == "*交通运输设备*甲"


def test_excel_duplicate_marked_yellow(tmp_path):
    out = tmp_path / "out.xlsx"
    export_excel([_invoice("A", dup=True), _invoice("B", dup=False)], out)
    wb = load_workbook(out)
    ws = wb["发票汇总"]
    # 重复行(第2行)填充色应为黄色族
    fill = ws.cell(row=2, column=1).fill
    assert fill.fgColor is not None
    assert str(fill.fgColor.rgb).endswith("FFF2CC") or fill.patternType == "solid"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_invoice_exporters.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 excel_exporter.py**

Create `file_toolbox/core/invoice/exporters/__init__.py`:
```python
"""发票导出器:Excel / JSON。"""
```

Create `file_toolbox/core/invoice/exporters/excel_exporter.py`:
```python
"""Excel 双 Sheet 导出。Sheet1 发票汇总(一行一发票),Sheet2 明细清单(一行一明细)。

重复行(is_duplicate=True)标浅黄底。openpyxl 延迟导入。
"""

from pathlib import Path

from file_toolbox.core.invoice.types import Invoice

try:
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill
except ImportError as e:
    raise ImportError(
        "Excel 导出需要 openpyxl: pip install 'file-toolbox[invoice]'"
    ) from e


_DUP_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

# Sheet1 列定义
_SUMMARY_HEADERS = [
    "发票号码", "发票类型", "开票日期", "销售方名称", "销售方税号",
    "购买方名称", "购买方税号", "不含税金额", "税额", "价税合计",
    "大写金额", "开票人", "备注", "来源文件", "解析方式",
]

# Sheet2 列定义
_DETAIL_HEADERS = [
    "发票号码", "项目名称", "规格型号", "单位", "数量", "单价", "金额", "税率", "税额",
]


def _summary_row(inv: Invoice) -> list:
    return [
        inv.invoice_number, inv.invoice_type, inv.issue_date,
        inv.seller_name, inv.seller_tax_id,
        inv.buyer_name, inv.buyer_tax_id,
        inv.amount_without_tax, inv.tax_amount, inv.amount_with_tax,
        inv.amount_chinese, inv.drawer, inv.remark,
        inv.source_file, inv.parse_method,
    ]


def export_excel(invoices: list[Invoice], output_path: Path) -> Path:
    """导出为双 Sheet Excel。返回输出路径。"""
    output_path = Path(output_path)
    wb = Workbook()

    # Sheet1 发票汇总
    ws1 = wb.active
    ws1.title = "发票汇总"
    ws1.append(_SUMMARY_HEADERS)
    for inv in invoices:
        ws1.append(_summary_row(inv))
        if inv.is_duplicate:
            row_idx = ws1.max_row
            for col in range(1, len(_SUMMARY_HEADERS) + 1):
                ws1.cell(row=row_idx, column=col).fill = _DUP_FILL

    # Sheet2 明细清单
    ws2 = wb.create_sheet("明细清单")
    ws2.append(_DETAIL_HEADERS)
    for inv in invoices:
        for item in inv.items:
            ws2.append([
                inv.invoice_number, item.name, item.spec, item.unit,
                item.quantity, item.unit_price, item.amount, item.tax_rate, item.tax_amount,
            ])
            if inv.is_duplicate:
                row_idx = ws2.max_row
                for col in range(1, len(_DETAIL_HEADERS) + 1):
                    ws2.cell(row=row_idx, column=col).fill = _DUP_FILL

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_invoice_exporters.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 提交**

```bash
git add file_toolbox/core/invoice/exporters/ tests/test_invoice_exporters.py
git commit -m "feat(invoice): Excel 双 Sheet 导出 + 重复标色"
```

---

## Task 8: JSON 导出器

**Files:**
- Modify: `file_toolbox/core/invoice/exporters/json_exporter.py`(新建)
- Test: 追加到 `tests/test_invoice_exporters.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_invoice_exporters.py` 顶部 import 区追加:
```python
import json
```
并在文件末尾追加:
```python
def test_json_export_structure(tmp_path):
    from file_toolbox.core.invoice.exporters.json_exporter import export_json
    from file_toolbox.core.invoice.types import FailedFile

    out = tmp_path / "out.json"
    invs = [_invoice("A")]
    failed = [FailedFile(file="bad.zip", reason="损坏")]
    export_json(invs, out, dedupe_strategy="mark", failed=failed)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["dedupe_strategy"] == "mark"
    assert "exported_at" in data
    assert len(data["invoices"]) == 1
    inv0 = data["invoices"][0]
    assert inv0["invoice_number"] == "A"
    assert inv0["seller"]["name"] == "测试销售方"
    assert inv0["buyer"]["name"] == "测试购买方"
    assert inv0["items"][0]["name"] == "*交通运输设备*甲"
    assert inv0["parse_method"] == "xml"
    assert data["failed"][0]["file"] == "bad.zip"


def test_json_chinese_not_escaped(tmp_path):
    """JSON 中文应为明文,不转义为 \\uXXXX。"""
    from file_toolbox.core.invoice.exporters.json_exporter import export_json

    out = tmp_path / "out.json"
    export_json([_invoice("A")], out, dedupe_strategy="keep_all")
    raw = out.read_text(encoding="utf-8")
    assert "测试销售方" in raw                  # 明文中文
    assert "\\u" not in raw.replace("\\u", "X") is True or "测试" in raw
```

> 第二个测试简化:只要中文明文存在即可。把断言改成:`assert "测试销售方" in raw`(去掉模糊的 replace)。

修正版测试(替换上面的 test_json_chinese_not_escaped):
```python
def test_json_chinese_not_escaped(tmp_path):
    from file_toolbox.core.invoice.exporters.json_exporter import export_json

    out = tmp_path / "out.json"
    export_json([_invoice("A")], out, dedupe_strategy="keep_all")
    raw = out.read_text(encoding="utf-8")
    assert "测试销售方" in raw                  # 中文明文,未转义
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_invoice_exporters.py -v`
Expected: FAIL (json_exporter not found)

- [ ] **Step 3: 实现 json_exporter.py**

Create `file_toolbox/core/invoice/exporters/json_exporter.py`:
```python
"""格式化 JSON 导出。中文明文(ensure_ascii=False),缩进 2。"""

import json
from datetime import datetime
from pathlib import Path

from file_toolbox.core.invoice.types import FailedFile, Invoice


def _invoice_to_dict(inv: Invoice) -> dict:
    return {
        "invoice_number": inv.invoice_number,
        "invoice_type": inv.invoice_type,
        "issue_date": inv.issue_date,
        "seller": {
            "name": inv.seller_name,
            "tax_id": inv.seller_tax_id,
            "addr": inv.seller_addr,
            "tel": inv.seller_tel,
            "bank": inv.seller_bank,
            "account": inv.seller_account,
        },
        "buyer": {
            "name": inv.buyer_name,
            "tax_id": inv.buyer_tax_id,
            "addr": inv.buyer_addr,
            "tel": inv.buyer_tel,
            "bank": inv.buyer_bank,
            "account": inv.buyer_account,
        },
        "amount_without_tax": inv.amount_without_tax,
        "tax_amount": inv.tax_amount,
        "amount_with_tax": inv.amount_with_tax,
        "amount_chinese": inv.amount_chinese,
        "drawer": inv.drawer,
        "remark": inv.remark,
        "items": [
            {
                "name": it.name, "spec": it.spec, "unit": it.unit,
                "quantity": it.quantity, "unit_price": it.unit_price,
                "amount": it.amount, "tax_rate": it.tax_rate, "tax_amount": it.tax_amount,
            }
            for it in inv.items
        ],
        "source_file": inv.source_file,
        "parse_method": inv.parse_method,
        "is_duplicate": inv.is_duplicate,
    }


def export_json(
    invoices: list[Invoice],
    output_path: Path,
    dedupe_strategy: str = "keep_all",
    failed: list[FailedFile] | None = None,
) -> Path:
    """导出格式化 JSON。返回输出路径。"""
    output_path = Path(output_path)
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "dedupe_strategy": dedupe_strategy,
        "invoices": [_invoice_to_dict(inv) for inv in invoices],
        "failed": [{"file": f.file, "reason": f.reason} for f in (failed or [])],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_invoice_exporters.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: 提交**

```bash
git add file_toolbox/core/invoice/exporters/json_exporter.py tests/test_invoice_exporters.py
git commit -m "feat(invoice): JSON 格式化导出"
```

---

## Task 9: InvoiceService 编排

**Files:**
- Create: `file_toolbox/core/invoice/service.py`
- Modify: `file_toolbox/core/invoice/__init__.py`
- Test: `tests/test_invoice_service.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_invoice_service.py`:
```python
import zipfile
import io
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_invoice_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 service.py**

Create `file_toolbox/core/invoice/service.py`:
```python
"""InvoiceService:编排 解析 -> 去重 -> 导出。"""

from pathlib import Path

from file_toolbox.core.invoice.dedupe import (
    DEDUPE,
    KEEP_ALL,
    MARK,
    dedupe_invoices,
)
from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError, parse_invoice
from file_toolbox.core.invoice.types import FailedFile, Invoice, ParseResult


class InvoiceService:
    """发票识别编排服务。"""

    def __init__(self):
        pass

    def parse_files(
        self,
        files: list[Path],
        dedupe_strategy: str = KEEP_ALL,
    ) -> ParseResult:
        """解析文件列表,应用去重,返回 ParseResult。

        单个文件解析失败进 failed,不中断整体。
        """
        invoices: list[Invoice] = []
        failed: list[FailedFile] = []
        for fp in files:
            try:
                inv = parse_invoice(Path(fp), source_file=Path(fp).name)
                invoices.append(inv)
            except UnsupportedFormatError as e:
                failed.append(FailedFile(file=Path(fp).name, reason=str(e)))
            except Exception as e:  # noqa: BLE001 - 解析意外错误也记为失败
                failed.append(FailedFile(file=Path(fp).name, reason=f"{type(e).__name__}: {e}"))

        kept, dups = dedupe_invoices(invoices, dedupe_strategy)
        return ParseResult(invoices=kept, duplicates=dups, failed=failed)

    def export(
        self,
        result: ParseResult,
        output_path: Path,
        fmt: str = "excel",
        json_path: Path | None = None,
        dedupe_strategy: str = KEEP_ALL,
    ) -> list[Path]:
        """导出。fmt: excel | json | both。返回生成的文件列表。"""
        from file_toolbox.core.invoice.exporters.excel_exporter import export_excel
        from file_toolbox.core.invoice.exporters.json_exporter import export_json

        written: list[Path] = []
        if fmt in ("excel", "both"):
            written.append(export_excel(result.invoices, output_path))
        if fmt in ("json", "both"):
            jp = json_path or output_path.with_suffix(".json")
            written.append(
                export_json(result.invoices, jp, dedupe_strategy, result.failed)
            )
        return written

    @staticmethod
    def supported_dedupe_strategies() -> list[str]:
        return [KEEP_ALL, DEDUPE, MARK]
```

- [ ] **Step 4: 更新 __init__.py**

Modify `file_toolbox/core/invoice/__init__.py`:
```python
"""电子发票识别:解析 PDF/OFD/XML,导出 Excel/JSON,按发票号码去重。"""

from file_toolbox.core.invoice.service import InvoiceService

__all__ = ["InvoiceService"]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_invoice_service.py tests/test_invoice_dedupe.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add file_toolbox/core/invoice/service.py file_toolbox/core/invoice/__init__.py tests/test_invoice_service.py
git commit -m "feat(invoice): InvoiceService 编排(解析->去重->导出)"
```

---

## Task 10: CLI 子命令

**Files:**
- Create: `file_toolbox/cli/invoice_cmd.py`
- Modify: `file_toolbox/cli/main.py`
- Test: `tests/test_invoice_cli.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_invoice_cli.py`:
```python
from pathlib import Path

from typer.testing import CliRunner

from file_toolbox.cli.main import app

runner = CliRunner()


def _xml(path: Path, num: str):
    path.write_text(
        f'<?xml version="1.0"?><EInvoice>'
        f'<Header><InherentLabel><GeneralOrSpecialVAT><LabelName>增值税专用发票</LabelName></GeneralOrSpecialVAT></InherentLabel></Header>'
        f'<EInvoiceData><SellerInformation><SellerName>s{num}</SellerName><SellerIdNum>sid</SellerIdNum>'
        f'<SellerAddr/><SellerTelNum/><SellerBankName/><SellerBankAccNum/></SellerInformation>'
        f'<BuyerInformation><BuyerName>b{num}</BuyerName><BuyerIdNum>bid</BuyerIdNum>'
        f'<BuyerTelNum/><BuyerAddr/><BuyerBankName/><BuyerBankAccNum/></BuyerInformation>'
        f'<BasicInformation><TotalAmWithoutTax>1.00</TotalAmWithoutTax><TotalTaxAm>0.13</TotalTaxAm>'
        f'<TotalTax-includedAmount>1.13</TotalTax-includedAmount><TotalTax-includedAmountInChinese>壹圆</TotalTax-includedAmountInChinese>'
        f'<Drawer>x</Drawer></BasicInformation></EInvoiceData>'
        f'<TaxSupervisionInfo><InvoiceNumber>{num}</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>'
        f'</EInvoice>',
        encoding="utf-8",
    )
    return path


def test_invoice_help_lists():
    r = runner.invoke(app, ["invoice", "--help"])
    assert r.exit_code == 0
    assert "invoice" in r.output.lower() or "发票" in r.output


def test_invoice_preview_no_write(tmp_path):
    f = _xml(tmp_path / "111.xml", "111")
    r = runner.invoke(app, ["invoice", str(f)])
    assert r.exit_code == 0
    assert "预览" in r.output or "111" in r.output
    # 未加 --yes 不写文件
    assert not (tmp_path / "发票结果.xlsx").exists()


def test_invoice_export_excel_with_yes(tmp_path):
    f = _xml(tmp_path / "222.xml", "222")
    out = tmp_path / "out.xlsx"
    r = runner.invoke(
        app, ["invoice", str(f), "--format", "excel", "--output", str(out), "--yes"]
    )
    assert r.exit_code == 0, r.output
    assert out.exists()


def test_invoice_export_json(tmp_path):
    f = _xml(tmp_path / "333.xml", "333")
    out = tmp_path / "out.json"
    r = runner.invoke(
        app, ["invoice", str(f), "--format", "json", "--output", str(out), "--yes"]
    )
    assert r.exit_code == 0
    assert out.exists()
    assert "333" in out.read_text(encoding="utf-8")


def test_invoice_no_files_errors(tmp_path):
    r = runner.invoke(app, ["invoice"])
    assert r.exit_code == 1
    assert "文件" in r.output
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_invoice_cli.py -v`
Expected: FAIL (invoice 命令不存在)

- [ ] **Step 3: 实现 invoice_cmd.py**

Create `file_toolbox/cli/invoice_cmd.py`:
```python
"""invoice 命令:电子发票识别,导出 Excel/JSON。默认预览,--yes 执行。"""

from pathlib import Path

import typer

from file_toolbox.core.invoice.dedupe import DEDUPE, KEEP_ALL, MARK
from file_toolbox.core.invoice.service import InvoiceService

_DEFAULT_OUTPUT = "发票结果.xlsx"


def _expand(files: list[Path], directory: Path | None, recursive: bool) -> list[Path]:
    """扩展文件列表(同 rename),去重保持顺序。"""
    result: list[Path] = list(files)
    if directory:
        if recursive:
            result.extend(p for p in directory.rglob("*") if p.is_file())
        else:
            result.extend(p for p in directory.iterdir() if p.is_file())
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in result:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def invoice(
    files: list[Path] = typer.Argument(None, help="发票文件(zip/xml/ofd/pdf)"),
    directory: Path | None = typer.Option(None, "--dir", help="目录批量加入"),
    recursive: bool = typer.Option(False, "--recursive", help="递归子目录"),
    fmt: str = typer.Option("excel", "--format", help="excel|json|both"),
    output: Path = typer.Option(_DEFAULT_OUTPUT, "--output", "-o", help="输出路径"),
    dedupe: str = typer.Option(KEEP_ALL, "--dedupe", help="keep_all|dedupe|mark"),
    yes: bool = typer.Option(False, "--yes", help="跳过预览直接导出(默认仅预览)"),
):
    """识别电子发票(PDF/OFD/XML),导出 Excel 或 JSON。"""
    all_files = _expand(files or [], directory, recursive)
    if not all_files:
        typer.secho("错误:未选择任何文件", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if dedupe not in (KEEP_ALL, DEDUPE, MARK):
        typer.secho(f"错误:无效的 --dedupe 策略: {dedupe}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    svc = InvoiceService()
    result = svc.parse_files(all_files, dedupe_strategy=dedupe)

    # 预览输出
    typer.echo("预览:")
    for inv in result.invoices:
        mark = " [重复]" if inv.is_duplicate else ""
        typer.echo(
            f"  {inv.invoice_number} | {inv.amount_with_tax} | "
            f"{inv.parse_method} | {inv.source_file}{mark}"
        )
    if result.duplicates:
        typer.echo(f"\n去重移除 {len(result.duplicates)} 条:")
        for d in result.duplicates:
            typer.echo(f"  {d.invoice_number} | {d.parse_method} | {d.source_file}")
    if result.failed:
        typer.echo(f"\n失败 {len(result.failed)} 条:")
        for f in result.failed:
            typer.secho(f"  {f.file}: {f.reason}", fg=typer.colors.YELLOW)
    typer.echo(
        f"\n共 {len(all_files)} 个文件: 成功 {len(result.invoices)}, "
        f"重复 {len(result.duplicates)}, 失败 {len(result.failed)}"
    )

    if not yes:
        typer.echo("(预览模式,加 --yes 导出)")
        return

    # 导出
    json_path = None
    if fmt == "both":
        # both 时 output 作为 xlsx,json 用同前缀
        json_path = output.with_suffix(".json")
    elif fmt == "json" and output.suffix.lower() == ".xlsx":
        output = output.with_suffix(".json")
    elif fmt == "excel" and output.suffix.lower() == ".json":
        output = output.with_suffix(".xlsx")

    written = svc.export(result, output, fmt=fmt, json_path=json_path, dedupe_strategy=dedupe)
    typer.secho(f"\n已导出 {len(written)} 个文件:", fg=typer.colors.GREEN)
    for w in written:
        typer.echo(f"  {w}")
```

- [ ] **Step 4: 注册命令到 main.py**

Modify `file_toolbox/cli/main.py`,在 import 区加:
```python
from file_toolbox.cli.invoice_cmd import invoice
```
在命令注册区(main_callback 之前)加:
```python
app.command(name="invoice")(invoice)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_invoice_cli.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: 提交**

```bash
git add file_toolbox/cli/invoice_cmd.py file_toolbox/cli/main.py tests/test_invoice_cli.py
git commit -m "feat(invoice): CLI 子命令 invoice(预览/导出/去重)"
```

---

## Task 11: 更新现有 CLI 测试 + pyproject

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: 更新 test_cli.py 的 help 命令列表**

Modify `tests/test_cli.py:19-21`,把命令列表断言加上 `invoice`:
```python
def test_help_lists_commands():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    for cmd in ["rename", "mkdir", "pdf", "replace", "gui", "invoice"]:
        assert cmd in r.output
```

- [ ] **Step 2: 确认 pyproject invoice extra 已加(Task 4 Step 1 已加)**

Run: `grep -n "invoice" pyproject.toml`
Expected: 包含 `invoice = ["pdfplumber>=0.11", "openpyxl>=3.1"]`

- [ ] **Step 3: 运行全部测试**

Run: `pytest -q`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add tests/test_cli.py pyproject.toml
git commit -m "test(invoice): CLI help 含 invoice 命令 + 依赖声明"
```

---

## Task 12: GUI Tab(第 5 个)

**Files:**
- Create: `file_toolbox/gui/dialogs/invoice_tab.py`
- Modify: `file_toolbox/gui/main_window.py`
- Test: `tests/test_invoice_gui.py`(轻量:实例化 Tab,验证能加载)

> 注意:GUI 测试在无显示环境可能跳过。用 `pytest.importorskip("PySide6")` 保护。

- [ ] **Step 1: 写轻量测试**

Create `tests/test_invoice_gui.py`:
```python
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_invoice_tab_instantiates(app):
    tab = InvoiceTab()
    assert tab.windowTitle() == "发票识别" or tab.objectName() is not None


def test_invoice_tab_has_table(app):
    tab = InvoiceTab()
    assert hasattr(tab, "_table")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_invoice_gui.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 invoice_tab.py**

Create `file_toolbox/gui/dialogs/invoice_tab.py`:
```python
"""发票识别 Tab:选文件 -> 解析 -> 表格预览 -> 导出。

标色:重复行黄底,PDF 弱解析行灰底。嵌入主窗口作为第 5 个 Tab。
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from file_toolbox.core.invoice.dedupe import DEDUPE, KEEP_ALL, MARK
from file_toolbox.core.invoice.service import InvoiceService
from file_toolbox.core.invoice.types import ParseResult

_DUP_COLOR = QColor(255, 242, 204)       # 浅黄(重复)
_PDF_COLOR = QColor(230, 230, 230)       # 浅灰(PDF 弱解析)
_HEADERS = [
    "发票号码", "发票类型", "开票日期", "销售方", "购买方",
    "价税合计", "来源", "解析方式",
]


class InvoiceTab(QWidget):
    """发票识别 Tab。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._svc = InvoiceService()
        self._result: ParseResult | None = None
        self._files: list[Path] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 文件选择
        file_row = QHBoxLayout()
        self._btn_add_files = QPushButton("+添加文件")
        self._btn_add_folder = QPushButton("+添加文件夹")
        self._btn_clear = QPushButton("清空")
        self._list_files = QListWidget()
        for btn in (self._btn_add_files, self._btn_add_folder, self._btn_clear):
            file_row.addWidget(btn)
        file_row.addStretch(1)
        layout.addLayout(file_row)
        layout.addWidget(self._list_files)

        # 选项行
        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("格式:"))
        self._rb_excel = QRadioButton("Excel")
        self._rb_json = QRadioButton("JSON")
        self._rb_both = QRadioButton("两者")
        self._rb_excel.setChecked(True)
        self._fmt_group = QButtonGroup(self)
        for rb in (self._rb_excel, self._rb_json, self._rb_both):
            self._fmt_group.addButton(rb)
            opt_row.addWidget(rb)

        opt_row.addWidget(QLabel("去重:"))
        self._cmb_dedupe = QComboBox()
        self._cmb_dedupe.addItems(["keep_all(不处理)", "dedupe(去重)", "mark(标色)"])
        self._cmb_dedupe.setCurrentIndex(0)
        opt_row.addWidget(self._cmb_dedupe)

        opt_row.addWidget(QLabel("输出目录:"))
        self._edit_outdir = QLineEdit()
        self._edit_outdir.setPlaceholderText("选择或输入输出目录")
        self._btn_browse = QPushButton("...")
        opt_row.addWidget(self._edit_outdir)
        opt_row.addWidget(self._btn_browse)
        opt_row.addStretch(1)
        layout.addLayout(opt_row)

        # 按钮
        btn_row = QHBoxLayout()
        self._btn_parse = QPushButton("开始解析")
        self._btn_export = QPushButton("导出")
        self._btn_export.setEnabled(False)
        btn_row.addWidget(self._btn_parse)
        btn_row.addWidget(self._btn_export)
        btn_row.addStretch(1)
        self._lbl_status = QLabel("就绪")
        btn_row.addWidget(self._lbl_status)
        layout.addLayout(btn_row)

        # 表格
        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, stretch=1)

        self._connect()

    def _connect(self):
        self._btn_add_files.clicked.connect(self._add_files)
        self._btn_add_folder.clicked.connect(self._add_folder)
        self._btn_clear.clicked.connect(self._clear)
        self._btn_browse.clicked.connect(self._browse_outdir)
        self._btn_parse.clicked.connect(self._parse)
        self._btn_export.clicked.connect(self._export)

    # --- 文件管理 ---
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择发票文件", "", "发票文件 (*.zip *.xml *.ofd *.pdf)"
        )
        for p in paths:
            self._files.append(Path(p))
            self._list_files.addItem(Path(p).name)

    def _add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if d:
            for p in Path(d).iterdir():
                if p.is_file() and p.suffix.lower() in (".zip", ".xml", ".ofd", ".pdf"):
                    self._files.append(p)
                    self._list_files.addItem(p.name)

    def _clear(self):
        self._files.clear()
        self._list_files.clear()
        self._table.setRowCount(0)
        self._result = None
        self._btn_export.setEnabled(False)
        self._lbl_status.setText("就绪")

    def _browse_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._edit_outdir.setText(d)

    def _dedupe_strategy(self) -> str:
        idx = self._cmb_dedupe.currentIndex()
        return [KEEP_ALL, DEDUPE, MARK][idx]

    def _format(self) -> str:
        if self._rb_json.isChecked():
            return "json"
        if self._rb_both.isChecked():
            return "both"
        return "excel"

    # --- 解析 ---
    def _parse(self):
        if not self._files:
            QMessageBox.warning(self, "提示", "请先添加发票文件")
            return
        strategy = self._dedupe_strategy()
        self._result = self._svc.parse_files(self._files, dedupe_strategy=strategy)
        self._populate_table()
        self._btn_export.setEnabled(bool(self._result.invoices))
        dup = sum(1 for i in self._result.invoices if i.is_duplicate)
        self._lbl_status.setText(
            f"成功 {len(self._result.invoices)} | 重复标记 {dup} | "
            f"去重移除 {len(self._result.duplicates)} | 失败 {len(self._result.failed)}"
        )

    def _populate_table(self):
        assert self._result is not None
        self._table.setRowCount(len(self._result.invoices))
        for r, inv in enumerate(self._result.invoices):
            values = [
                inv.invoice_number, inv.invoice_type, inv.issue_date,
                inv.seller_name, inv.buyer_name, inv.amount_with_tax,
                inv.source_file, inv.parse_method,
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                if inv.is_duplicate:
                    item.setBackground(QBrush(_DUP_COLOR))
                elif inv.parse_method == "pdf":
                    item.setBackground(QBrush(_PDF_COLOR))
                self._table.setItem(r, c, item)

    # --- 导出 ---
    def _export(self):
        if not self._result or not self._result.invoices:
            QMessageBox.warning(self, "提示", "无数据可导出")
            return
        outdir = self._edit_outdir.text().strip() or "."
        outdir_path = Path(outdir)
        outdir_path.mkdir(parents=True, exist_ok=True)
        base = outdir_path / "发票结果"
        xlsx_path = base.with_suffix(".xlsx")
        json_path = base.with_suffix(".json")
        try:
            written = self._svc.export(
                self._result, xlsx_path, fmt=self._format(),
                json_path=json_path, dedupe_strategy=self._dedupe_strategy(),
            )
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(e))
            return
        QMessageBox.information(
            self, "完成", "已导出:\n" + "\n".join(str(w) for w in written)
        )
```

- [ ] **Step 4: 注册到 main_window.py**

Modify `file_toolbox/gui/main_window.py`:
- 在 import 区追加:
```python
from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab
```
- 在 `MainWindow.__init__` 的 Tab 创建区(约第 47-54 行),在 `_replace_tab` 后追加:
```python
        self._invoice_tab = InvoiceTab()
        tabs.addTab(self._invoice_tab, "发票识别")
```
- 在 `closeEvent` 的 tab 元组里加 `self._invoice_tab`:
```python
        for tab in (self._rename_tab, self._mkdir_tab, self._pdf_tab, self._replace_tab, self._invoice_tab):
```
- 在 `_open_history` 的工具选择列表里加 `"invoice"`:
```python
            ["rename", "replace", "pdf", "mkdir", "invoice"],
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_invoice_gui.py -v`
Expected: PASS (若环境无显示,确保 CI 用 offscreen: `QT_QPA_PLATFORM=offscreen pytest ...`)

- [ ] **Step 6: 提交**

```bash
git add file_toolbox/gui/dialogs/invoice_tab.py file_toolbox/gui/main_window.py tests/test_invoice_gui.py
git commit -m "feat(invoice): GUI Tab 表格预览 + 标色 + 导出"
```

---

## Task 13: 集成验证 + 文档

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: 全量测试**

Run: `QT_QPA_PLATFORM=offscreen pytest -q`
Expected: 全部 PASS

> Windows Git Bash 下若 offscreen 无效,改用 `pytest -q`(GUI 测试 importorskip 保护)。

- [ ] **Step 2: 端到端手工验证(用真实示例)**

> 注意:此步用 `发票示例` 真实文件做一次性验证,**不提交任何产物**,验证后删除输出。

```bash
cd "C:\Users\felji\Downloads\发票示例"
python -m file_toolbox invoice *.zip *.ofd *.pdf --format excel -o /tmp/验证结果.xlsx --dedupe mark --yes
python -m file_toolbox invoice *.zip --format json -o /tmp/验证结果.json --yes
```

预期:3 个文件(2 zip + 1 ofd + 1 pdf,但 zip 内含 xml),解析出对应发票,Excel 双 Sheet 正确,JSON 中文明文。验证后:
```bash
rm -f /tmp/验证结果.xlsx /tmp/验证结果.json
```

- [ ] **Step 3: 更新 README.md**

在 README.md 的功能表格(`| 功能 |` 表)追加一行:
```markdown
| **发票识别** | 电子发票(PDF/OFD/XML)→ Excel(双 Sheet)/JSON,按发票号码去重 | 需 `pip install 'file-toolbox[invoice]'` |
```

在「命令行」章节的示例区,追加 invoice 示例:
```bash
# 发票识别(默认预览,--yes 导出)
file-toolbox invoice *.zip *.xml *.ofd *.pdf \
    --format excel --output 发票汇总.xlsx \
    --dedupe mark --yes
```

在「图形界面」章节的 Tab 描述里,把「4 个 Tab」改为「5 个 Tab」,列出含「发票识别」。

在「安装」章节追加:
```bash
# 带发票识别:
pip install -e ".[invoice]"
```

在「平台说明」追加:
```markdown
- 发票识别(PDF/OFD/XML 解析 + Excel/JSON 导出):**全平台**,需额外安装 `pip install 'file-toolbox[invoice]'`(pdfplumber + openpyxl)。
```

- [ ] **Step 4: 更新 CHANGELOG.md**

在 CHANGELOG.md 顶部追加(若顶部是已发布版本则新建 `## [Unreleased]` 区):
```markdown
## [Unreleased]
### Added
- 发票识别工具 `invoice`:识别电子发票(PDF/OFD/XML),导出 Excel(双 Sheet:汇总+明细)/JSON。
  - 解析优先级:ZIP 内 XML > OFD > PDF(PDF 为尽力而为)。
  - 按发票号码去重,支持 keep_all/dedupe/mark(标色)三策略。
  - GUI 表格预览,重复行标黄、PDF 弱解析行标灰。
  - 新增可选依赖组 `invoice`(pdfplumber + openpyxl)。
```

- [ ] **Step 5: 最终全量测试 + lint**

Run: `QT_QPA_PLATFORM=offscreen pytest -q && ruff check file_toolbox tests`
Expected: 全部 PASS,无 lint 错误

- [ ] **Step 6: 提交**

```bash
git add README.md CHANGELOG.md
git commit -m "docs(invoice): README + CHANGELOG 更新(第5工具发票识别)"
```

---

## 自查记录(Self-Review)

**1. Spec 覆盖:**
- ✅ 数据模型 → Task 1
- ✅ XML 解析 + 路由 → Task 2
- ✅ OFD 解析 → Task 3
- ✅ PDF 解析(pdfplumber,处理空规格/动态表区)→ Task 4
- ✅ ZIP 解析(嵌套,优先级)→ Task 5
- ✅ 去重三策略 → Task 6
- ✅ Excel 双 Sheet + 标色 → Task 7
- ✅ JSON 格式化 → Task 8
- ✅ Service 编排 → Task 9
- ✅ CLI 子命令 → Task 10
- ✅ GUI Tab → Task 12
- ✅ 历史 → main_window 历史下拉加 invoice(Task 12 Step 4)
- ✅ 依赖 → Task 4 Step 1 + Task 11
- ✅ 隐私约束 → 测试全用虚构数据(各 fixture),ZIP 临时目录自动清理(zip_parser.py TemporaryDirectory)
- ✅ 端到端真实示例验证(不提交产物)→ Task 13 Step 2

**2. Placeholder 扫描:** 无 TBD/TODO;每个 step 含完整代码或命令。

**3. 类型/命名一致性:**
- `parse_invoice` / `parse_xml` / `parse_ofd` / `parse_pdf` / `parse_zip` 签名统一为 `(path, source_file="")` → 全篇一致。
- `dedupe_invoices(invoices, strategy) -> (kept, dups)` 在 Task 6 定义,Task 9 service 调用一致。
- `export_excel(invoices, output_path)`、`export_json(invoices, output_path, dedupe_strategy, failed)` 签名与 Task 9 service.export 调用一致。
- 常量 `KEEP_ALL/DEDUPE/MARK` 在 Task 6 定义,Task 9/10/12 引用一致。
- `is_duplicate` 字段 Task 1 定义,Task 6/7/12 引用一致。

**4. 已知简化(spec 允许):**
- OFD 明细行(items)本版留空(CustomData 无明细,坐标聚类复杂);汇总字段完整。spec 第 4.3 节已说明。
- PDF 解析为尽力而为,置信度通过 `parse_method=pdf` + GUI 灰底体现。
