"""OFD 发票解析(ZIP 内 XML)。

设计:以 OFD.xml 的 CustomData 键值为主(结构化数据,可靠度近似 XML 原件),
Content.xml 的带坐标 TextObject 补充买卖方名称/大写金额,以及明细行聚类。

已知限制:
- 多 DocBody(一张 .ofd 内含多张发票)仅处理首张,不拆分多发票。
"""

import contextlib
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.types import Invoice, LineItem

OFD_NS = "{http://www.ofdspec.org/2016}"

# Content.xml 解析出的 TextObject 字典({"text": str, "x": float, "y": float})
TextObj = dict[str, Any]


# --------------------------------------------------------------------------- #
# 键名归一化(#2):解决 CustomData Name 的变体问题(全角空格、尾部括号后缀、别名)
# --------------------------------------------------------------------------- #

# 别名 -> 标准键。覆盖税务局不同渠道的常见变体。
_KEY_ALIASES: dict[str, str] = {
    # 价税合计
    "价税合计(大写)": "价税合计",
    "价税合计（大写）": "价税合计",
    "价税合计(小写)": "价税合计",
    "价税合计（小写）": "价税合计",
    # 合计金额/税额
    "合计(元)": "合计金额",
    "合计（元）": "合计金额",
    "金额合计": "合计金额",
    "税额合计": "合计税额",
    # 开票日期
    "开票时间": "开票日期",
    # 纳税人识别号简称
    "销售方识别号": "销售方纳税人识别号",
    "购买方识别号": "购买方纳税人识别号",
}


def _normalize_custom_key(raw: str) -> str:
    """归一化 CustomData 的 Name 键。

    步骤:去首尾空白(含全角空格)→ 查别名表(原始键优先)→ 剥离尾部括号后缀兜底。
    例:"价税合计(大写)" → "价税合计";"合计(元)" → "合计金额"。
    """
    key = raw.replace("\u3000", "").strip()
    # 先查原始键(如 "合计(元)" 直接命中别名表)
    if key in _KEY_ALIASES:
        return _KEY_ALIASES[key]
    # 再剥离尾部半角/全角括号后缀兜底:(...) / （...）
    stripped = re.sub(r"[\(（][^\)）]*[\)）]$", "", key)
    return _KEY_ALIASES.get(stripped, stripped)


def _parse_custom_data(ofd_xml: str) -> dict[str, str]:
    """从 OFD.xml 的 CustomData 提取键值,键名归一化后返回 {标准键: 值}。"""
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
            result[_normalize_custom_key(name)] = cd.text.strip()
    return result


# --------------------------------------------------------------------------- #
# Content.xml 解析:文本列表 + TextObject 坐标(供明细聚类与名称/金额补充)
# --------------------------------------------------------------------------- #


def _read_zip_member(zf: zipfile.ZipFile, name: str) -> str:
    """读 zip 内某成员文本,不存在返回空串。"""
    try:
        return zf.read(name).decode("utf-8", errors="replace")
    except KeyError:
        return ""


def _collect_content_xmls(zf: zipfile.ZipFile, doc_root: str) -> list[str]:
    """收集所有页的 Content.xml 内容。

    优先解析 Document.xml 的 <Page BaseLoc="..."> 权威路径(#7 多页),
    Document.xml 缺失时回退到 zip 内所有 *Content.xml。
    返回各页 Content.xml 文本(按页顺序)。
    """
    # 1. 尝试按 Document.xml 的 BaseLoc 精确定位
    pages: list[str] = []
    if doc_root:
        doc_xml = _read_zip_member(zf, doc_root)
        if doc_xml:
            try:
                root = ET.fromstring(doc_xml)
                base = doc_root.rsplit("/", 1)[0] if "/" in doc_root else ""
                for page in root.iter(f"{OFD_NS}Page"):
                    base_loc = page.get("BaseLoc", "")
                    if not base_loc:
                        continue
                    # BaseLoc 相对 Doc_x 目录
                    path = f"{base}/{base_loc}" if base else base_loc
                    content = _read_zip_member(zf, path)
                    if content:
                        pages.append(content)
            except ET.ParseError:
                pass  # 回退到模糊匹配

    # 2. 回退:zip 内任意 *Content.xml
    if not pages:
        for name in zf.namelist():
            if name.endswith("Content.xml"):
                content = _read_zip_member(zf, name)
                if content:
                    pages.append(content)
    return pages


