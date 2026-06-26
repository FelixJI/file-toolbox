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
    assert dup_flags.count(True) == 2          # ofd 和 pdf 标
    assert dup_flags.count(False) == 1         # xml 不标
