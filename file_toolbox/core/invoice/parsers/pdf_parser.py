"""PDF 发票解析(pdfplumber word 坐标策略)。

核心思路(经真实发票验证):
- 所有结构化字段从 extract_words() 的坐标提取,不依赖 extract_text() 的全文拼接
- 明细列锚点从表头行 word 动态学习(_learn_columns),告别硬编码
- 数据 word 用中心 (x0+x1)/2 找最近表头列,避免长数字误归邻列
- 买卖方优先用竖排"购/销"标签定位,找不到才退回"名称出现顺序"

已知难点:版式差异(连写/拆字表头)、跨行商品名、空单元格。本解析为尽力而为,
置信度低(parse_method="pdf")。
"""

import re
from pathlib import Path

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.types import Invoice, LineItem

# pdfplumber 延迟导入,缺依赖给友好提示
try:
    import pdfplumber
except ImportError as e:
    raise ImportError("PDF 解析需要 pdfplumber: pip install 'file-toolbox[invoice]'") from e


# --------------------------------------------------------------------------- #
# 硬编码列锚点:动态学习失败时的保底值
# --------------------------------------------------------------------------- #
_FALLBACK_ANCHORS: list[tuple[str, float]] = [
    ("name", 50),
    ("spec", 190),
    ("unit", 250),
    ("quantity", 290),
    ("unit_price", 330),
    ("amount", 380),
    ("tax_rate", 430),
    ("tax_amount", 470),
]

_HEADER_KEYWORDS = ("项目名称", "规格型号")
_TOTAL_KEYWORDS = ("合计",)

# 表头单字标题 -> 所属列(用于把"单"+"位"这种拆字表头归并成一列)
_SINGLE_CHAR_COL: dict[str, str] = {
    "单": None,  # 候选 unit/unit_price,靠后续字确定
    "位": "unit",
    "数": None,  # 候选 quantity
    "量": "quantity",
    "价": "unit_price",
    "金": None,  # 候选 amount
    "额": "amount",
    "税": None,  # 候选 tax_rate/tax_amount
}


def _word_center(w: dict) -> float:
    """word 的水平中心。判列用中心而非 x0,避免长数字误归邻列。"""
    return (w["x0"] + w["x1"]) / 2


# --------------------------------------------------------------------------- #
# 动态列锚点:从表头行 word 学习每列的中心 x
# --------------------------------------------------------------------------- #


def _learn_columns(header_words: list[dict]) -> dict[str, float]:
    """从表头行 word 动态学习各列中心 x。

    兼容两种形态:
    - 连写: 一个 word "单位"/"数量"(fixture 形态)
    - 拆字: "单"+"位" 两个相邻 word(真实发票形态)

    返回 {列名: center_x}。学不全时,缺失列用 _FALLBACK_ANCHORS 补。
    """
    cols: dict[str, float] = {}
    # 按出现顺序遍历(已按 x 排序更稳)
    sorted_words = sorted(header_words, key=lambda w: w["x0"])

    pending_single: str | None = None  # 上一个待定的单字(如"单"待"位"确认)
    for w in sorted_words:
        text = w["text"].strip()
        cx = _word_center(w)

        if text == "项目名称":
            cols["name"] = cx
            pending_single = None
        elif text == "规格型号":
            cols["spec"] = cx
            pending_single = None
        elif "税率" in text:
            cols["tax_rate"] = cx
            pending_single = None
        elif text == "单位":
            cols["unit"] = cx
            pending_single = None
        elif text == "数量":
            cols["quantity"] = cx
            pending_single = None
        elif text == "单价":
            cols["unit_price"] = cx
            pending_single = None
        elif text == "金额":
            cols["amount"] = cx
            pending_single = None
        elif text == "税额":
            cols["tax_amount"] = cx
            pending_single = None
        elif text == "单":
            pending_single = "unit_or_price"  # 待"位"或"价"确认
        elif text == "数":
            pending_single = "quantity"
        elif text == "金":
            pending_single = "amount"
        elif text == "位" and pending_single == "unit_or_price":
            # "单"+"位" -> unit,中心取两者中点
            prev = cols.get("_pending_unit_single_cx")
            cols["unit"] = (prev + cx) / 2 if prev else cx
            pending_single = None
        elif text == "价" and pending_single == "unit_or_price":
            prev = cols.get("_pending_unit_single_cx")
            cols["unit_price"] = (prev + cx) / 2 if prev else cx
            pending_single = None
        elif text == "量" and pending_single == "quantity":
            prev = cols.get("_pending_unit_single_cx")
            cols["quantity"] = (prev + cx) / 2 if prev else cx
            pending_single = None
        elif text == "额" and pending_single == "amount":
            prev = cols.get("_pending_unit_single_cx")
            cols["amount"] = (prev + cx) / 2 if prev else cx
            pending_single = None
        elif text == "额" and pending_single == "tax":
            prev = cols.get("_pending_unit_single_cx")
            cols["tax_amount"] = (prev + cx) / 2 if prev else cx
            pending_single = None
        elif text == "税":
            pending_single = "tax"
            cols["_pending_unit_single_cx"] = cx

        if pending_single in ("unit_or_price", "quantity", "amount", "tax"):
            cols["_pending_unit_single_cx"] = cx

    cols.pop("_pending_unit_single_cx", None)

    # 缺失列用保底锚点补
    fallback = dict(_FALLBACK_ANCHORS)
    for col, cx in fallback.items():
        if col not in cols:
            cols[col] = cx
    return cols