def _parse_text_objects(content_xml: str) -> list[TextObj]:
    """解析 Content.xml,返回 TextObject 列表。

    每项:{"text": str, "x": float, "y": float}。
    坐标取 TextCode 的 X/Y(基线起点);缺失时回退 TextObject 的 Boundary 前两位。
    """
    objs: list[TextObj] = []
    if not content_xml:
        return objs
    try:
        root = ET.fromstring(content_xml)
    except ET.ParseError:
        return objs
    for to in root.iter(f"{OFD_NS}TextObject"):
        boundary = to.get("Boundary", "")
        bx = by = 0.0
        if boundary:
            parts = boundary.split()
            if len(parts) >= 2:
                with contextlib.suppress(ValueError):
                    bx, by = float(parts[0]), float(parts[1])
        # 一个 TextObject 可含多个 TextCode(不同段),逐段收集
        for tc in to.iter(f"{OFD_NS}TextCode"):
            text = (tc.text or "").strip()
            if not text:
                continue
            x = _parse_float(tc.get("X"), bx)
            y = _parse_float(tc.get("Y"), by)
            objs.append({"text": text, "x": x, "y": y})
    return objs


def _parse_float(val: str | None, default: float) -> float:
    try:
        return float(val) if val is not None else default
    except ValueError:
        return default


def _parse_content_texts(content_xml: str) -> list[str]:
    """从 Content.xml 提取所有 TextCode 文本(坐标无关),返回文本列表。"""
    return [o["text"] for o in _parse_text_objects(content_xml)]


# --------------------------------------------------------------------------- #
# 明细行坐标聚类(#1):Y 定行、X 定列,复用 pdf_parser 的聚列思路
# --------------------------------------------------------------------------- #

# 明细列的 x 锚点(适配 OFD 版式,单位 pt,与 pdf_parser 经验值一致)。
_COL_ANCHORS: list[tuple[str, float]] = [
    ("name", 50),
    ("spec", 190),
    ("unit", 250),
    ("quantity", 290),
    ("unit_price", 330),
    ("amount", 380),
    ("tax_rate", 430),
    ("tax_amount", 470),
]

# 构造列分界:每列 x 范围 = [本列起点, 下一列起点);最后一列到无穷
_COL_RANGES: list[tuple[str, float, float]] = []
for _i, (_col_name, _anchor) in enumerate(_COL_ANCHORS):
    _nxt = _COL_ANCHORS[_i + 1][1] if _i + 1 < len(_COL_ANCHORS) else float("inf")
    _prev = _COL_ANCHORS[_i - 1][1] if _i > 0 else 0
    _start = (_anchor + _prev) / 2 if _i > 0 else _anchor - 20
    _COL_RANGES.append((_col_name, _start, _nxt))

_COL_ORDER = [c for c, _, _ in _COL_RANGES]

_HEADER_KEYWORDS = ("项目名称", "规格型号")
_TOTAL_KEYWORDS = ("合计",)


def _column_of(x0: float) -> str:
    """根据 x 返回所属列名;落不进任何列归到最接近的锚点列。"""
    for name, lo, hi in _COL_RANGES:
        if lo <= x0 < hi:
            return name
    return min(_COL_ANCHORS, key=lambda a: abs(x0 - a[1]))[0]


