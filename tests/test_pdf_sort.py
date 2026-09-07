"""pdf_sort 核心测试:排序键提取、自然排序、页序计算、计划/执行/失败/取消/历史。

全部基于程序化生成的虚构 PDF(reportlab 文字页 + pypdf 空白页),纯 Python、跨平台。
"""

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.pdf_sort import (
    ORDER_ASC,
    ORDER_DESC,
    UNMATCHED_FAIL,
    UNMATCHED_FIRST,
    UNMATCHED_LAST,
    FailedFile,
    FilePlan,
    PagePlan,
    PdfSortService,
    SortedFile,
    SortOptions,
    SortResult,
    compile_pattern,
    compute_order,
    extract_key,
    natural_key,
)

# ==================== 排序键提取(纯函数) ====================


def test_compile_pattern_invalid_raises():
    with pytest.raises(ValueError, match="无效的匹配格式"):
        compile_pattern("([0-9")


def test_extract_key_prefers_capture_group():
    regex = compile_pattern(r"NO\.\s*(\d+)")
    assert extract_key("Date: 2024-01-02 NO.7", regex) == "7"


def test_extract_key_whole_match_without_group():
    regex = compile_pattern(r"\d{4}-\d{2}-\d{2}")
    assert extract_key("Date: 2024-01-02", regex) == "2024-01-02"


def test_extract_key_first_match_wins():
    regex = compile_pattern(r"(\d{4}-\d{2}-\d{2})")
    assert extract_key("A: 2024-01-02 B: 2023-12-31", regex) == "2024-01-02"


def test_extract_key_none_when_no_match():
    regex = compile_pattern(r"出库日期[:：]\s*([0-9-]+)")
    assert extract_key("nothing here", regex) is None
    assert extract_key("", regex) is None


def test_extract_key_tolerates_whitespace_noise():
    """OCR/文字层常见噪声:标签逐字拆开、跨行,先原文后折叠/去空白候选。"""
    regex = compile_pattern(r"出库日期[:：]\s*([0-9-]+)")
    # 标签被逐字拆开 -> 原文不中,去空白候选命中
    assert extract_key("出 库 日 期 : 2024-01-05", regex) == "2024-01-05"
    # 标签与值跨行 -> 原文直接命中(\s* 覆盖换行)
    assert extract_key("出库日期:\n2024-01-06", regex) == "2024-01-06"
    # 词间多空格 -> 折叠候选命中
    regex2 = compile_pattern(r"Date\s*:\s*([0-9-]+)")
    assert extract_key("Date   :   2024-01-07", regex2) == "2024-01-07"


def test_natural_key_compares_digits_numerically():
    """数字段按数值:'NO.9' < 'NO.10';非零填充日期 '2024-1-9' < '2024-1-10'。"""
    assert natural_key("NO.9") < natural_key("NO.10")
    assert natural_key("2024-1-9") < natural_key("2024-1-10")
    assert natural_key("2024-02") > natural_key("2024-1")


def test_natural_key_mixed_forms_never_raise():
    """不同形态的键(纯数字 vs 纯文字)比较不抛 TypeError,数字恒排在前。"""
    assert natural_key("2024-01-01") < natural_key("N/A")
    assert natural_key("N/A") > natural_key("123")


# ==================== 页序计算(纯函数) ====================


def test_compute_order_asc_and_desc():
    keys = ["c", "a", "b"]
    assert compute_order(keys, ORDER_ASC, UNMATCHED_LAST) == [1, 2, 0]
    assert compute_order(keys, ORDER_DESC, UNMATCHED_LAST) == [0, 2, 1]


def test_compute_order_stable_for_equal_keys():
    """键相同的页保持原有先后(升序与降序均稳定)。"""
    keys = ["b", "a", "b"]
    assert compute_order(keys, ORDER_ASC, UNMATCHED_LAST) == [1, 0, 2]
    assert compute_order(keys, ORDER_DESC, UNMATCHED_LAST) == [0, 2, 1]


def test_compute_order_unmatched_policies():
    keys = ["b", None, "a"]
    assert compute_order(keys, ORDER_ASC, UNMATCHED_LAST) == [2, 0, 1]
    assert compute_order(keys, ORDER_ASC, UNMATCHED_FIRST) == [1, 2, 0]
    assert compute_order(keys, ORDER_ASC, UNMATCHED_FAIL) is None
    # 全部匹配时 fail 策略不影响结果
    assert compute_order(["b", "a"], ORDER_ASC, UNMATCHED_FAIL) == [1, 0]


def test_compute_order_natural_number_sequence():
    keys = ["NO.10", "NO.9", "NO.2"]
    assert compute_order(keys, ORDER_ASC, UNMATCHED_LAST) == [2, 1, 0]


