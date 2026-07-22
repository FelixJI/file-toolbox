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
    assert len(inv.items) == 3
    assert inv.items[0].name == "*交通运输设备*测试品甲"
    assert inv.items[0].spec == "TEST-001"
    assert inv.items[0].quantity == "2"
    assert inv.items[0].amount == "1000.00"
    assert inv.items[0].tax_rate == "13%"
    # 第二条规格为空(验证空单元格不错位)
    assert inv.items[1].name == "*交通运输设备*无规格品"
    assert inv.items[1].spec == ""
    assert inv.items[1].quantity == "3"
    # 第三条(有规格)
    assert inv.items[2].spec == "C-3"


def test_parse_pdf_totals(pdf_sample):
    inv = parse_pdf(pdf_sample, source_file="sample.pdf")
    assert inv.amount_without_tax == "1350.00"
    assert inv.tax_amount == "175.50"
    assert inv.amount_with_tax == "1525.50"


# --------------------------------------------------------------------------- #
# 动态锚点重构后的场景(模拟真实发票形态)
# --------------------------------------------------------------------------- #


def test_parse_pdf_dynamic_anchors_items(pdf_sample_realistic):
    """拆字表头 + 长单价 + 续行:动态学列锚点后全字段正确。"""
    inv = parse_pdf(pdf_sample_realistic)
    assert len(inv.items) == 1
    it = inv.items[0]
    # 名称主体 + 续行合并
    assert it.name == "*交通运输设备*补强块（L135）"
    # 规格型号独立成列(不再混入 name)
    assert it.spec == "P000002356623"
    assert it.unit == "件"
    assert it.quantity == "26"
    # 长单价用 word 中心判列,不误归数量
    assert it.unit_price == "96.2001361061947"
    assert it.amount == "2501.20"
    assert it.tax_rate == "13%"
    assert it.tax_amount == "325.16"


def test_parse_pdf_parties_by_label(pdf_sample_realistic):
    """有购/销竖排标签时,按标签 x 定位买卖方(左购右销),不依赖出现顺序。"""
    inv = parse_pdf(pdf_sample_realistic)
    # 名称:徐州中车(x0=30,左=购) / 中车南京浦镇(x0=315,右=销)
    assert inv.buyer_name == "徐州中车轨道装备有限公司"
    assert inv.seller_name == "中车南京浦镇车辆有限公司"
    # 税号裁掉"统一社会信用代码/"前缀
    assert inv.buyer_tax_id == "91BUYERTAXID00000Z"
    assert inv.seller_tax_id == "91SELLERTAXID00000X"


def test_parse_pdf_totals_split_row(pdf_sample_realistic):
    """合计行'合'+'计'拆字 + 价税合计金额跨行。"""
    inv = parse_pdf(pdf_sample_realistic)
    assert inv.amount_without_tax == "2501.20"
    assert inv.tax_amount == "325.16"
    # 价税合计金额在标签行的相邻 y 行
    assert inv.amount_with_tax == "2826.36"
    assert inv.amount_chinese == "贰仟捌佰贰拾陆圆叁角陆分"