def _extract_detail_items(objs: list[TextObj]) -> list[LineItem]:
    """从 TextObject 列表按坐标聚类提取明细行。

    流程:按 y 分行(3pt 容差)→ 定位表头行 → 每行按 x 落列 → 合并续行。
    空单元格(spec 缺失)因无对象落入该列,自动为空。
    """
    if not objs:
        return []

    # 按 y 分行
    rows: dict[int, list[TextObj]] = {}
    keys_in_order: list[int] = []
    for o in objs:
        key = round(o["y"] / 3)
        if key not in rows:
            rows[key] = []
            keys_in_order.append(key)
        rows[key].append(o)

    # 定位表头行
    start_idx = None
    for i, key in enumerate(keys_in_order):
        row_text = "".join(o["text"] for o in rows[key])
        if all(kw in row_text for kw in _HEADER_KEYWORDS):
            start_idx = i + 1
            break
    if start_idx is None:
        start_idx = 0

    items: list[LineItem] = []
    for key in keys_in_order[start_idx:]:
        ws = rows[key]
        row_text = "".join(o["text"] for o in ws)
        # 合计行结束
        if any(kw in row_text for kw in _TOTAL_KEYWORDS):
            break

        col_vals: dict[str, list[str]] = {c: [] for c in _COL_ORDER}
        for o in sorted(ws, key=lambda w: w["x"]):
            col_vals[_column_of(o["x"])].append(o["text"])

        def join(col: str, col_vals: dict[str, list[str]] = col_vals) -> str:
            return "".join(col_vals.get(col, []))

        name = join("name")
        if not name:
            continue

        # 续行:只有 name/spec 列有值,其余空 → 合并到上一条
        tail_empty = all(
            not join(c)
            for c in ("unit", "quantity", "unit_price", "amount", "tax_rate", "tax_amount")
        )
        if items and tail_empty and (join("name") or join("spec")):
            last = items[-1]
            cont_spec = join("spec")
            cont_name = join("name")
            if cont_spec:
                last.spec = (last.spec + cont_spec).strip()
            if cont_name:
                last.name = (last.name + cont_name).strip()
            continue

        items.append(
            LineItem(
                name=name,
                spec=join("spec"),
                unit=join("unit"),
                quantity=join("quantity"),
                unit_price=join("unit_price"),
                amount=join("amount"),
                tax_rate=join("tax_rate"),
                tax_amount=join("tax_amount"),
            )
        )
    return items


# --------------------------------------------------------------------------- #
# 文本辅助:买卖方名称(#3 全角冒号)、大写金额(#6 精确匹配)、发票类型(#4)
# --------------------------------------------------------------------------- #


def _extract_party_names_from_objs(objs: list[TextObj]) -> tuple[str, str]:
    """从 TextObject 块列表提取买卖方名称(#3 半角/全角冒号)。

    OFD 的标签与值通常在同一个 TextObject 内(如"名称:XXX"),
    因此逐块按冒号切分,而非全文 join 后匹配(避免跨块粘连)。
    """
    hits: list[str] = []
    for o in objs:
        t = o["text"]
        for lab in ("名称:", "名称："):
            if lab in t:
                val = t.split(lab, 1)[1].strip()
                # 同块内若冒号后还有其它标签,裁掉
                for stop in ("名称:", "名称：", "识别号:", "识别号："):
                    if stop in val:
                        val = val.split(stop, 1)[0].strip()
                if val:
                    hits.append(val)
                break
    seller = hits[0] if len(hits) >= 1 else ""
    buyer = hits[1] if len(hits) >= 2 else ""
    return seller, buyer


# 大写金额正则:必须以 圆/元/整 结尾,避免误匹配"备注:壹元"这类短干扰
_AMOUNT_CN_RE = re.compile(r"[\u4e00-\u9fa5]{2,}(?:圆|元)(?:[\u4e00-\u9fa5]*)(?:角|整)?")


def _extract_amount_chinese(texts: list[str]) -> str:
    """从文本里找大写金额。收紧匹配(#6):必须像'壹仟...圆/元...[角/整]'。"""
    for t in texts:
        # 跳过含"备注"上下文的行,避免备注里的金额描述误匹配
        if "备注" in t:
            continue
        if not any(k in t for k in ("圆", "元")):
            continue
        m = _AMOUNT_CN_RE.search(t)
        if m:
            return m.group(0).strip()
    return ""


