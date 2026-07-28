"""ofd_parser 辅助函数与边界的补充测试。

覆盖未达行:辅助函数空输入/异常分支、Content.xml 回退、明细续行合并、
_parse_first_doc_root 异常等。
"""

from __future__ import annotations

import io
import zipfile

import pytest

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.parsers.ofd_parser import (
    _collect_content_xmls,
    _column_of,
    _extract_amount_chinese,
    _extract_detail_items,
    _extract_invoice_type,
    _extract_party_names_from_objs,
    _normalize_custom_key,
    _parse_custom_data,
    _parse_first_doc_root,
    _parse_float,
    _parse_text_objects,
    _safe_add,
    parse_ofd,
)

# ---------------------------------------------------------------------------
# _normalize_custom_key:剥离括号兜底
# ---------------------------------------------------------------------------


def test_normalize_custom_key_strips_trailing_paren():
    """尾部括号后缀兜底:不在别名表 → 剥离括号后再查/返回。"""
    assert _normalize_custom_key("价税合计(大写)") == "价税合计"  # 别名表直接命中
    # 不在别名表但有括号 → 剥离
    assert _normalize_custom_key("自定义键(注释)") == "自定义键"
    assert _normalize_custom_key("全角（注释）") == "全角"


def test_normalize_custom_key_fullwidth_space():
    """含全角空格的键被清理。"""
    assert _normalize_custom_key("价税合计\u3000(大写)") == "价税合计"


def test_normalize_custom_key_plain():
    """普通键原样返回。"""
    assert _normalize_custom_key("发票号码") == "发票号码"


# ---------------------------------------------------------------------------
# _parse_custom_data:空 / ParseError(行 68-73)
# ---------------------------------------------------------------------------


def test_parse_custom_data_empty_returns_empty():
    """空字符串 → 返回 {}(行 68-69)。"""
    assert _parse_custom_data("") == {}


def test_parse_custom_data_parse_error_returns_empty():
    """非 XML → ParseError → 返回 {}(行 72-73)。"""
    assert _parse_custom_data("not xml <<<") == {}


def test_parse_custom_data_skips_empty_name_or_text():
    """Name 空 或 text 空 → 跳过。"""
    xml = (
        '<?xml version="1.0"?><ofd:OFD xmlns:ofd="http://www.ofdspec.org/2016">'
        '<ofd:CustomData Name="">值</ofd:CustomData>'  # 空 Name → 跳过
        '<ofd:CustomData Name="键"></ofd:CustomData>'  # 空 text → 跳过
        '<ofd:CustomData Name="发票号码">123</ofd:CustomData>'  # 有效
        "</ofd:OFD>"
    )
    result = _parse_custom_data(xml)
    assert result == {"发票号码": "123"}


# ---------------------------------------------------------------------------
# _parse_text_objects:空 / ParseError / 空 TextCode(行 138-156)
# ---------------------------------------------------------------------------


def test_parse_text_objects_empty_returns_empty():
    """空字符串 → 返回 [](行 138-139)。"""
    assert _parse_text_objects("") == []


def test_parse_text_objects_parse_error_returns_empty():
    """非 XML → 返回 [](行 142-143)。"""
    assert _parse_text_objects("not xml <<<") == []


def test_parse_text_objects_skips_empty_textcode():
    """TextCode 文本为空 → 跳过(行 155-156)。"""
    xml = (
        '<?xml version="1.0"?><ofd:Page xmlns:ofd="http://www.ofdspec.org/2016">'
        '<ofd:TextObject><ofd:TextCode></ofd:TextCode></ofd:TextObject>'  # 空 → 跳过
        '<ofd:TextObject><ofd:TextCode X="10" Y="20">有效</ofd:TextCode></ofd:TextObject>'
        "</ofd:Page>"
    )
    objs = _parse_text_objects(xml)
    assert len(objs) == 1
    assert objs[0]["text"] == "有效"
    assert objs[0]["x"] == 10.0
    assert objs[0]["y"] == 20.0