def _column_of(w: dict, col_centers: dict[str, float]) -> str:
    """根据 word 中心找最近的表头列名。"""
    cx = _word_center(w)
    best_col = min(col_centers, key=lambda c: abs(cx - col_centers[c]))
    return best_col


# --------------------------------------------------------------------------- #
# Y 分行聚类(保留原逻辑)
# --------------------------------------------------------------------------- #


def _group_rows(words: list[dict]) -> tuple[dict[int, list[dict]], list[int]]:
    """按 top 分行(3pt 容差)。返回 ({y_key: [words]}, 有序 y_keys)。"""
    rows: dict[int, list[dict]] = {}
    keys_in_order: list[int] = []
    for w in words:
        key = round(w["top"] / 3)
        if key not in rows:
            rows[key] = []
            keys_in_order.append(key)
        rows[key].append(w)
    return rows, keys_in_order


# --------------------------------------------------------------------------- #
# 明细行提取(动态列锚点 + word 中心判列 + 续行合并)
# --------------------------------------------------------------------------- #


def _extract_detail_items(words: list[dict], col_centers: dict[str, float]) -> list[LineItem]:
    """用 word 坐标提取明细。比依赖 extract_tables 的列检测更稳定。

    流程:按 y 分行 -> 定位表头行 -> 动态学列锚点 -> 每行按 word 中心落列 -> 合并续行。
    空单元格(spec 缺失)因无 word 落入该列,自动为 ""。
    """
    if not words:
        return []

    rows, keys_in_order = _group_rows(words)

    # 定位表头行(含'项目名称'和'规格型号')
    start_idx = None
    for i, key in enumerate(keys_in_order):
        row_text = "".join(w["text"] for w in rows[key])
        if all(kw in row_text for kw in _HEADER_KEYWORDS):
            start_idx = i + 1
            break
    if start_idx is None:
        start_idx = 0

    col_order = [
        "name",
        "spec",
        "unit",
        "quantity",
        "unit_price",
        "amount",
        "tax_rate",
        "tax_amount",
    ]

    items: list[LineItem] = []
    for key in keys_in_order[start_idx:]:
        ws = rows[key]
        row_text = "".join(w["text"] for w in ws)
        # 合计行结束
        if any(kw in row_text for kw in _TOTAL_KEYWORDS):
            break

        # 按列归并 word
        col_vals: dict[str, list[str]] = {c: [] for c in col_order}
        for w in sorted(ws, key=lambda x: x["x0"]):
            col_vals[_column_of(w, col_centers)].append(w["text"])

        def join(col: str, col_vals: dict[str, list[str]] = col_vals) -> str:
            return "".join(col_vals.get(col, []))

        name = join("name")
        if not name:
            continue

        # 续行:只有 name/spec 列有值,其余空 -> 合并到上一条
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
# 发票号码/日期(从 word 行提取,容忍空格)
# --------------------------------------------------------------------------- #


def _extract_invoice_number(rows: dict[int, list[dict]], keys: list[int]) -> str:
    """从含'发票号码'的行提取 18+ 位数字。"""
    for key in keys:
        row_text = "".join(w["text"] for w in rows[key])
        if "发票号码" in row_text:
            m = re.search(r"(\d{18,})", row_text)
            if m:
                return m.group(1)
    # fallback:任意 18+ 位数字
    for key in keys:
        for w in rows[key]:
            m = re.search(r"(\d{18,})", w["text"])
            if m:
                return m.group(1)
    return ""