def _extract_invoice_type(texts: list[str], custom: dict[str, str]) -> str:
    """发票类型(#4):优先从标题文本识别,回退到 CustomData,再回退'电子发票'。

    识别常见标题:'电子发票(增值税专用发票)'、'增值税电子普通发票'等。
    """
    for t in texts:
        if ("增值税" in t and ("专用" in t or "普通" in t)) or "电子发票" in t:
            # 取整行作为类型(去掉首尾空白/括号变体)
            return t.strip()
    return custom.get("发票类型", "电子发票")


# --------------------------------------------------------------------------- #
# 金额兜底(#5):价税合计缺失时用 不含税 + 税额 补算
# --------------------------------------------------------------------------- #


def _safe_add(a: str, b: str) -> str:
    """两个金额字符串相加,保留两位小数;任一非法返回空串。"""
    try:
        return f"{round(float(a) + float(b), 2):.2f}"
    except (ValueError, TypeError):
        return ""


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #


def parse_ofd(path: Path, source_file: str = "") -> Invoice:
    """解析 OFD 发票文件(仅首张 DocBody)。

    Raises UnsupportedFormatError: 文件不存在 / 非 ZIP / 缺 OFD.xml。
    """
    path = Path(path)
    if not path.exists():
        raise UnsupportedFormatError(f"文件不存在: {path}")
    try:
        with zipfile.ZipFile(path, "r") as zf:
            ofd_xml = _read_zip_member(zf, "OFD.xml")
            if not ofd_xml:
                raise UnsupportedFormatError("OFD 缺少 OFD.xml")

            # DocRoot 路径(如 Doc_0/Document.xml),用于按 BaseLoc 精确定位多页 Content
            doc_root = _parse_first_doc_root(ofd_xml)
            content_xmls = _collect_content_xmls(zf, doc_root)
    except zipfile.BadZipFile as e:
        raise UnsupportedFormatError(f"OFD 不是有效 ZIP: {e}") from e

    custom = _parse_custom_data(ofd_xml)

    # 合并所有页的 TextObject(多页发票 #7)
    all_objs: list[TextObj] = []
    all_texts: list[str] = []
    for cx in content_xmls:
        all_objs.extend(_parse_text_objects(cx))
        all_texts.extend(_parse_content_texts(cx))

    seller_name, buyer_name = _extract_party_names_from_objs(all_objs)
    amount_chinese = _extract_amount_chinese(all_texts)
    invoice_type = _extract_invoice_type(all_texts, custom)
    items = _extract_detail_items(all_objs)

    amount_without_tax = custom.get("合计金额", "")
    tax_amount = custom.get("合计税额", "")
    amount_with_tax = custom.get("价税合计", "")
    # #5 价税合计缺失时,用 不含税 + 税额 兜底
    if not amount_with_tax and amount_without_tax and tax_amount:
        amount_with_tax = _safe_add(amount_without_tax, tax_amount)

    return Invoice(
        invoice_number=custom.get("发票号码", ""),
        invoice_type=invoice_type,
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
        amount_without_tax=amount_without_tax,
        tax_amount=tax_amount,
        amount_with_tax=amount_with_tax,
        amount_chinese=amount_chinese,
        drawer=custom.get("开票人", ""),
        remark=custom.get("备注", ""),
        items=items,
        source_file=source_file or path.name,
        parse_method="ofd",
    )


def _parse_first_doc_root(ofd_xml: str) -> str:
    """从 OFD.xml 取首个 DocBody 的 DocRoot 路径(如 'Doc_0/Document.xml')。"""
    try:
        root = ET.fromstring(ofd_xml)
    except ET.ParseError:
        return ""
    for dr in root.iter(f"{OFD_NS}DocRoot"):
        if dr.text:
            return dr.text.strip()
    return ""
