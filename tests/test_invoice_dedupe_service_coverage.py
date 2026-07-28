"""dedupe / invoice service 边界补充测试。

覆盖:
- dedupe_invoices 未知策略 → keep_all 行为(行 70)
- dedupe _method_rank 未知方式排最后(行 18)
- InvoiceService.parse_files 通用异常(非 UnsupportedFormatError)记为失败(行 35-36)
- InvoiceService.supported_dedupe_strategies / supported_formats(行 63, 68)
- InvoiceService.export fmt='both' 与 json_path 默认
"""

from file_toolbox.core.invoice.dedupe import (
    DEDUPE,
    KEEP_ALL,
    MARK,
    _method_rank,
    dedupe_invoices,
)
from file_toolbox.core.invoice.service import InvoiceService
from file_toolbox.core.invoice.types import Invoice, ParseResult


def _inv(num: str, method: str = "xml") -> Invoice:
    return Invoice(
        invoice_number=num,
        invoice_type="",
        issue_date="",
        seller_name="",
        seller_tax_id="",
        seller_addr="",
        seller_tel="",
        seller_bank="",
        seller_account="",
        buyer_name="",
        buyer_tax_id="",
        buyer_addr="",
        buyer_tel="",
        buyer_bank="",
        buyer_account="",
        amount_without_tax="",
        tax_amount="",
        amount_with_tax="",
        amount_chinese="",
        drawer="",
        remark="",
        items=[],
        source_file=f"{num}.xml",
        parse_method=method,
    )


# ---------------------------------------------------------------------------
# dedupe:未知策略(行 70)
# ---------------------------------------------------------------------------


def test_dedupe_unknown_strategy_defaults_to_keep_all():
    invs = [_inv("1"), _inv("1"), _inv("2")]
    kept, dups = dedupe_invoices(invs, "bogus_strategy")
    assert len(kept) == 3
    assert dups == []


# ---------------------------------------------------------------------------
# _method_rank:未知方式
# ---------------------------------------------------------------------------


def test_method_rank_known():
    assert _method_rank("xml") == 0
    assert _method_rank("ofd") == 1
    assert _method_rank("pdf") == 2


def test_method_rank_unknown_is_last():
    assert _method_rank("bogus") == 99
    assert _method_rank("xml") < _method_rank("bogus")


# ---------------------------------------------------------------------------
# dedupe:keep_all 原样返回
# ---------------------------------------------------------------------------


def test_dedupe_keep_all_no_change():
    invs = [_inv("1"), _inv("1")]
    kept, dups = dedupe_invoices(invs, KEEP_ALL)
    assert len(kept) == 2
    assert dups == []


# ---------------------------------------------------------------------------
# dedupe:dedupe 策略优先级
# ---------------------------------------------------------------------------


def test_dedupe_strategy_keeps_highest_priority():
    """同号 xml/ofd/pdf → 保留 xml,其余进 dups。"""
    invs = [_inv("1", "pdf"), _inv("1", "xml"), _inv("1", "ofd")]
    kept, dups = dedupe_invoices(invs, DEDUPE)
    assert len(kept) == 1
    assert kept[0].parse_method == "xml"
    assert len(dups) == 2


def test_dedupe_strategy_single_unchanged():
    invs = [_inv("1"), _inv("2")]
    kept, dups = dedupe_invoices(invs, DEDUPE)
    assert len(kept) == 2
    assert dups == []


# ---------------------------------------------------------------------------
# dedupe:mark 策略
# ---------------------------------------------------------------------------


def test_dedupe_mark_strategy_flags_duplicates():
    invs = [_inv("1", "pdf"), _inv("1", "xml")]
    kept, dups = dedupe_invoices(invs, MARK)
    assert len(kept) == 2
    assert dups == []
    dup_flags = [i.is_duplicate for i in kept]
    assert True in dup_flags and False in dup_flags


def test_dedupe_mark_single_not_flagged():
    invs = [_inv("1", "xml"), _inv("2", "xml")]
    kept, _ = dedupe_invoices(invs, MARK)
    assert all(not i.is_duplicate for i in kept)


# ---------------------------------------------------------------------------
# InvoiceService.parse_files:通用异常(行 35-36)
# ---------------------------------------------------------------------------


def test_service_parse_files_generic_exception_recorded(tmp_path, monkeypatch):
    """非 UnsupportedFormatError 异常 → 记为失败(行 35-36)。"""
    import file_toolbox.core.invoice.service as svc_mod

    def boom(_path, source_file=""):
        raise ValueError("unexpected boom")

    monkeypatch.setattr(svc_mod, "parse_invoice", boom)
    f = tmp_path / "a.xml"
    f.write_text("x", encoding="utf-8")
    result = InvoiceService().parse_files([f])
    assert len(result.failed) == 1
    assert "ValueError" in result.failed[0].reason
    assert "boom" in result.failed[0].reason


# ---------------------------------------------------------------------------
# InvoiceService.supported_*(行 63, 68)
# ---------------------------------------------------------------------------


def test_service_supported_dedupe_strategies():
    strategies = InvoiceService.supported_dedupe_strategies()
    assert KEEP_ALL in strategies
    assert DEDUPE in strategies
    assert MARK in strategies


def test_service_supported_formats():
    fmts = InvoiceService.supported_formats()
    assert "excel" in fmts
    assert "json" in fmts
    assert "both" in fmts


# ---------------------------------------------------------------------------
# InvoiceService.export:fmt='both' 与 json_path 默认
# ---------------------------------------------------------------------------


def test_service_export_both(tmp_path):
    inv = _inv("1")
    result = ParseResult(invoices=[inv], duplicates=[], failed=[])
    out = tmp_path / "out.xlsx"
    written = InvoiceService().export(result, out, fmt="both")
    assert len(written) == 2
    assert any(p.suffix == ".xlsx" for p in written)
    assert any(p.suffix == ".json" for p in written)


def test_service_export_json_only_with_explicit_path(tmp_path):
    inv = _inv("1")
    result = ParseResult(invoices=[inv], duplicates=[], failed=[])
    out = tmp_path / "out.xlsx"
    jp = tmp_path / "custom.json"
    written = InvoiceService().export(result, out, fmt="json", json_path=jp)
    assert len(written) == 1
    assert written[0] == jp


def test_service_export_excel_only(tmp_path):
    inv = _inv("1")
    result = ParseResult(invoices=[inv], duplicates=[], failed=[])
    out = tmp_path / "out.xlsx"
    written = InvoiceService().export(result, out, fmt="excel")
    assert len(written) == 1
    assert written[0] == out
