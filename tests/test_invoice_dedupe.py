from file_toolbox.core.invoice.dedupe import DEDUPE, KEEP_ALL, MARK, dedupe_invoices
from file_toolbox.core.invoice.types import Invoice


def _make(num: str, method: str = "xml") -> Invoice:
    return Invoice(
        invoice_number=num,
        invoice_type="增值税专用发票",
        issue_date="2026-05-19",
        seller_name="s",
        seller_tax_id="s",
        seller_addr="s",
        seller_tel="s",
        seller_bank="s",
        seller_account="s",
        buyer_name="b",
        buyer_tax_id="b",
        buyer_addr="b",
        buyer_tel="b",
        buyer_bank="b",
        buyer_account="b",
        amount_without_tax="1",
        tax_amount="1",
        amount_with_tax="2",
        amount_chinese="x",
        drawer="d",
        remark="",
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
    assert dup_flags.count(True) == 2  # ofd 和 pdf 标
    assert dup_flags.count(False) == 1  # xml 不标


# ---------------------------------------------------------------------------
# 边界:同优先级并列 / 空号误并 / 未知策略兜底 —— 锁定当前行为
# ---------------------------------------------------------------------------


def test_dedupe_same_priority_tie_keeps_first():
    """同优先级(同为 xml)的同号发票 → 保留索引最小(首个)。min 在并列时取首个。"""
    invs = [_make("A", "xml"), _make("A", "xml")]
    kept, dups = dedupe_invoices(invs, DEDUPE)
    assert len(kept) == 1
    assert kept[0] is invs[0]  # 首个


def test_dedupe_empty_invoice_numbers_currently_collapse():
    """两张**不同**发票但 invoice_number 都为空(提取失败)→ 当前被误并为同组去重。

    锁定当前行为(已知风险):空号分组键相同,dedupe 会丢弃其一 → 不同发票被静默合并。
    未来若修复(如空号不去重),该测试应变红提醒有意更新。
    """
    invs = [_make("", "pdf"), _make("", "pdf")]
    kept, dups = dedupe_invoices(invs, DEDUPE)
    assert len(kept) == 1  # 当前:误并,只剩 1 张
    assert len(dups) == 1


def test_dedupe_unknown_strategy_falls_back_to_keep_all():
    """未知策略 → 回退 keep_all 语义(全部保留,无 duplicates)。"""
    invs = [_make("A"), _make("A")]
    kept, dups = dedupe_invoices(invs, "bogus")
    assert len(kept) == 2
    assert len(dups) == 0
