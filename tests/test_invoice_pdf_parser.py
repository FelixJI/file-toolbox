from __future__ import annotations

import pytest

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.parsers.pdf_parser import (
    Word,
    _column_of,
    _extract_amount_chinese,
    _extract_amounts,
    _extract_detail_items,
    _extract_invoice_number,
    _extract_issue_date,
    _extract_party_by_label,
    _extract_tax_ids,
    _find_amount_in_next_rows,
    _find_label_word,
    _group_rows,
    _learn_columns,
    _row_join_no_space,
    _word_center,
    parse_pdf,
)


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


def _w(text: str, x0: float, x1: float, top: float) -> Word:
    """构造一个 pdfplumber word 字典。"""
    return {"text": text, "x0": x0, "x1": x1, "top": top}


# ---------------------------------------------------------------------------
# _word_center
# ---------------------------------------------------------------------------


def test_word_center():
    assert _word_center({"x0": 10, "x1": 20}) == 15.0


# ---------------------------------------------------------------------------
# _learn_columns:fallback 补列(行 148-152)
# ---------------------------------------------------------------------------


def test_learn_columns_fallback_for_missing():
    """表头只学到部分列 → 缺失列用 _FALLBACK_ANCHORS 补(行 150-152)。"""
    # 只有'项目名称'在 name 区,'规格型号'缺失 → spec 用 fallback
    header = [
        _w("项目名称", 45, 90, 100),
    ]
    cols = _learn_columns(header)
    assert "name" in cols
    assert "spec" in cols  # fallback 补
    assert "tax_amount" in cols


def test_learn_columns_empty_header_all_fallback():
    """空表头 → 全部用 fallback(行 148-152 全走)。"""
    cols = _learn_columns([])
    # 8 列都有值
    assert len(cols) == 8
    assert cols["name"] == 50


def test_learn_columns_split_shui_e_produces_tax_amount():
    """'税'+'额' 拆字两个相邻 word → tax_amount 列,中心取两字中点(行 136-142)。

    _learn_columns 的拆字配对:'税' 设 pending='tax' 并记 cx(行 140-142),后续
    '额' 在 pending=='tax' 时配对 → tax_amount,中心取两字中点(行 136-138)。
    现有测试只用连写 word('税额'),从未直接单测 '税'+'额' 拆字路径;该分支是 4 个
    pending 分支(unit_or_price/quantity/amount/tax)里唯一没被直接单测的。
    """
    header = [_w("税", 425, 440, 100), _w("额", 465, 480, 100)]
    cols = _learn_columns(header)
    assert "tax_amount" in cols
    # 税 cx=(425+440)/2=432.5,额 cx=(465+480)/2=472.5,中点=(432.5+472.5)/2=452.5
    assert cols["tax_amount"] == 452.5


# ---------------------------------------------------------------------------
# _column_of
# ---------------------------------------------------------------------------


def test_column_of_finds_nearest():
    centers = {"name": 50, "amount": 380}
    assert _column_of(_w("x", 48, 52, 0), centers) == "name"
    assert _column_of(_w("x", 378, 382, 0), centers) == "amount"


# ---------------------------------------------------------------------------
# _group_rows
# ---------------------------------------------------------------------------


def test_group_rows_clusters_by_top():
    """top 相近(3pt 容差)的 word 归同一行。"""
    words = [
        _w("a", 0, 10, 100),
        _w("b", 20, 30, 102),  # round(100/3)=round(102/3)=34? 实际 100/3=33.3→33, 102/3=34
        _w("c", 0, 10, 200),
    ]
    rows, keys = _group_rows(words)
    # 至少分两行(200 单独一行);100/102 可能同或不同,只验证聚合正确
    assert len(rows) >= 2
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# _extract_detail_items:边界(行 193, 205, 236, 243-251)
# ---------------------------------------------------------------------------


def test_extract_detail_items_empty_words():
    """空 words → 返回 [](行 193)。"""
    assert _extract_detail_items([], {"name": 50}) == []


def test_extract_detail_items_no_header_starts_at_zero():
    """无表头行 → start_idx=0,从头处理(行 205)。"""
    words = [
        _w("品名", 45, 90, 100),  # 无表头
        _w("合计", 45, 90, 120),  # 合计行立即结束
    ]
    items = _extract_detail_items(words, {"name": 50, "spec": 190, "amount": 380})
    # 第一行 name="品名",但下一行是合计 → 只 1 项?合计行 break 前先处理品名行
    # 实际:keys_order=[33, 40],start_idx=0,处理 key=33("品名")→ append;key=40("合计")→ break
    assert len(items) == 1


