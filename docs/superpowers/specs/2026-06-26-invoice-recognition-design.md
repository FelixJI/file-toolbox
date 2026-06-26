# 发票识别功能设计 (Invoice Recognition)

- 日期:2026-06-26
- 状态:已批准(待实现)
- 范围:为 file-toolbox 新增第 5 个工具 `invoice`,识别电子发票(PDF / OFD / XML),导出为 Excel(双 Sheet)或格式化 JSON。
- 不在范围内:扫描版发票(图片型 OCR)、纸质发票。

## 1. 背景与目标

用户从税务局下载的电子发票有三种来源,数据可靠性差异很大:

| 来源 | 内部结构 | 可靠性 |
|---|---|---|
| 完整下载 ZIP | 含 PDF + OFD + 嵌套 ZIP(内 XML) | XML 最高 |
| 裸 OFD | 本质是「XML 压缩包」,`OFD.xml` 有结构化 `<CustomData>` | ≈ XML |
| 裸 PDF | **纯版式文档,无 XML/XMP/附件**(已实测验证),只能文本+坐标还原表格 | 弱(启发式) |

目标:统一识别为结构化数据,支持去重,导出 Excel/JSON。

> **PDF 底层验证结论(实测)**:示例 PDF `embfile_count=0`、pypdf `attachments` 为空、catalog 仅有 `/Pages`+`/Type`、无 XMP、无任何 `EmbeddedFile/Filespec/xfa/EInvoice` 迹象。确认为纯版式 PDF,无结构化数据可提取,只能走文本还原。

> **解析库选型结论(实测)**:pdfplumber 的 `text` 策略对无边框表格的列对齐开箱即用,优于 PyMuPDF 的手工 y 桶聚类。发票解析采用 **pdfplumber**;项目其他模块(PDF 生成)仍用 PyMuPDF,互不影响。

## 2. 关键决策(用户确认)

| 决策点 | 选择 |
|---|---|
| 明细呈现 | Excel 双 Sheet:Sheet1 发票汇总(一行一发票),Sheet2 明细清单(一行一明细) |
| 格式覆盖 | XML 优先 + OFD + PDF 全部支持 |
| 解析优先级 | ZIP 内 XML > OFD > PDF |
| 去重键 | 发票号码(`InvoiceNumber`) |
| 去重时机 | 解析后立即去重展示 |
| 导出格式 | Excel(openpyxl)+ JSON |
| 解析失败 | 跳过 + 失败报告(文件名+原因) |
| GUI 预览 | 表格预览(QTableWidget) |

## 3. 架构与模块布局

遵循现有工具模式(`core/<service>` → `cli/<cmd>` → `gui/dialogs/<tab>`),新增第 5 个工具 `invoice`:

```
file_toolbox/
├── core/
│   └── invoice/                       # 新增
│       ├── __init__.py
│       ├── types.py                   # 数据模型(dataclass)
│       ├── service.py                 # InvoiceService: 编排 解析→去重→导出
│       ├── dedupe.py                  # 去重逻辑(按发票号码,三种策略)
│       ├── exporters/
│       │   ├── __init__.py
│       │   ├── excel_exporter.py      # openpyxl 双 Sheet + 重复标色
│       │   └── json_exporter.py       # 格式化 JSON
│       └── parsers/                   # 每种格式一个解析器,统一接口
│           ├── __init__.py
│           ├── base.py                # InvoiceParser 抽象基类 + 路由
│           ├── zip_parser.py          # 解压,优先找 XML(含嵌套 zip)
│           ├── xml_parser.py          # <EInvoice> SWEI3200 schema
│           ├── ofd_parser.py          # OFD.xml CustomData + Content.xml
│           └── pdf_parser.py          # pdfplumber text 策略 表格还原
├── cli/
│   └── invoice_cmd.py                 # 新增:invoice 子命令
└── gui/
    └── dialogs/
        └── invoice_tab.py             # 新增:第 5 个 Tab
```

### 数据模型(`core/invoice/types.py`)

```python
from dataclasses import dataclass, field

@dataclass
class LineItem:
    name: str          # 项目名称,如 "*交通运输设备*解钩软管"
    spec: str          # 规格型号,可能为空
    unit: str          # 单位,可能为空
    quantity: str      # 数量
    unit_price: str    # 单价
    amount: str        # 金额
    tax_rate: str      # 税率,如 "13%"
    tax_amount: str    # 税额

@dataclass
class Invoice:
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
    amount_without_tax: str
    tax_amount: str
    amount_with_tax: str
    amount_chinese: str          # 大写金额
    drawer: str                  # 开票人
    remark: str
    items: list[LineItem] = field(default_factory=list)
    source_file: str             # 来源文件名(溯源)
    parse_method: str            # xml | ofd | pdf(记录数据来源可靠度)
    is_duplicate: bool = False   # mark 策略下,同号第 2 条及以后置 True

@dataclass
class FailedFile:
    file: str
    reason: str

@dataclass
class ParseResult:
    invoices: list[Invoice]          # 保留的(keep_all/mark 为全部,dedupe 为去重后)
    duplicates: list[Invoice] = field(default_factory=list)  # 被去掉的(dedupe 才填充)
    failed: list[FailedFile] = field(default_factory=list)
```

