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
                # 选优先级最高(数字最小);同优先级取索引最小(首个)
                best = min(range(len(grp)), key=lambda i: _method_rank(grp[i].parse_method))
                kept.append(grp[best])
                dups.extend(grp[:best] + grp[best + 1 :])
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
