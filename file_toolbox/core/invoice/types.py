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