## 4. 解析器设计

### 4.1 路由与优先级

单一入口 `InvoiceParser.parse(path) -> Invoice`,按扩展名路由:

| 输入扩展名 | 处理 |
|---|---|
| `.zip` | 解压 → 找 XML(**递归解嵌套 zip**)→ 若无,找 OFD → 若无,找 PDF |
| `.xml` | 直接 XML 解析 |
| `.ofd` | OFD 解析 |
| `.pdf` | PDF 解析 |
| 其他 | 抛 `UnsupportedFormatError` → 进 failed |

ZIP 内多格式并存时,**优先采信 XML**(用户明确要求)。

> **同号不同来源的优先级**:解析后若发现同一发票号出现在多个文件(如一份 zip 的 XML + 一份裸 OFD),去重时保留优先级更高的来源(xml > ofd > pdf)。

### 4.2 XML 解析器(`xml_parser.py`)

Schema 为 `<EInvoice>`(EInvoiceTag `SWEI3200`),直接读标签即可,字段映射:

| XML 标签 | Invoice 字段 |
|---|---|
| `TaxSupervisionInfo/InvoiceNumber` | invoice_number |
| `Header/InherentLabel/EInvoiceType/LabelName` | invoice_type |
| `TaxSupervisionInfo/IssueTime` | issue_date |
| `SellerInformation/SellerName` 等 6 个 | seller_* |
| `BuyerInformation/BuyerName` 等 6 个 | buyer_* |
| `BasicInformation/TotalAmWithoutTax` | amount_without_tax |
| `BasicInformation/TotalTaxAm` | tax_amount |
| `BasicInformation/TotalTax-includedAmount` | amount_with_tax |
| `BasicInformation/TotalTax-includedAmountInChinese` | amount_chinese |
| `BasicInformation/Drawer` | drawer |
| `AdditionalInformation/Remark` | remark |
| 多个 `IssuItemInformation` | items |

每个 `IssuItemInformation` → 一个 `LineItem`:
- `ItemName` → name
- `SpecMod` → spec(**可能为空,空标签 normalize 为 ""**)
- `MeaUnits` → unit
- `Quantity` → quantity
- `UnPrice` → unit_price
- `Amount` → amount
- `TaxRate` → tax_rate(如 `0.130000` → `"13%"`)
- `ComTaxAm` → tax_amount

用 `xml.etree.ElementTree` 解析。所有字段缺失时给默认空串,不报错。`parse_method="xml"`。

### 4.3 OFD 解析器(`ofd_parser.py`)

OFD 是 ZIP 包,分两层取数:

1. **`OFD.xml` 的 `<CustomData>`**(优先,结构化键值,等价 XML 源):
   - `Name="发票号码"` → invoice_number
   - `Name="销售方纳税人识别号"` → seller_tax_id
   - `Name="购买方纳税人识别号"` → buyer_tax_id
   - `Name="合计金额"` → amount_without_tax
   - `Name="合计税额"` → tax_amount
   - `Name="开票日期"` → issue_date
2. **`Doc_0/Pages/Page_0/Content.xml` 的 `<TextCode>`**(补全 CustomData 没有的字段,如买卖方名称、大写金额、明细行):
   - 按文本内容正则匹配标签后的值。
   - 明细行需按 OFD 坐标聚类(同 y 坐标的 TextCode 为一行)。

CustomData 提供的字段最可靠,Content.xml 补充。`parse_method="ofd"`。

### 4.4 PDF 解析器(`pdf_parser.py`)— 尽力而为

**已知难点(用户指出,已实测验证):**
1. **明细行数不固定 → 表格高矮不一**:不能用固定行号定位,需动态识别表头/表尾。
2. **规格等字段可能为空**:空单元格要识别成空,不能错位。
3. 跨行明细(项目名/规格换行被拆成两行)。
4. 表头列名被竖排标签污染。

**方案:** pdfplumber `text` 策略(`vertical_strategy='text'`),按对齐聚类列。

```python
table_settings = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 6,
    "min_words_vertical": 3,
    "text_tolerance": 3,
}
```