def test_parse_text_objects_boundary_fallback_when_no_xy():
    """无 X/Y → 回退 Boundary 前两位。"""
    xml = (
        '<?xml version="1.0"?><ofd:Page xmlns:ofd="http://www.ofdspec.org/2016">'
        '<ofd:TextObject Boundary="100 200 50 12">'
        '<ofd:TextCode>无坐标</ofd:TextCode></ofd:TextObject>'
        "</ofd:Page>"
    )
    objs = _parse_text_objects(xml)
    assert objs[0]["x"] == 100.0
    assert objs[0]["y"] == 200.0


# ---------------------------------------------------------------------------
# _parse_float:ValueError(行 166-167)
# ---------------------------------------------------------------------------


def test_parse_float_value_error_returns_default():
    """非法 float → ValueError → 返回默认值(行 166-167)。"""
    assert _parse_float("abc", 5.0) == 5.0


def test_parse_float_none_returns_default():
    """val=None → 返回默认值。"""
    assert _parse_float(None, 7.0) == 7.0


def test_parse_float_valid():
    assert _parse_float("3.14", 0.0) == 3.14


# ---------------------------------------------------------------------------
# _collect_content_xmls:回退路径(行 112, 118-127)
# ---------------------------------------------------------------------------


def _make_zip(members: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_collect_content_xmls_fallback_to_glob(tmp_path):
    """无 doc_root → 回退 zip 内任意 *Content.xml(行 122-127)。"""
    zbytes = _make_zip(
        {
            "Doc_0/Pages/Page_0/Content.xml": '<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"/>',
        }
    )
    p = tmp_path / "test.ofd"
    p.write_bytes(zbytes)
    with zipfile.ZipFile(p, "r") as zf:
        pages = _collect_content_xmls(zf, "")
    assert len(pages) == 1


def test_collect_content_xmls_empty_baseloc_skipped(tmp_path):
    """Document.xml 含 Page 但 BaseLoc 空 → 跳过;无有效页 → 回退 glob。"""
    doc_xml = (
        '<?xml version="1.0"?><ofd:Document xmlns:ofd="http://www.ofdspec.org/2016">'
        '<ofd:Pages><ofd:Page BaseLoc=""/></ofd:Pages></ofd:Document>'
    )
    zbytes = _make_zip(
        {
            "Doc_0/Document.xml": doc_xml,
            "Doc_0/Pages/Page_0/Content.xml": '<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"/>',
        }
    )
    p = tmp_path / "test.ofd"
    p.write_bytes(zbytes)
    with zipfile.ZipFile(p, "r") as zf:
        pages = _collect_content_xmls(zf, "Doc_0/Document.xml")
    # BaseLoc 空 → 精确路径无页 → 回退 glob 找到 1 个
    assert len(pages) == 1


def test_collect_content_xmls_document_parse_error_falls_back(tmp_path):
    """Document.xml 非 XML → ParseError → 回退 glob(行 118-119)。"""
    zbytes = _make_zip(
        {
            "Doc_0/Document.xml": "not xml <<<",
            "Doc_0/Pages/Page_0/Content.xml": '<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"/>',
        }
    )
    p = tmp_path / "test.ofd"
    p.write_bytes(zbytes)
    with zipfile.ZipFile(p, "r") as zf:
        pages = _collect_content_xmls(zf, "Doc_0/Document.xml")
    assert len(pages) == 1


def test_collect_content_xmls_precise_baseloc(tmp_path):
    """Document.xml 有 BaseLoc → 精确定位 Content.xml。"""
    doc_xml = (
        '<?xml version="1.0"?><ofd:Document xmlns:ofd="http://www.ofdspec.org/2016">'
        '<ofd:Pages><ofd:Page BaseLoc="Pages/Page_0/Content.xml"/></ofd:Pages></ofd:Document>'
    )
    zbytes = _make_zip(
        {
            "Doc_0/Document.xml": doc_xml,
            "Doc_0/Pages/Page_0/Content.xml": '<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"/>',
        }
    )
    p = tmp_path / "test.ofd"
    p.write_bytes(zbytes)
    with zipfile.ZipFile(p, "r") as zf:
        pages = _collect_content_xmls(zf, "Doc_0/Document.xml")
    assert len(pages) == 1


# ---------------------------------------------------------------------------
# _parse_first_doc_root:ParseError / 无 DocRoot(行 441-442, 446)
# ---------------------------------------------------------------------------


def test_parse_first_doc_root_parse_error_returns_empty():
    """非 XML → ParseError → 返回 ''(行 441-442)。"""
    assert _parse_first_doc_root("not xml <<<") == ""


def test_parse_first_doc_root_no_docroot_returns_empty():
    """无 DocRoot 元素 → 返回 ''(行 446)。"""
    xml = '<?xml version="1.0"?><ofd:OFD xmlns:ofd="http://www.ofdspec.org/2016"/>'
    assert _parse_first_doc_root(xml) == ""


def test_parse_first_doc_root_strips_whitespace():
    """DocRoot 文本被 strip。"""
    xml = (
        '<?xml version="1.0"?><ofd:OFD xmlns:ofd="http://www.ofdspec.org/2016">'
        '<ofd:DocBody><ofd:DocRoot>  Doc_0/Document.xml  </ofd:DocRoot></ofd:DocBody></ofd:OFD>'
    )
    assert _parse_first_doc_root(xml) == "Doc_0/Document.xml"


def test_parse_first_doc_root_empty_text_skipped():
    """DocRoot text 为空 → 跳过,返回 ''。"""
    xml = (
        '<?xml version="1.0"?><ofd:OFD xmlns:ofd="http://www.ofdspec.org/2016">'
        '<ofd:DocBody><ofd:DocRoot></ofd:DocRoot></ofd:DocBody></ofd:OFD>'
    )
    assert _parse_first_doc_root(xml) == ""


# ---------------------------------------------------------------------------
# _extract_detail_items:空输入 / 续行合并 / 空名称跳过(行 220, 259, 267-274)
# ---------------------------------------------------------------------------


def test_extract_detail_items_empty_returns_empty():
    """空 objs → 返回 [](行 220)。"""
    assert _extract_detail_items([]) == []


def test_extract_detail_items_empty_name_skipped():
    """行首列(name)空 → 跳过该行(行 259)。"""
    # 构造一行:y=200,name 列(x=50)无对象,只有 amount(x=380)
    objs = [{"text": "100", "x": 380, "y": 200}]
    items = _extract_detail_items(objs)
    assert items == []


def test_extract_detail_items_continuation_merges_to_prev():
    """续行(只有 name/spec,其余空)→ 合并到上一条(行 266-274)。"""
    # 表头行
    header_y = 100
    data_y = 120
    cont_y = 123  # 同一聚类(y/3 容差)
    objs = [
        # 表头
        {"text": "项目名称", "x": 50, "y": header_y},
        {"text": "规格型号", "x": 190, "y": header_y},
        {"text": "单位", "x": 250, "y": header_y},
        {"text": "数量", "x": 290, "y": header_y},
        {"text": "单价", "x": 330, "y": header_y},
        {"text": "金额", "x": 380, "y": header_y},
        {"text": "税率", "x": 430, "y": header_y},
        {"text": "税额", "x": 470, "y": header_y},
        # 数据行
        {"text": "*品*甲", "x": 50, "y": data_y},
        {"text": "S1", "x": 190, "y": data_y},
        {"text": "件", "x": 250, "y": data_y},
        {"text": "1", "x": 290, "y": data_y},
        {"text": "10", "x": 330, "y": data_y},
        {"text": "10", "x": 380, "y": data_y},
        {"text": "13%", "x": 430, "y": data_y},
        {"text": "1.3", "x": 470, "y": data_y},
        # 续行(只有 name 列有值)
        {"text": "续块", "x": 50, "y": cont_y},
    ]
    items = _extract_detail_items(objs)
    assert len(items) == 1
    assert "续块" in items[0].name
    assert "*品*甲" in items[0].name


def test_extract_detail_items_continuation_with_name_and_spec():
    """续行同时有 name 和 spec,其余列空 → 合并到上一条(行 266-274,含 271 cont_spec)。"""
    header_y = 100
    data_y = 120
    cont_y = 200  # 不同聚类
    objs = [
        {"text": "项目名称", "x": 50, "y": header_y},
        {"text": "规格型号", "x": 190, "y": header_y},
        {"text": "单位", "x": 250, "y": header_y},
        {"text": "数量", "x": 290, "y": header_y},
        {"text": "单价", "x": 330, "y": header_y},
        {"text": "金额", "x": 380, "y": header_y},
        {"text": "税率", "x": 430, "y": header_y},
        {"text": "税额", "x": 470, "y": header_y},
        {"text": "品名", "x": 50, "y": data_y},
        {"text": "原spec", "x": 190, "y": data_y},
        {"text": "件", "x": 250, "y": data_y},
        {"text": "1", "x": 290, "y": data_y},
        {"text": "10", "x": 330, "y": data_y},
        {"text": "10", "x": 380, "y": data_y},
        {"text": "13%", "x": 430, "y": data_y},
        {"text": "1.3", "x": 470, "y": data_y},
        # 续行:同时有 name 和 spec,其余空 → 合并(触发 cont_spec 分支,行 271)
        {"text": "续名", "x": 50, "y": cont_y},
        {"text": "续spec", "x": 190, "y": cont_y},
    ]
    items = _extract_detail_items(objs)
    assert len(items) == 1
    assert "品名" in items[0].name
    assert "续名" in items[0].name
    assert "原spec" in items[0].spec
    assert "续spec" in items[0].spec


def test_extract_detail_items_continuation_name_only_no_spec():
    """续行只有 name(无 spec)→ 合并 name,cont_spec 为空跳过 spec 赋值(行 270 False)。"""
    header_y = 100
    data_y = 120
    cont_y = 200
    objs = [
        {"text": "项目名称", "x": 50, "y": header_y},
        {"text": "规格型号", "x": 190, "y": header_y},
        {"text": "单位", "x": 250, "y": header_y},
        {"text": "数量", "x": 290, "y": header_y},
        {"text": "单价", "x": 330, "y": header_y},
        {"text": "金额", "x": 380, "y": header_y},
        {"text": "税率", "x": 430, "y": header_y},
        {"text": "税额", "x": 470, "y": header_y},
        {"text": "主品名", "x": 50, "y": data_y},
        {"text": "件", "x": 250, "y": data_y},
        {"text": "1", "x": 290, "y": data_y},
        {"text": "10", "x": 330, "y": data_y},
        {"text": "10", "x": 380, "y": data_y},
        {"text": "13%", "x": 430, "y": data_y},
        {"text": "1.3", "x": 470, "y": data_y},
        # 续行:只有 name
        {"text": "续名", "x": 50, "y": cont_y},
    ]
    items = _extract_detail_items(objs)
    assert len(items) == 1
    assert "主品名" in items[0].name
    assert "续名" in items[0].name


# ---------------------------------------------------------------------------
# _extract_party_names_from_objs:名称含识别号停止标签(行 311)
# ---------------------------------------------------------------------------


def test_extract_party_names_stops_at_taxid_label():
    """名称块内含'识别号:' → 裁掉(行 310-311)。"""
    objs = [
        {"text": "名称:销售方名称识别号:123", "x": 50, "y": 100},
        {"text": "名称:购买方", "x": 300, "y": 100},
    ]
    seller, buyer = _extract_party_names_from_objs(objs)
    assert seller == "销售方名称"
    assert buyer == "购买方"


def test_extract_party_names_empty_when_no_label():
    """无'名称:'标签 → 返回 ('', '')。"""
    objs = [{"text": "其它文本", "x": 50, "y": 100}]
    assert _extract_party_names_from_objs(objs) == ("", "")


def test_extract_party_names_fullwidth_colon():
    """全角冒号 '名称：' 也识别。"""
    objs = [{"text": "名称：全角方", "x": 50, "y": 100}]
    seller, _ = _extract_party_names_from_objs(objs)
    assert seller == "全角方"


# ---------------------------------------------------------------------------
# _extract_amount_chinese:跳过备注(行 328-329)
# ---------------------------------------------------------------------------


def test_extract_amount_chinese_skips_remark():
    """含'备注'的行被跳过,不误匹配其中的金额(行 328-329)。"""
    texts = ["备注:此处有壹圆整", "贰仟圆整"]
    assert _extract_amount_chinese(texts) == "贰仟圆整"


def test_extract_amount_chinese_no_match_returns_empty():
    """无圆/元 → 返回 ''。"""
    assert _extract_amount_chinese(["普通文本"]) == ""


def test_extract_amount_chinese_matches_jiao():
    """含'角'的金额匹配。"""
    assert _extract_amount_chinese(["壹佰贰拾圆伍角"]) == "壹佰贰拾圆伍角"


# ---------------------------------------------------------------------------
# _extract_invoice_type:回退到 custom/默认
# ---------------------------------------------------------------------------


def test_extract_invoice_type_from_custom():
    """标题无类型 → 回退 custom['发票类型'](行 347)。"""
    assert _extract_invoice_type(["普通文本"], {"发票类型": "自定义类型"}) == "自定义类型"


def test_extract_invoice_type_default():
    """无标题无 custom → 默认 '电子发票'(行 347)。"""
    assert _extract_invoice_type(["普通文本"], {}) == "电子发票"


# ---------------------------------------------------------------------------
# _safe_add
# ---------------------------------------------------------------------------


def test_safe_add_valid():
    assert _safe_add("1000.00", "130.00") == "1130.00"


def test_safe_add_invalid_returns_empty():
    assert _safe_add("abc", "130") == ""
    assert _safe_add("100", None) == ""


# ---------------------------------------------------------------------------
# _column_of:边界
# ---------------------------------------------------------------------------


def test_column_of_known_anchors():
    """各列锚点 x → 正确列名。"""
    assert _column_of(50.0) == "name"
    assert _column_of(470.0) == "tax_amount"


def test_column_of_far_left_falls_to_nearest():
    """x 远小于第一列 → 落到最近锚点 name。"""
    assert _column_of(-1000) == "name"


# ---------------------------------------------------------------------------
# parse_ofd:BadZipFile / 缺 OFD.xml
# ---------------------------------------------------------------------------


def test_parse_ofd_bad_zip_content(tmp_path):
    """非 ZIP 内容(但不是空)→ BadZipFile → UnsupportedFormatError。"""
    p = tmp_path / "bad.ofd"
    p.write_bytes(b"definitely not a zip file here")
    with pytest.raises(UnsupportedFormatError, match="不是有效 ZIP"):
        parse_ofd(p)


def test_parse_ofd_amount_fallback_when_price_missing(tmp_path):
    """价税合计缺失但有不含税+税额 → _safe_add 兜底(行 406-407)。"""
    # 构造 OFD:无价税合计键,有合计金额 + 合计税额
    ofd_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ofd:OFD xmlns:ofd="http://www.ofdspec.org/2016" Version="1.2" DocType="OFD">'
        '<ofd:DocBody><ofd:DocRoot>Doc_0/Document.xml</ofd:DocRoot>'
        '<ofd:DocInfo><ofd:CustomDatas>'
        '<ofd:CustomData Name="发票号码">99990000000000000077</ofd:CustomData>'
        '<ofd:CustomData Name="合计金额">1000.00</ofd:CustomData>'
        '<ofd:CustomData Name="合计税额">130.00</ofd:CustomData>'
        '</ofd:CustomDatas></ofd:DocInfo></ofd:DocBody></ofd:OFD>'
    )
    doc_xml = (
        '<?xml version="1.0"?><ofd:Document xmlns:ofd="http://www.ofdspec.org/2016">'
        '<ofd:CommonData><ofd:PageArea><ofd:PhysicalBox>0 0 210 297</ofd:PhysicalBox></ofd:PageArea></ofd:CommonData>'
        '<ofd:Pages><ofd:Page ID="1" BaseLoc="Pages/Page_0/Content.xml"/></ofd:Pages></ofd:Document>'
    )
    content_xml = (
        '<?xml version="1.0"?><ofd:Page xmlns:ofd="http://www.ofdspec.org/2016">'
        '<ofd:Content><ofd:Layer Type="Body"/></ofd:Content></ofd:Page>'
    )
    zbytes = _make_zip(
        {"OFD.xml": ofd_xml, "Doc_0/Document.xml": doc_xml, "Doc_0/Pages/Page_0/Content.xml": content_xml}
    )
    p = tmp_path / "fallback.ofd"
    p.write_bytes(zbytes)
    inv = parse_ofd(p, source_file="fallback.ofd")
    # 价税合计 = 1000 + 130 = 1130.00
    assert inv.amount_with_tax == "1130.00"
    assert inv.invoice_number == "99990000000000000077"


def test_parse_ofd_default_source_file(tmp_path, ofd_sample):
    """不传 source_file → 用 path.name。"""
    inv = parse_ofd(ofd_sample)
    assert inv.source_file == "sample.ofd"
