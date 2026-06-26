"""PDF 发票解析(pdfplumber text 策略,尽力而为)。

已知难点:明细行数不固定(动态定位表头/表尾)、规格可能为空(空单元格)、跨行明细。
方案:text 策略聚列 + 列索引固定映射 + 合并续行。PDF 是纯版式文档,无结构化数据,
所以本解析为尽力而为,置信度低(parse_method="pdf")。
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
_TOTAL_KEYWORDS = ("合计",)

# 明细列的 x 中心锚点(经验值,适配税务局标准版式)。
# 用 extract_words 的 x0 落到哪个区间判定该 word 属于哪列。
# 区间为左闭右开,边界取相邻列锚点中点。
_COL_ANCHORS = [  # (列名, 锚点 x0)
    ("name", 50),
    ("spec", 190),
    ("unit", 250),
    ("quantity", 290),
    ("unit_price", 330),
    ("amount", 380),
    ("tax_rate", 430),
    ("tax_amount", 470),
]

# 构造列分界:每列的 x 范围 = [本列锚点, 下一列锚点);最后一列到无穷
_COL_RANGES: list[tuple[str, float, float]] = []
for i, (col_name, anchor) in enumerate(_COL_ANCHORS):
    nxt = _COL_ANCHORS[i + 1][1] if i + 1 < len(_COL_ANCHORS) else float("inf")
    # 列范围起点取本列锚点与上一列锚点的中点(允许文字略左偏)
    prev = _COL_ANCHORS[i - 1][1] if i > 0 else 0
    start = (anchor + prev) / 2 if i > 0 else anchor - 20
    _COL_RANGES.append((col_name, start, nxt))

_COL_ORDER = [c for c, _, _ in _COL_RANGES]
_COL_BY_NAME = {name: (lo, hi) for name, lo, hi in _COL_RANGES}


def _column_of(x0: float) -> str:
    """根据 word 的 x0 返回它属于的列名;落不进任何列归到最接近的。"""
    for name, lo, hi in _COL_RANGES:
        if lo <= x0 < hi:
            return name
    # 最接近哪列锚点
    best = min(_COL_ANCHORS, key=lambda a: abs(x0 - a[1]))
    return best[0]


def _find_all_label_values(full_text: str, labels: list[str]) -> list[str]:
    """在全文里查找 labels 中任一标签,返回各次出现后紧跟的值。

    值 = 标签之后、到下一个已知标签(或换行)之前的文本。
    用于一行内含多个同类标签(如'名称:X 名称:Y')的情况。
    多个 labels 可能互为后缀(如'识别号:'是'...识别号:'的后缀),同一处会被
    多次命中 -> 用区间去重:若某次命中被前一次完全包含,跳过。
    """
    hits: list[tuple[int, int]] = []  # (起始位置, 标签结束位置)
    for lab in labels:
        idx = 0
        while True:
            pos = full_text.find(lab, idx)
            if pos == -1:
                break
            hits.append((pos, pos + len(lab)))
            idx = pos + len(lab)
    hits.sort()

    # 去除被包含的命中(长标签覆盖短后缀标签)
    deduped: list[tuple[int, int]] = []
    for start, end in hits:
        if any(s <= start and end <= e2 and (s, e2) != (start, end) for s, e2 in deduped):
            continue
        # 同一起点保留最长那个:若已有同起点但更短,替换
        replaced = False
        for i, (s, e2) in enumerate(deduped):
            if s == start:
                if end > e2:
                    deduped[i] = (start, end)
                replaced = True
                break
        if not replaced:
            deduped.append((start, end))

    values: list[str] = []
    for i, (start, end) in enumerate(deduped):
        tail_end = deduped[i + 1][0] if i + 1 < len(deduped) else len(full_text)
        val = full_text[end:tail_end].strip()
        # 同行内若有两个标签无分隔,值可能带上下文;裁到第一个换行
        val = val.split("\n", 1)[0].strip()
        values.append(val)
    return values


def _extract_detail_items_from_words(page) -> list[LineItem]:
    """用 extract_words + x 坐标聚列提取明细。

    比依赖 extract_tables 的列检测更稳定(后者对整页文字密度敏感)。
    流程:按 y 分行 -> 定位表头行 -> 每行按 x 落列 -> 合并续行。
    空单元格(spec 缺失)因无 word 落入该列,自动为 ""。
    """
    words = page.extract_words()
    if not words:
        return []

    # 按 y(top)分行,3pt 容差;同一行的 word 按列归并
    rows: dict[int, list] = {}
    keys_in_order: list[int] = []
    for w in words:
        key = round(w["top"] / 3)
        if key not in rows:
            rows[key] = []
            keys_in_order.append(key)
        rows[key].append(w)

    # 定位表头行(含'项目名称'和'规格型号')
    start_idx = None
    for i, key in enumerate(keys_in_order):
        row_text = "".join(w["text"] for w in rows[key])
        if all(kw in row_text for kw in _HEADER_KEYWORDS):
            start_idx = i + 1
            break
    if start_idx is None:
        start_idx = 0

    items: list[LineItem] = []
    for key in keys_in_order[start_idx:]:
        ws = rows[key]
        row_text = "".join(w["text"] for w in ws)
        # 合计行结束
        if any(kw in row_text for kw in _TOTAL_KEYWORDS):
            break

        # 按列归并 word
        col_vals: dict[str, list[str]] = {c: [] for c in _COL_ORDER}
        for w in sorted(ws, key=lambda x: x["x0"]):
            col = _column_of(w["x0"])
            col_vals[col].append(w["text"])

        def join(col: str) -> str:
            return "".join(col_vals.get(col, []))

        name = join("name")
        if not name:
            continue

        # 续行:只有 name/spec 列有值,其余空 -> 合并到上一条
        tail_empty = all(
            not join(c) for c in ("unit", "quantity", "unit_price", "amount", "tax_rate", "tax_amount")
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


def _extract_invoice_number(lines: list[str]) -> str:
    for ln in lines:
        if "发票号码" in ln:
            m = re.search(r"(\d{18,})", ln.replace(" ", ""))
            if m:
                return m.group(1)
    # fallback:任意 18+ 位数字
    for ln in lines:
        m = re.search(r"(\d{18,})", ln.replace(" ", ""))
        if m:
            return m.group(1)
    return ""


def _extract_party_names(full_text: str) -> tuple[str, str]:
    """按'名称:'在全文出现顺序取买卖方名称(容忍同行两个标签)。"""
    hits = _find_all_label_values(full_text, ["名称:", "名称："])
    seller = hits[0] if len(hits) >= 1 else ""
    buyer = hits[1] if len(hits) >= 2 else ""
    return seller, buyer


def _extract_tax_ids(full_text: str) -> tuple[str, str]:
    """按识别号标签在全文出现顺序取买卖方税号(容忍同行两个标签)。"""
    pats = [
        "统一社会信息代码/纳税人识别号:",
        "统一社会信息代码/纳税人识别号：",
        "纳税人识别号:",
        "纳税人识别号：",
        "识别号:",
        "识别号：",
    ]
    hits = _find_all_label_values(full_text, pats)
    seller = hits[0] if len(hits) >= 1 else ""
    buyer = hits[1] if len(hits) >= 2 else ""
    return seller, buyer


def _extract_amounts(lines: list[str], full_text: str) -> tuple[str, str, str]:
    """从文本提取 不含税金额/税额/价税合计。"""
    amount_without_tax = ""
    tax_amount = ""
    amount_with_tax = ""

    for ln in lines:
        if "合计" in ln and "价税合计" not in ln and not amount_without_tax:
            nums = re.findall(r"([\d]+\.\d{2})", ln)
            if len(nums) >= 2:
                amount_without_tax = nums[0]
                tax_amount = nums[1]
        if "价税合计" in ln or "小写" in ln:
            nums = re.findall(r"([\d]+\.\d{2})", ln)
            if nums:
                amount_with_tax = nums[-1]
    return amount_without_tax, tax_amount, amount_with_tax


def _extract_amount_chinese(lines: list[str]) -> str:
    """提取大写金额(含 圆/元/角/分/整 的中文串)。"""
    for ln in lines:
        if "价税合计" in ln and any(k in ln for k in ("圆", "元", "角", "分", "整")):
            m = re.search(r"([\u4e00-\u9fa5]{2,}(?:圆|元)(?:[\u4e00-\u9fa5]*))", ln)
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

        # 用 extract_words + x 坐标聚列提取明细(比 extract_tables 稳定)
        items = _extract_detail_items_from_words(page)

        invoice_number = _extract_invoice_number(lines)
        seller_name, buyer_name = _extract_party_names(full_text)
        seller_tax_id, buyer_tax_id = _extract_tax_ids(full_text)
        amount_without_tax, tax_amount, amount_with_tax = _extract_amounts(lines, full_text)
        amount_chinese = _extract_amount_chinese(lines)

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