# ==================== 计划(plan_pages) ====================


def _blank_pdf(path: Path, pages: int) -> Path:
    """生成无文字层的空白 PDF(纯图像扫描件无 OCR 的等价物)。"""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=300)
    writer.write(path)
    writer.close()
    return path


def test_plan_pages_returns_keys_and_order(make_text_pdf):
    pdf = make_text_pdf(
        "danju.pdf",
        ["CKD Date: 2024-03-15", "CKD Date: 2024-01-02", "CKD Date: 2024-02-20"],
    )

    plans, failed = PdfSortService().plan_pages([pdf], SortOptions(pattern=r"Date:\s*([0-9-]+)"))

    assert failed == []
    assert len(plans) == 1
    plan = plans[0]
    assert plan.file == "danju.pdf"
    assert plan.order == [1, 2, 0]
    assert [(p.page, p.key, p.matched, p.new_index) for p in plan.pages] == [
        (0, "2024-03-15", True, 2),
        (1, "2024-01-02", True, 0),
        (2, "2024-02-20", True, 1),
    ]


def test_plan_pages_invalid_pattern_raises():
    with pytest.raises(ValueError, match="无效的匹配格式"):
        PdfSortService().plan_pages([], SortOptions(pattern="("))


def test_plan_pages_unsupported_suffix(tmp_path):
    legacy = tmp_path / "a.docx"
    legacy.write_bytes(b"fake")
    plans, failed = PdfSortService().plan_pages([legacy], SortOptions(pattern="x"))
    assert plans == []
    assert "不支持的格式" in failed[0].error


def test_plan_pages_missing_file(tmp_path):
    missing = tmp_path / "ghost.pdf"
    plans, failed = PdfSortService().plan_pages([missing], SortOptions(pattern="x"))
    assert plans == []
    assert "无法读取" in failed[0].error


def test_plan_pages_no_text_layer(tmp_path):
    blank = _blank_pdf(tmp_path / "scan.pdf", 2)
    plans, failed = PdfSortService().plan_pages([blank], SortOptions(pattern=r"Date:\s*([0-9-]+)"))
    assert failed == []
    assert plans[0].order is None
    assert "文字层" in plans[0].note
    assert all(not p.matched for p in plans[0].pages)


def test_plan_pages_fail_policy_marks_file(tmp_path, make_text_pdf):
    pdf = make_text_pdf("mixed.pdf", ["Date: 2024-01-02", "no marks", "Date: 2024-02-01"])
    plans, failed = PdfSortService().plan_pages(
        [pdf], SortOptions(pattern=r"Date:\s*([0-9-]+)", unmatched=UNMATCHED_FAIL)
    )
    assert failed == []
    assert plans[0].order is None
    assert "1 页未匹配" in plans[0].note
    assert plans[0].pages[1].matched is False
    assert plans[0].pages[0].new_index == -1


def test_plan_pages_progress_callback(make_text_pdf):
    pdf = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    calls: list[tuple[int, int, str]] = []

    PdfSortService().plan_pages(
        [pdf],
        SortOptions(pattern="Date"),
        progress_callback=lambda c, t, m: calls.append((c, t, m)),
    )

    assert calls == [(1, 1, "分析 a.pdf")]


# ==================== 执行(sort) ====================


def _page_texts(path: Path) -> list[str]:
    with path.open("rb") as stream:
        return [(p.extract_text() or "").strip() for p in PdfReader(stream).pages]


def test_sort_writes_reordered_output(make_text_pdf, tmp_path):
    src = make_text_pdf(
        "danju.pdf",
        ["Date: 2024-03-15", "Date: 2024-01-02", "Date: 2024-02-20"],
    )
    before = src.read_bytes()

    result = PdfSortService().sort([src], SortOptions(pattern=r"Date:\s*([0-9-]+)"))

    assert result.success
    assert result.failed == []
    out = tmp_path / "danju_排序.pdf"
    assert result.sorted_files[0].output == out
    assert _page_texts(out) == ["Date: 2024-01-02", "Date: 2024-02-20", "Date: 2024-03-15"]
    assert src.read_bytes() == before  # 源文件永不被修改


def test_sort_desc(make_text_pdf, tmp_path):
    src = make_text_pdf("d.pdf", ["Date: 2024-01-02", "Date: 2024-03-15", "Date: 2024-02-01"])
    PdfSortService().sort([src], SortOptions(pattern=r"Date:\s*([0-9-]+)", order=ORDER_DESC))
    assert _page_texts(tmp_path / "d_排序.pdf") == [
        "Date: 2024-03-15",
        "Date: 2024-02-01",
        "Date: 2024-01-02",
    ]