**表格识别逻辑:**
1. `extract_tables(table_settings)` 取明细表。
2. **表区定位**:找含「项目名称」的行作为表头,到含「合计」的行作为表尾,之间所有行 = 明细数据(不依赖固定行数,解决难点1)。
3. **列索引固定映射**(不依赖表头文字识别,解决难点4):
   - col0=项目名, col1=规格, col2=单位, col3=数量, col4=单价, col5=金额, col6=税率, col7=税额
4. **空单元格** → pdfplumber 返回 `None`,normalize 为 `""`(解决难点2)。
5. **合并跨行明细**(解决难点3):数据行后若紧跟「前几列有值、其余全空」的续行,合并到上一条明细(项目名续行拼到 name,规格续行拼到 spec)。

**表头/买卖方区(汇总字段)提取:** 单独用 `extract_text` + 正则,按标签匹配(如「名称:」后取值)。PDF 的汇总字段可靠度低于 OFD/XML。

**置信度标记:** `parse_method="pdf"`。GUI 表格中 PDF 来源行标灰,Excel 可在 `parse_method` 列体现,提示用户该条为弱解析结果。

### 4.5 ZIP 解析器(`zip_parser.py`)

```python
def parse(zip_path) -> Invoice:
    # 1. 解压到临时目录(tempfile + try/finally 清理,不留隐私残留)
    # 2. 递归查找 .xml(含解嵌套 zip 里的 .xml)
    #    - 找到 → xml_parser.parse,parse_method 仍记 "xml"
    # 3. 无 xml → 找 .ofd → ofd_parser.parse
    # 4. 无 ofd → 找 .pdf → pdf_parser.parse
    # 5. 都没有 → raise UnsupportedFormatError
```

临时文件用 `tempfile.TemporaryDirectory()`,解析完自动清理,**不残留隐私内容**。

## 5. 去重(`dedupe.py`)

去重键 = 发票号码。三种策略:

| 策略 | 行为 |
|---|---|
| `keep_all`(默认) | 保留所有,重复的各自独立成行 |
| `dedupe` | 同号只保留第一条(按文件输入顺序),其余进 `duplicates` 不导出 |
| `mark` | 全部保留,同号中第 2 条及以后标记 `is_duplicate=True`(导出时标色) |

去重在 `InvoiceService` 中解析后、导出前执行,产出 `ParseResult`。

**同号不同来源冲突:** 保留优先级更高的(xml > ofd > pdf)。即:若同号有一条 xml 和一条 pdf,保留 xml 那条。

## 6. 导出

### 6.1 Excel(`excel_exporter.py`,openpyxl,双 Sheet)

**Sheet1「发票汇总」** — 一行一发票(金额列为发票级,直接取自 XML `TotalAmWithoutTax`/`TotalTaxAm`/`TotalTax-includedAmount`,非明细汇总):
| 发票号码 | 发票类型 | 开票日期 | 销售方名称 | 销售方税号 | 购买方名称 | 购买方税号 | 不含税金额 | 税额 | 价税合计 | 大写金额 | 开票人 | 备注 | 来源文件 | 解析方式 |

**Sheet2「明细清单」** — 一行一明细:
| 发票号码(外键) | 项目名称 | 规格型号 | 单位 | 数量 | 单价 | 金额 | 税率 | 税额 |

**重复标色(`mark` 策略):**
- Sheet1 对应汇总行 + Sheet2 该发票所有明细行,标浅黄底(`PatternFill(start_color="FFF2CC")`)。

**PDF 弱解析提示:**
- `parse_method=pdf` 的行不强制标色,但该列值 `pdf` 本身即为提示(用户一眼可见)。

### 6.2 JSON(`json_exporter.py`,格式化)

`ensure_ascii=False`、缩进 2 空格:

```json
{
  "exported_at": "2026-06-26T10:30:00",
  "dedupe_strategy": "mark",
  "invoices": [
    {
      "invoice_number": "...",
      "invoice_type": "...",
      "issue_date": "...",
      "seller": { "name": "...", "tax_id": "...", "addr": "...", "tel": "...", "bank": "...", "account": "..." },
      "buyer": { "name": "...", "tax_id": "...", "..." : "..." },
      "amount_without_tax": "...",
      "tax_amount": "...",
      "amount_with_tax": "...",
      "amount_chinese": "...",
      "drawer": "...",
      "remark": "...",
      "items": [ { "name": "...", "spec": "...", "unit": "...", "quantity": "...", "unit_price": "...", "amount": "...", "tax_rate": "...", "tax_amount": "..." } ],
      "source_file": "...",
      "parse_method": "xml"
    }
  ],
  "failed": [ { "file": "...", "reason": "..." } ]
}
```

## 7. CLI 接口(`cli/invoice_cmd.py`)

第 5 个子命令 `invoice`,沿用 dry-run + `--yes` 惯例:

```bash
file-toolbox invoice *.zip *.xml *.ofd *.pdf \
    --format excel --output 发票汇总.xlsx \
    --dedupe mark --yes

# 目录批量 + 递归
file-toolbox invoice --dir ./发票/ --recursive --format json -o ./out/发票.json
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `files`(位置) | — | 发票文件,可多个 |
| `--dir` | — | 目录批量加入 |
| `--recursive` | False | 递归子目录 |
| `--format` | `excel` | `excel` \| `json` \| `both` |
| `--output` / `-o` | `./发票结果.xlsx`(或 `.json`) | 输出路径;`both` 时作为文件名前缀(生成 `.xlsx` + `.json`) |
| `--dedupe` | `keep_all` | `keep_all` \| `dedupe` \| `mark` |
| `--yes` | False | 默认预览(打印解析结果不写文件);加 `--yes` 才写文件 |

预览输出(不加 `--yes`)打印:成功 N 条(发票号+金额+来源+parse_method)、重复 M 条、失败 K 条(文件名+原因),不写文件。

在 `cli/main.py` 注册:`app.command(name="invoice")(invoice)`。

## 8. GUI 接口(`gui/dialogs/invoice_tab.py`)

第 5 个 Tab「发票识别」,嵌入主窗口:

```
┌─ 发票识别 ─────────────────────────────────────────────┐
│ [+添加文件] [+添加文件夹] [清空]            输出目录:[...]│
│ ┌─────────────────────────────────────────┐            │
│ │ 文件列表(zip/xml/ofd/pdf)               │            │
│ └─────────────────────────────────────────┘            │
│ [开始解析]   格式:(●Excel ○JSON ○两者)  去重:(下拉)    │
│ ┌─────────────────────────────────────────┐            │
│ │ 发票汇总表(QTableWidget)                │            │
│ │  重复行标黄;PDF弱解析行标灰              │            │
│ └─────────────────────────────────────────┘            │
│ [导出]    状态栏:成功12 重复2 失败1                    │
└────────────────────────────────────────────────────────┘
```

- **表格预览**:解析后用 `QTableWidget` 展示 Sheet1 汇总内容(发票号/日期/买卖方/金额/来源/parse_method)。
- **标色**:`mark` 策略下重复行黄底;`parse_method=pdf` 的行灰底(提示弱解析)。点击行可展开明细(或在下方第二个表格显示明细)。
- **导出**:选格式→写文件→状态栏提示路径。

在 `gui/main_window.py` 注册第 5 个 Tab;顶部「历史」按钮下拉里加 `invoice` 选项。

## 9. 历史

新增 `.file_toolbox/history/invoice.jsonl`,记录每次导出(时间、文件数、策略、输出路径),复用现有 `JsonHistoryStore`,与现有 4 工具一致。

## 10. 依赖

`pyproject.toml` 新增可选依赖组:

```toml
invoice = ["pdfplumber>=0.11", "openpyxl>=3.1"]
```

PDF/Excel 相关 import 用**延迟导入**(GUI/CLI 入口处检测,缺依赖时友好提示 `pip install 'file-toolbox[invoice]'`),避免影响其他工具。

## 11. 隐私与测试约束

- **测试 fixture 用合成数据**:测试不直接用 `发票示例` 的真实发票(含真实公司名、税号、银行账号、发票号)。使用虚构数据(如「测试销售方有限公司」、占位税号、凑整金额)构造 XML/OFD/PDF 样例。
- **不提交真实示例**:`.gitignore` 已含 `.file_toolbox/`;spec 文档代码片段只用虚构数据。
- **临时文件清理**:解析 ZIP 时用 `tempfile.TemporaryDirectory()` + try/finally,不残留。

## 12. 测试策略

| 层 | 测试内容 |
|---|---|
| 单元 - types | dataclass 构造、默认值 |
| 单元 - xml_parser | 用虚构 XML fixture,验证字段映射、空规格处理、多明细、税率归一化 |
| 单元 - ofd_parser | 用虚构 OFD fixture(最小 OFD.xml + Content.xml),验证 CustomData 优先 + Content 补充 |
| 单元 - pdf_parser | 用虚构 PDF fixture 或最小版式 PDF,验证表区定位、空单元格、跨行合并 |
| 单元 - zip_parser | 嵌套 zip 递归找 XML、优先级 |
| 单元 - dedupe | 三种策略、同号不同来源优先级 |
| 单元 - excel/json exporters | 输出结构、重复标色、JSON 格式 |
| 集成 - service | 完整流程 解析→去重→导出 |
| 集成 - CLI | 预览不写文件、`--yes` 写文件、失败报告 |

所有 fixture 文件均用虚构数据,放 `tests/fixtures/invoice/`。