def _extract_issue_date(rows: dict[int, list[dict]], keys: list[int]) -> str:
    """提取开票日期 YYYY-MM-DD(容忍'YYYY年MM月DD日')。"""
    for key in keys:
        for w in rows[key]:
            m = re.search(r"(\d{4})\s*年\s*(\d{2})\s*月\s*(\d{2})\s*日", w["text"])
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


# --------------------------------------------------------------------------- #
# 买卖方与税号(优先竖排"购/销"标签定位,退回出现顺序)
# --------------------------------------------------------------------------- #

_TAX_LABELS = (
    "统一社会信息代码/纳税人识别号:",
    "统一社会信息代码/纳税人识别号：",
    "统一社会信用代码/纳税人识别号:",
    "统一社会信用代码/纳税人识别号：",
    "纳税人识别号:",
    "纳税人识别号：",
    "识别号:",
    "识别号：",
)


def _find_label_word(
    rows: dict[int, list[dict]], keys: list[int], labels: tuple[str, ...]
) -> list[tuple[float, str]]:
    """在所有行找含 labels 任一的 word,返回 [(x0, 冒号后的值)]。"""
    hits: list[tuple[float, str]] = []
    for key in keys:
        for w in rows[key]:
            t = w["text"]
            for lab in labels:
                pos = t.find(lab)
                if pos != -1:
                    val = t[pos + len(lab) :].strip()
                    # 裁掉同行可能粘的后续标签
                    for stop_lab in labels:
                        sp = val.find(stop_lab)
                        if sp != -1:
                            val = val[:sp].strip()
                    if val:
                        hits.append((w["x0"], val))
                    break
    return hits