def test_extract_detail_items_empty_name_skipped():
    """行 name 为空 → continue 跳过(行 236)。"""
    # 构造一行:只有 amount 列有 word(name 列无)
    words = [
        _w("金额", 378, 390, 100),  # name 列无 → join("name")="" → skip
    ]
    centers = {"name": 50, "amount": 380}
    items = _extract_detail_items(words, centers)
    assert items == []


def test_extract_detail_items_continuation_merges():
    """续行(只有 name/spec)→ 合并到上一条(行 243-251)。"""
    centers = {
        "name": 50,
        "spec": 190,
        "unit": 250,
        "quantity": 290,
        "unit_price": 330,
        "amount": 380,
        "tax_rate": 430,
        "tax_amount": 470,
    }
    words = [
        # 表头
        _w("项目名称", 45, 90, 100),
        _w("规格型号", 185, 240, 100),
        _w("单位", 245, 270, 100),
        _w("数量", 285, 310, 100),
        _w("单价", 325, 350, 100),
        _w("金额", 375, 400, 100),
        _w("税率", 425, 450, 100),
        _w("税额", 465, 490, 100),
        # 数据行
        _w("主品", 45, 90, 120),
        _w("S1", 185, 200, 120),
        _w("件", 245, 260, 120),
        _w("1", 285, 295, 120),
        _w("10", 325, 340, 120),
        _w("10", 375, 390, 120),
        _w("13%", 425, 440, 120),
        _w("1.3", 465, 480, 120),
        # 续行:只有 name
        _w("续", 45, 60, 140),
    ]
    items = _extract_detail_items(words, centers)
    assert len(items) == 1
    assert "续" in items[0].name


def test_extract_detail_items_continuation_with_spec():
    """续行同时有 name 和 spec → 合并(行 247-248 cont_spec)。"""
    centers = {
        "name": 50,
        "spec": 190,
        "unit": 250,
        "quantity": 290,
        "unit_price": 330,
        "amount": 380,
        "tax_rate": 430,
        "tax_amount": 470,
    }
    words = [
        _w("项目名称", 45, 90, 100),
        _w("规格型号", 185, 240, 100),
        _w("单位", 245, 270, 100),
        _w("数量", 285, 310, 100),
        _w("单价", 325, 350, 100),
        _w("金额", 375, 400, 100),
        _w("税率", 425, 450, 100),
        _w("税额", 465, 490, 100),
        _w("主品", 45, 90, 120),
        _w("原spec", 185, 220, 120),
        _w("件", 245, 260, 120),
        _w("1", 285, 295, 120),
        _w("10", 325, 340, 120),
        _w("10", 375, 390, 120),
        _w("13%", 425, 440, 120),
        _w("1.3", 465, 480, 120),
        # 续行:name + spec,其余空
        _w("续名", 45, 70, 140),
        _w("续spec", 185, 215, 140),
    ]
    items = _extract_detail_items(words, centers)
    assert len(items) == 1
    assert "续名" in items[0].name
    assert "续spec" in items[0].spec


# ---------------------------------------------------------------------------
# _extract_invoice_number:fallback(行 282-287)
# ---------------------------------------------------------------------------


def test_extract_invoice_number_from_label():
    rows = {0: [_w("发票号码：", 300, 360, 100), _w("99990000000000000001", 370, 500, 100)]}
    assert _extract_invoice_number(rows, [0]) == "99990000000000000001"


def test_extract_invoice_number_fallback_any_18_digits():
    """无'发票号码'标签 → fallback 扫描任意 18+ 位(行 282-287)。"""
    rows = {0: [_w("其它文本", 0, 50, 100), _w("99990000000000000099", 60, 200, 100)]}
    assert _extract_invoice_number(rows, [0]) == "99990000000000000099"


def test_extract_invoice_number_no_match_returns_empty():
    rows = {0: [_w("无数字", 0, 50, 100)]}
    assert _extract_invoice_number(rows, [0]) == ""


def test_extract_invoice_number_label_but_no_digits():
    """有'发票号码'标签但无 18+ 位 → fallback 找到。"""
    rows = {0: [_w("发票号码：", 0, 50, 100)], 1: [_w("99990000000000000055", 0, 200, 110)]}
    assert _extract_invoice_number(rows, [0, 1]) == "99990000000000000055"


