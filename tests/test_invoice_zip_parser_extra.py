"""zip_parser 边界路径补充测试:目录条目、文件不存在、BadZipFile、
嵌套 zip 损坏、下游解析器抛 UnsupportedFormatError 的回退、最终无发票报错。
"""

import zipfile

import pytest

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError
from file_toolbox.core.invoice.parsers.zip_parser import (
    _find_files_by_ext,
    _safe_extract,
    parse_zip,
)

# ---------------------------------------------------------------------------
# _find_files_by_ext
# ---------------------------------------------------------------------------


def test_find_files_by_ext_returns_sorted(tmp_path):
    """rglob 结果排序,递归包含子目录。"""
    (tmp_path / "b.xml").write_text("x")
    (tmp_path / "a.xml").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.xml").write_text("x")
    (tmp_path / "ignore.txt").write_text("x")

    found = _find_files_by_ext(tmp_path, ".xml")
    assert [p.name for p in found] == ["a.xml", "b.xml", "c.xml"]


def test_find_files_by_ext_no_match(tmp_path):
    """无匹配 → 空列表。"""
    (tmp_path / "a.txt").write_text("x")
    assert _find_files_by_ext(tmp_path, ".xml") == []


# ---------------------------------------------------------------------------
# _safe_extract:目录条目跳过
# ---------------------------------------------------------------------------


def test_safe_extract_skips_directory_entries(tmp_path):
    """is_dir() 的条目被跳过(不解压出目录)。"""
    src = tmp_path / "with_dir.zip"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("a_dir/", b"")  # 目录条目
        zf.writestr("a_dir/file.txt", b"hello")

    dest = tmp_path / "out"
    dest.mkdir()
    with zipfile.ZipFile(src, "r") as zf:
        _safe_extract(zf, dest)

    assert (dest / "a_dir" / "file.txt").read_text() == "hello"


def test_safe_extract_normalizes_dest(tmp_path):
    """dest 用 resolve();普通条目解压到 dest 下。"""
    src = tmp_path / "plain.zip"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("x.txt", b"data")

    dest = tmp_path / "out"
    dest.mkdir()
    with zipfile.ZipFile(src, "r") as zf:
        _safe_extract(zf, dest)

    assert (dest / "x.txt").read_bytes() == b"data"


# ---------------------------------------------------------------------------
# parse_zip:文件不存在
# ---------------------------------------------------------------------------


def test_parse_zip_missing_file_raises(tmp_path):
    """path 不存在 → UnsupportedFormatError(文件不存在)。"""
    with pytest.raises(UnsupportedFormatError, match="文件不存在"):
        parse_zip(tmp_path / "nope.zip")


# ---------------------------------------------------------------------------
# parse_zip:BadZipFile
# ---------------------------------------------------------------------------


def test_parse_zip_bad_zip_raises(tmp_path):
    """非 ZIP 内容 → BadZipFile → 包装为 UnsupportedFormatError。"""
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip at all")
    with pytest.raises(UnsupportedFormatError, match="ZIP 解压失败"):
        parse_zip(bad)


# ---------------------------------------------------------------------------
# parse_zip:嵌套 zip 损坏(BadZipFile/OSError)被静默跳过
# ---------------------------------------------------------------------------


def test_parse_zip_nested_bad_zip_skipped(tmp_path):
    """外层合法 ZIP,内含一个坏的内层 zip → 静默跳过(不崩)。

    最终因无 xml/ofd/pdf 可解析 → UnsupportedFormatError。
    """
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as zf:
        # 内层 zip 头但内容损坏 → BadZipFile
        zf.writestr("inner.zip", b"PK\x03\x04corrupted")
    with pytest.raises(UnsupportedFormatError, match="未找到可识别的发票文件"):
        parse_zip(outer)


# ---------------------------------------------------------------------------
# parse_zip:xml/ofd/pdf 全部下游失败 → 最终报错
# ---------------------------------------------------------------------------


def test_parse_zip_xml_and_ofd_fail_raises(tmp_path):
    """ZIP 内有 .xml/.ofd 但内容均无法解析 → 各分支 UnsupportedFormatError
    被吞,最终 raise "未找到可识别的发票文件"。

    (不含 .pdf:parse_pdf 对坏 PDF 抛 PdfminerException 而非 UnsupportedFormatError,
    那是不可达防御分支,不在此覆盖。)
    """
    z = tmp_path / "mixed.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a.xml", b"not xml garbage")
        zf.writestr("b.ofd", b"not a zip garbage")
    with pytest.raises(UnsupportedFormatError, match="未找到可识别的发票文件"):
        parse_zip(z)


# ---------------------------------------------------------------------------
# parse_zip:xml 优先,但若 xml 失败则回退 ofd
# ---------------------------------------------------------------------------


def test_parse_zip_xml_fails_falls_back_to_ofd(tmp_path, ofd_sample):
    """ZIP 内同时有坏 xml 和好 ofd:xml 分支抛 UnsupportedFormatError → 回退 ofd。"""
    ofd_bytes = ofd_sample.read_bytes()
    z = tmp_path / "fallback.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("bad.xml", b"garbage not xml")
        zf.writestr("good.ofd", ofd_bytes)
    inv = parse_zip(z, source_file="fallback.zip")
    assert inv.invoice_number == "99990000000000000002"
    assert inv.parse_method == "ofd"


# ---------------------------------------------------------------------------
# parse_zip:无发票文件
# ---------------------------------------------------------------------------


def test_parse_zip_no_invoice_files_raises(tmp_path):
    """ZIP 内只有无关文件 → 最终报错。"""
    z = tmp_path / "empty.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("readme.txt", b"hi")
        zf.writestr("data.csv", b"a,b")
    with pytest.raises(UnsupportedFormatError, match="未找到可识别的发票文件"):
        parse_zip(z)


# ---------------------------------------------------------------------------
# parse_zip:source_file 默认用 path.name
# ---------------------------------------------------------------------------


def test_parse_zip_default_source_file(zip_xml_only):
    """不传 source_file → 内部用 path.name。"""
    inv = parse_zip(zip_xml_only)
    assert inv.invoice_number == "99990000000000000001"


def test_parse_zip_pdf_only(pdf_sample, tmp_path):
    """ZIP 内只含 .pdf(无 xml/ofd)→ pdf 分支解析成功。"""
    pdf_bytes = pdf_sample.read_bytes()
    z = tmp_path / "pdf_only.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("inv.pdf", pdf_bytes)
    inv = parse_zip(z, source_file="pdf_only.zip")
    assert inv.parse_method == "pdf"
    assert inv.invoice_number == "99990000000000000003"