def _extract_party_by_label(words_grouped: tuple[dict, list]) -> tuple[str, str]:
    """优先用竖排'购/销'标签定位买卖方。返回 (seller_name, buyer_name)。

    真实发票有竖排'购买方'(左) / '销售方'(右) 标签字;
    找不到则退回按'名称:'出现顺序(第一个=销售方,兼容 fixture)。
    """
    rows, keys = words_grouped
    # 找'购'和'销'竖排标签的 x 坐标
    gou_x: list[float] = []
    xiao_x: list[float] = []
    for key in keys:
        for w in rows[key]:
            if w["text"] == "购":
                gou_x.append(w["x0"])
            elif w["text"] == "销":
                xiao_x.append(w["x0"])
    gou_x_med = sorted(gou_x)[len(gou_x) // 2] if gou_x else None
    xiao_x_med = sorted(xiao_x)[len(xiao_x) // 2] if xiao_x else None

    name_hits = _find_label_word(rows, keys, ("名称:", "名称："))
    if not name_hits:
        return "", ""

    if gou_x_med is not None and xiao_x_med is not None:
        # 有购/销标签:按 x 区分。购=买方,销=卖方。
        # '名称'word 的 x0 与最近的标签 x 匹配
        seller = buyer = ""
        for x0, val in name_hits:
            if abs(x0 - xiao_x_med) < abs(x0 - gou_x_med):
                seller = val
            else:
                buyer = val
        return seller, buyer

    # 退回:第一个名称=销售方,第二个=购买方(兼容 fixture)
    seller = name_hits[0][1] if len(name_hits) >= 1 else ""
    buyer = name_hits[1][1] if len(name_hits) >= 2 else ""
    return seller, buyer


def _extract_tax_ids(words_grouped: tuple[dict, list]) -> tuple[str, str]:
    """提取买卖方税号。优先用购/销标签 x 定位,退回出现顺序。"""
    rows, keys = words_grouped
    gou_x: list[float] = []
    xiao_x: list[float] = []
    for key in keys:
        for w in rows[key]:
            if w["text"] == "购":
                gou_x.append(w["x0"])
            elif w["text"] == "销":
                xiao_x.append(w["x0"])
    gou_x_med = sorted(gou_x)[len(gou_x) // 2] if gou_x else None
    xiao_x_med = sorted(xiao_x)[len(xiao_x) // 2] if xiao_x else None

    tax_hits = _find_label_word(rows, keys, _TAX_LABELS)
    if not tax_hits:
        return "", ""

    if gou_x_med is not None and xiao_x_med is not None:
        seller = buyer = ""
        for x0, val in tax_hits:
            if abs(x0 - xiao_x_med) < abs(x0 - gou_x_med):
                seller = val
            else:
                buyer = val
        return seller, buyer

    seller = tax_hits[0][1] if len(tax_hits) >= 1 else ""
    buyer = tax_hits[1][1] if len(tax_hits) >= 2 else ""
    return seller, buyer


# --------------------------------------------------------------------------- #
# 金额提取(逐行 word,容忍中文间空格)
# --------------------------------------------------------------------------- #


def _row_join_no_space(ws: list[dict]) -> str:
    """把一行 word 的 text 直接拼接(不加空格),解决'合 计'拆字问题。"""
    return "".join(w["text"] for w in ws)


def _extract_amounts(rows: dict[int, list[dict]], keys: list[int]) -> tuple[str, str, str]:
    """从行 word 提取 不含税金额/税额/价税合计。

    合计行判定:拼接后含'合计'(去空格后匹配,容忍'合 计')且不含'价税合计'。
    价税合计:与'价税合计(大写)'标签可能分在相邻 y 行,向后看 1-2 行找金额。
    """
    amount_without_tax = ""
    tax_amount = ""
    amount_with_tax = ""

    for key in keys:
        ws = rows[key]
        joined = _row_join_no_space(ws)
        if not amount_without_tax and "合计" in joined and "价税合计" not in joined:
            nums = re.findall(r"([\d,]+\.\d{2})", joined)
            if len(nums) >= 2:
                amount_without_tax = nums[0].replace(",", "")
                tax_amount = nums[1].replace(",", "")
        if "价税合计" in joined or "小写" in joined:
            # 本行有金额就用本行;否则向后看 1-2 行(标签与金额可能分行)
            nums = re.findall(r"([\d,]+\.\d{2})", joined)
            if nums:
                amount_with_tax = nums[-1].replace(",", "")
            else:
                amount_with_tax = _find_amount_in_next_rows(rows, keys, key, 2)

    # 兜底:若价税合计仍未取到,扫描含'小写'或紧跟合计行后的金额行
    if not amount_with_tax:
        for key in keys:
            joined = _row_join_no_space(rows[key])
            if "小写" in joined:
                amount_with_tax = _find_amount_in_next_rows(rows, keys, key, 2)
                if amount_with_tax:
                    break
    return amount_without_tax, tax_amount, amount_with_tax


def _find_amount_in_next_rows(
    rows: dict[int, list[dict]], keys: list[int], start_key: int, look: int = 2
) -> str:
    """从 start_key 之后 look 个 y 行里找第一个金额数字(x.x​x)。

    价税合计的金额常与'(大写)'标签分在不同 y 行(如标签在 y=143,¥23480.52 在 y=142)。
    """
    try:
        idx = keys.index(start_key)
    except ValueError:
        return ""
    for key in keys[idx + 1 : idx + 1 + look]:
        for w in rows[key]:
            m = re.search(r"([\d,]+\.\d{2})", w["text"])
            if m:
                return m.group(1).replace(",", "")
    # 向前也看 1 行(金额行可能在标签行上方)
    if idx > 0:
        for w in rows[keys[idx - 1]]:
            m = re.search(r"([\d,]+\.\d{2})", w["text"])
            if m:
                return m.group(1).replace(",", "")
    return ""


def _extract_amount_chinese(rows: dict[int, list[dict]], keys: list[int]) -> str:
    """提取大写金额(含 圆/元/角/分/整 的中文串)。"""
    for key in keys:
        ws = rows[key]
        joined = _row_join_no_space(ws)
        if "价税合计" in joined and any(k in joined for k in ("圆", "元", "角", "分", "整")):
            m = re.search(r"([\u4e00-\u9fa5]{2,}(?:圆|元)(?:[\u4e00-\u9fa5]*))", joined)
            if m:
                return m.group(1)
    return ""


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #


def parse_pdf(path: Path, source_file: str = "") -> Invoice:
    """解析 PDF 发票。尽力而为,置信度低。"""
    path = Path(path)
    if not path.exists():
        raise UnsupportedFormatError(f"文件不存在: {path}")

    with pdfplumber.open(str(path)) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(x_tolerance=2, y_tolerance=2)

        rows, keys = _group_rows(words)

        # 动态学列锚点:从表头行 word 学,失败用保底值
        header_words: list[dict] = []
        for key in keys:
            row_text = "".join(w["text"] for w in rows[key])
            if all(kw in row_text for kw in _HEADER_KEYWORDS):
                header_words = rows[key]
                break
        col_centers = _learn_columns(header_words)

        items = _extract_detail_items(words, col_centers)

        invoice_number = _extract_invoice_number(rows, keys)
        issue_date = _extract_issue_date(rows, keys)
        seller_name, buyer_name = _extract_party_by_label((rows, keys))
        seller_tax_id, buyer_tax_id = _extract_tax_ids((rows, keys))
        amount_without_tax, tax_amount, amount_with_tax = _extract_amounts(rows, keys)
        amount_chinese = _extract_amount_chinese(rows, keys)

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