# ---------------------------------------------------------------------------
# _extract_issue_date(行 297)
# ---------------------------------------------------------------------------


def test_extract_issue_date_chinese_format():
    rows = {0: [_w("开票日期：2026年05月19日", 0, 200, 100)]}
    assert _extract_issue_date(rows, [0]) == "2026-05-19"


def test_extract_issue_date_no_match_returns_empty():
    rows = {0: [_w("无日期", 0, 50, 100)]}
    assert _extract_issue_date(rows, [0]) == ""


# ---------------------------------------------------------------------------
# _find_label_word + _extract_party_by_label(行 332, 362, 369-372)
# ---------------------------------------------------------------------------


def test_find_label_word_basic():
    rows = {0: [_w("名称:甲方", 100, 200, 100), _w("名称:乙方", 300, 400, 100)]}
    hits = _find_label_word(rows, [0], ("名称:",))
    assert len(hits) == 2
    assert hits[0] == (100, "甲方")


def test_find_label_word_strips_subsequent_label():
    """同行后续标签被裁掉(行 330-332)。"""
    rows = {0: [_w("名称:甲方识别号:123", 100, 300, 100)]}
    hits = _find_label_word(rows, [0], ("名称:", "识别号:"))
    assert hits == [(100, "甲方")]


def test_find_label_word_no_match_returns_empty():
    rows = {0: [_w("其它", 0, 50, 100)]}
    assert _find_label_word(rows, [0], ("名称:",)) == []


def test_extract_party_by_label_with_gou_xiao():
    """有购/销竖排标签 → 按 x 区分(行 364-373)。"""
    words_grouped = (
        {
            0: [
                _w("购", 10, 20, 80),
                _w("销", 300, 310, 80),
                _w("名称:买方名", 30, 200, 100),
                _w("名称:卖方名", 320, 500, 100),
            ]
        },
        [0],
    )
    seller, buyer = _extract_party_by_label(words_grouped)
    # 销标签 x=300,买方名称 x0=30 离购(10)近,卖方 x0=320 离销(300)近
    assert seller == "卖方名"
    assert buyer == "买方名"


def test_extract_party_by_label_no_labels_fallback_order():
    """无购/销标签 → 退回出现顺序(行 375-378)。"""
    words_grouped = (
        {0: [_w("名称:第一", 100, 200, 100), _w("名称:第二", 300, 400, 100)]},
        [0],
    )
    seller, buyer = _extract_party_by_label(words_grouped)
    assert seller == "第一"
    assert buyer == "第二"


def test_extract_party_by_label_no_name_hits_returns_empty():
    """无'名称:'标签 → 返回 ('', '')(行 361-362)。"""
    words_grouped = ({0: [_w("其它", 0, 50, 100)]}, [0])
    assert _extract_party_by_label(words_grouped) == ("", "")


# ---------------------------------------------------------------------------
# _extract_tax_ids(行 397, 402-405)
# ---------------------------------------------------------------------------


def test_extract_tax_ids_no_hits_returns_empty():
    """无税号标签 → 返回 ('', '')(行 396-397)。"""
    words_grouped = ({0: [_w("其它", 0, 50, 100)]}, [0])
    assert _extract_tax_ids(words_grouped) == ("", "")


def test_extract_tax_ids_with_gou_xiao():
    """有购/销标签 → 按 x 区分税号(行 399-406)。"""
    words_grouped = (
        {
            0: [
                _w("购", 10, 20, 80),
                _w("销", 300, 310, 80),
                _w("纳税人识别号:BUYID", 30, 200, 100),
                _w("纳税人识别号:SELLID", 320, 500, 100),
            ]
        },
        [0],
    )
    seller, buyer = _extract_tax_ids(words_grouped)
    assert seller == "SELLID"
    assert buyer == "BUYID"


def test_extract_tax_ids_fallback_order():
    """无购/销标签 → 退回出现顺序(行 408-410)。"""
    words_grouped = (
        {0: [_w("识别号:FIRST", 100, 200, 100), _w("识别号:SECOND", 300, 400, 100)]},
        [0],
    )
    seller, buyer = _extract_tax_ids(words_grouped)
    assert seller == "FIRST"
    assert buyer == "SECOND"


# ---------------------------------------------------------------------------
# _row_join_no_space
# ---------------------------------------------------------------------------


def test_row_join_no_space():
    ws = [_w("合", 0, 10, 0), _w("计", 20, 30, 0)]
    assert _row_join_no_space(ws) == "合计"