@pytest.mark.parametrize(
    ("policy", "expected_pos"),
    [(UNMATCHED_LAST, 2), (UNMATCHED_FIRST, 0)],
)
def test_sort_unmatched_placement(make_text_pdf, tmp_path, policy, expected_pos):
    src = make_text_pdf("m.pdf", ["Date: 2024-02-01", "broken page", "Date: 2024-01-01"])
    result = PdfSortService().sort(
        [src], SortOptions(pattern=r"Date:\s*([0-9-]+)", unmatched=policy)
    )
    assert result.success
    texts = _page_texts(tmp_path / "m_排序.pdf")
    assert texts[expected_pos] == "broken page"
    assert [t for i, t in enumerate(texts) if i != expected_pos] == [
        "Date: 2024-01-01",
        "Date: 2024-02-01",
    ]


def test_sort_unmatched_fail_no_output(make_text_pdf, tmp_path):
    src = make_text_pdf("f.pdf", ["Date: 2024-01-01", "no marks"])
    result = PdfSortService().sort(
        [src], SortOptions(pattern=r"Date:\s*([0-9-]+)", unmatched=UNMATCHED_FAIL)
    )
    assert not result.success
    assert result.sorted_files == []
    assert "1 页未匹配" in result.failed[0].error
    assert not (tmp_path / "f_排序.pdf").exists()


def test_sort_all_unmatched_no_text_layer(tmp_path):
    blank = _blank_pdf(tmp_path / "scan.pdf", 2)
    result = PdfSortService().sort([blank], SortOptions(pattern=r"Date:\s*([0-9-]+)"))
    assert not result.success
    assert "文字层" in result.failed[0].error


def test_sort_unchanged_skips_write(make_text_pdf, tmp_path):
    src = make_text_pdf("ok.pdf", ["Date: 2024-01-01", "Date: 2024-01-02"])
    result = PdfSortService().sort([src], SortOptions(pattern=r"Date:\s*([0-9-]+)"))
    assert result.success
    assert result.sorted_files[0].output is None
    assert "顺序未变" in result.sorted_files[0].note
    assert not (tmp_path / "ok_排序.pdf").exists()


def test_sort_output_never_overwrites(make_text_pdf, tmp_path):
    src = make_text_pdf("a.pdf", ["Date: 2024-02-01", "Date: 2024-01-01"])
    out = tmp_path / "a_排序.pdf"
    out.write_bytes(b"precious")

    result = PdfSortService().sort([src], SortOptions(pattern=r"Date:\s*([0-9-]+)"))

    assert out.read_bytes() == b"precious"
    assert result.sorted_files[0].output == tmp_path / "a_排序_1.pdf"
    assert _page_texts(tmp_path / "a_排序_1.pdf") == ["Date: 2024-01-01", "Date: 2024-02-01"]


def test_sort_single_file_custom_output_forces_pdf(make_text_pdf, tmp_path):
    src = make_text_pdf("a.pdf", ["Date: 2024-02-01", "Date: 2024-01-01"])
    out = tmp_path / "sub" / "out.doc"  # 非法后缀归一为 .pdf

    result = PdfSortService().sort([src], SortOptions(pattern=r"Date:\s*([0-9-]+)"), output=out)

    assert result.sorted_files[0].output == tmp_path / "sub" / "out.pdf"
    assert result.sorted_files[0].output.is_file()


def test_sort_multiple_files_each_sorted(make_text_pdf, tmp_path):
    a = make_text_pdf("a.pdf", ["Date: 2024-02-01", "Date: 2024-01-01"])
    b = make_text_pdf("b.pdf", ["Date: 2024-04-01", "Date: 2024-03-01"])
    out_dir = tmp_path / "outs"

    result = PdfSortService().sort(
        [a, b], SortOptions(pattern=r"Date:\s*([0-9-]+)"), output=out_dir
    )

    assert result.success
    assert _page_texts(out_dir / "a_排序.pdf") == ["Date: 2024-01-01", "Date: 2024-02-01"]
    assert _page_texts(out_dir / "b_排序.pdf") == ["Date: 2024-03-01", "Date: 2024-04-01"]


def test_sort_output_file_with_multiple_files_rejected(make_text_pdf, tmp_path):
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    b = make_text_pdf("b.pdf", ["Date: 2024-01-02"])
    with pytest.raises(ValueError, match="输出目录"):
        PdfSortService().sort([a, b], SortOptions(pattern="Date"), output=tmp_path / "m.pdf")