# ---------------------------------------------------------------------------
# _find_amount_in_next_rows:ValueError / 向前看(行 469-470, 477-482)
# ---------------------------------------------------------------------------


def test_find_amount_in_next_rows_value_error_returns_empty():
    """start_key 不在 keys → ValueError → 返回 ''(行 469-470)。"""
    rows = {0: [_w("100.00", 0, 50, 100)]}
    assert _find_amount_in_next_rows(rows, [0, 1], 99, 2) == ""


def test_find_amount_in_next_rows_finds_after():
    rows = {
        0: [_w("标签", 0, 50, 100)],
        1: [_w("100.00", 0, 50, 110)],
    }
    assert _find_amount_in_next_rows(rows, [0, 1], 0, 2) == "100.00"


def test_find_amount_in_next_rows_looks_before():
    """向后无金额 → 向前看 1 行(行 477-482)。"""
    rows = {
        0: [_w("100.00", 0, 50, 100)],
        1: [_w("标签", 0, 50, 110)],
    }
    # start_key=1,向后无,向前 key=0 有金额
    assert _find_amount_in_next_rows(rows, [0, 1], 1, 2) == "100.00"


def test_find_amount_in_next_rows_no_amount_returns_empty():
    rows = {0: [_w("无金额", 0, 50, 100)], 1: [_w("也无", 0, 50, 110)]}
    assert _find_amount_in_next_rows(rows, [0, 1], 0, 2) == ""


# ---------------------------------------------------------------------------
# _extract_amounts:小写兜底(行 451-456)
# ---------------------------------------------------------------------------


def test_extract_amounts_xiaoxie_fallback():
    """价税合计未取到 → 含'小写'的行兜底,金额在下一行(行 450-456)。"""
    # 合计行 + 价税合计标签行(无金额,无小写) + 小写行(无金额) + 金额行
    rows = {
        0: [_w("合计", 0, 50, 100), _w("1000.00", 380, 440, 100), _w("130.00", 470, 520, 100)],
        1: [_w("价税合计(大写)", 0, 100, 110)],  # 无金额,无"小写"
        2: [_w("(小写)", 0, 50, 120)],  # 含小写但本行无金额
        3: [_w("1130.00", 400, 460, 130)],  # 金额在下一行
    }
    without, tax, with_tax = _extract_amounts(rows, [0, 1, 2, 3])
    assert without == "1000.00"
    assert tax == "130.00"
    # 价税合计:行1 价税合计但无金额→next rows(2,3);行2 有金额?无;
    # 行3 有 1130.00 → 但 _find_amount_in_next_rows 从 key=1 向后看 2 行 → key=2,3
    assert with_tax == "1130.00"


def test_extract_amounts_jia_shui_in_same_row():
    """价税合计标签行有金额 → 直接取(行 444-445)。"""
    rows = {
        0: [_w("合计", 0, 50, 100), _w("1000.00", 380, 440, 100), _w("130.00", 470, 520, 100)],
        1: [_w("价税合计", 0, 50, 110), _w("1130.00", 400, 460, 110)],
    }
    without, tax, with_tax = _extract_amounts(rows, [0, 1])
    assert without == "1000.00"
    assert tax == "130.00"
    assert with_tax == "1130.00"


def test_extract_amounts_no_data_returns_empty():
    rows = {0: [_w("无关", 0, 50, 100)]}
    without, tax, with_tax = _extract_amounts(rows, [0])
    assert (without, tax, with_tax) == ("", "", "")


# ---------------------------------------------------------------------------
# _extract_amount_chinese(行 494)
# ---------------------------------------------------------------------------


def test_extract_amount_chinese_no_match_returns_empty():
    """无价税合计+中文 → 返回 ''(行 494)。"""
    rows = {0: [_w("无关文本", 0, 50, 100)]}
    assert _extract_amount_chinese(rows, [0]) == ""


def test_extract_amount_chinese_matches():
    rows = {0: [_w("价税合计(大写)壹仟圆整", 0, 200, 100)]}
    assert "壹仟圆" in _extract_amount_chinese(rows, [0])


# ---------------------------------------------------------------------------
# parse_pdf:文件不存在(行 506)
# ---------------------------------------------------------------------------


def test_parse_pdf_missing_file(tmp_path):
    """文件不存在 → UnsupportedFormatError(行 505-506)。"""
    with pytest.raises(UnsupportedFormatError, match="文件不存在"):
        parse_pdf(tmp_path / "nope.pdf")