def test_sort_failed_source_continues(make_text_pdf, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    good = make_text_pdf("g.pdf", ["Date: 2024-02-01", "Date: 2024-01-01"])

    result = PdfSortService().sort([bad, good], SortOptions(pattern=r"Date:\s*([0-9-]+)"))

    assert result.success
    assert len(result.failed) == 1
    assert result.failed[0].file == "bad.pdf"
    assert _page_texts(tmp_path / "g_排序.pdf") == ["Date: 2024-01-01", "Date: 2024-02-01"]


def test_sort_all_failed_no_output(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"nope")
    result = PdfSortService().sort([bad], SortOptions(pattern="Date"))
    assert not result.success
    assert result.error_message == "全部源文件失败"
    assert not (tmp_path / "bad_排序.pdf").exists()


def test_sort_empty_file_list():
    result = PdfSortService().sort([], SortOptions(pattern="Date"))
    assert not result.success
    assert result.error_message == "没有可排序的 PDF"


def test_sort_encrypted_pdf_fails_with_message(tmp_path, make_text_pdf):
    src = make_text_pdf("enc.pdf", ["Date: 2024-01-01"])
    encrypted = tmp_path / "locked.pdf"
    writer = PdfWriter()
    with src.open("rb") as stream:
        writer.append(PdfReader(stream))
    writer.encrypt("secret")
    writer.write(encrypted)
    writer.close()

    result = PdfSortService().sort([encrypted], SortOptions(pattern="Date"))

    assert not result.success
    assert "加密" in result.failed[0].error


def test_sort_cancel_between_files(make_text_pdf, tmp_path):
    a = make_text_pdf("a.pdf", ["Date: 2024-02-01", "Date: 2024-01-01"])
    b = make_text_pdf("b.pdf", ["Date: 2024-01-01"])
    calls: list[int] = []

    def cancel_after_first() -> bool:
        return bool(calls)

    def progress(cur: int, total: int, msg: str) -> None:
        calls.append(cur)

    result = PdfSortService().sort(
        [a, b],
        SortOptions(pattern=r"Date:\s*([0-9-]+)"),
        cancel_check=cancel_after_first,
        progress_callback=progress,
    )

    assert result.cancelled
    assert not result.success
    assert (tmp_path / "a_排序.pdf").is_file()  # 首个文件已完成
    assert not (tmp_path / "b_排序.pdf").exists()


# ==================== 历史 ====================


def test_sort_records_history_on_success(make_text_pdf, tmp_path):
    history = JsonHistoryStore(history_dir=tmp_path / "h")
    src = make_text_pdf("a.pdf", ["Date: 2024-01-02", "Date: 2024-02-01"])
    svc = PdfSortService(history_store=history)

    svc.sort([src], SortOptions(pattern=r"Date:\s*([0-9-]+)", order=ORDER_DESC))

    records = history.get_records("pdf_sort")
    assert len(records) == 1
    data = records[0]["data"]
    assert data["file_count"] == 1
    assert data["page_count"] == 2
    assert data["unmatched_count"] == 0
    assert data["order"] == ORDER_DESC
    assert data["pattern"] == r"Date:\s*([0-9-]+)"
    assert len(data["outputs"]) == 1
    assert data["success"] is True


def test_sort_no_history_when_cancelled_or_nothing_written(make_text_pdf, tmp_path):
    history = JsonHistoryStore(history_dir=tmp_path / "h")
    svc = PdfSortService(history_store=history)
    src = make_text_pdf("a.pdf", ["Date: 2024-01-01"])

    r1 = svc.sort([src], SortOptions(pattern="Date"), cancel_check=lambda: True)
    unchanged = make_text_pdf("b.pdf", ["Date: 2024-01-01", "Date: 2024-01-02"])
    r2 = svc.sort([unchanged], SortOptions(pattern="Date"))

    assert r1.cancelled and r2.success
    assert history.get_records("pdf_sort") == []  # 取消与未写出输出均不记录


def test_sort_result_semantics():
    ok = SortResult(sorted_files=[SortedFile("a.pdf", Path("o.pdf"), [])])
    assert ok.success is True
    assert ok.written_count == 1
    unchanged = SortResult(sorted_files=[SortedFile("a.pdf", None, [])])
    assert unchanged.success is True
    assert unchanged.written_count == 0
    assert SortResult(cancelled=True).success is False
    assert SortResult().success is False


def test_dataclass_defaults():
    plan = FilePlan(file="a.pdf")
    assert plan.pages == [] and plan.order is None and plan.note == ""
    page = PagePlan(page=0, key="", matched=False)
    assert page.new_index == -1 and page.note == ""
    assert FailedFile("a.pdf", "e").error == "e"
