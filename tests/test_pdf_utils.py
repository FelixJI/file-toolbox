"""file_toolbox.core.batch_pdf.pdf_utils 单元测试。

覆盖 convert_pdf_to_image_pdf / merge_pdfs / get_file_info 以及
_resize_to_fit / _fit_image_to_paper 等纯逻辑函数。
使用 fitz(PyMuPDF) 与 PIL 直接生成 fixture,不依赖任何 Office COM。
"""

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")  # noqa: F841 — 触发 skip 并保留别名
pytest.importorskip("PIL")  # noqa: E402

from file_toolbox.core.batch_pdf.constants import (  # noqa: E402
    PAPER_SIZES,
    PRINT_MODE_DUPLEX,
    SCALE_ACTUAL_SIZE,
    SCALE_FIT_MARGIN,
    SUPPORTED_FORMATS,
)
from file_toolbox.core.batch_pdf.pdf_utils import (  # noqa: E402
    _fit_image_to_paper,
    _resize_to_fit,
    convert_pdf_to_image_pdf,
    get_file_info,
    merge_pdfs,
)

# --- fixture 构造工具 ----------------------------------------------------------


def _make_pdf(path: Path, pages: int = 1) -> Path:
    """生成一个指定页数的空白 PDF(width=200, height=300 点)。"""
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=200, height=300)
    doc.save(str(path))
    doc.close()
    return path


# --- convert_pdf_to_image_pdf --------------------------------------------------


def test_convert_pdf_to_image_pdf(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=1)
    out = tmp_path / "out.pdf"

    ok, msg = convert_pdf_to_image_pdf(src, out)

    assert ok is True
    assert msg == ""
    assert out.exists()
    doc = fitz.open(str(out))
    try:
        assert len(doc) == 1
    finally:
        doc.close()


def test_convert_pdf_to_image_pdf_multipage(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=3)
    out = tmp_path / "out.pdf"

    ok, msg = convert_pdf_to_image_pdf(src, out)

    assert ok, msg
    doc = fitz.open(str(out))
    try:
        assert len(doc) == 3
    finally:
        doc.close()


def test_convert_pdf_to_image_pdf_with_paper(tmp_path):
    """指定 paper_size 走 _fit_image_to_paper 分支。"""
    src = _make_pdf(tmp_path / "src.pdf", pages=1)
    out = tmp_path / "out.pdf"

    ok, msg = convert_pdf_to_image_pdf(
        src,
        out,
        paper_size="A4",
        orientation="portrait",
        scale_mode=SCALE_FIT_MARGIN,
    )

    assert ok, msg
    assert out.exists()


# --- merge_pdfs ----------------------------------------------------------------


def test_merge_pdfs_two_files(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", pages=1)
    b = _make_pdf(tmp_path / "b.pdf", pages=1)
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([a, b], out)

    assert ok, msg
    assert out.exists()
    doc = fitz.open(str(out))
    try:
        assert len(doc) == 2
    finally:
        doc.close()


def test_merge_pdfs_duplex_inserts_blank_for_odd(tmp_path):
    """单面源(1 页)在 duplex 模式下应补一张空白页(共 2 页)。"""
    odd = _make_pdf(tmp_path / "odd.pdf", pages=1)
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([odd], out, print_mode=PRINT_MODE_DUPLEX)

    assert ok, msg
    doc = fitz.open(str(out))
    try:
        assert len(doc) == 2  # 原页 + 补的空白页
    finally:
        doc.close()


def test_merge_pdfs_duplex_even_pages_no_blank(tmp_path):
    """偶数页源在 duplex 模式下不应插入额外空白页。"""
    even = _make_pdf(tmp_path / "even.pdf", pages=2)
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([even], out, print_mode=PRINT_MODE_DUPLEX)

    assert ok, msg
    doc = fitz.open(str(out))
    try:
        assert len(doc) == 2  # 不补页
    finally:
        doc.close()


def test_merge_pdfs_missing_file_skipped(tmp_path):
    """列表中不存在的文件应被跳过,不报错。"""
    a = _make_pdf(tmp_path / "a.pdf", pages=1)
    missing = tmp_path / "does_not_exist.pdf"
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([a, missing], out)

    assert ok, msg
    doc = fitz.open(str(out))
    try:
        assert len(doc) == 1
    finally:
        doc.close()


# --- get_file_info -------------------------------------------------------------


def test_get_file_info(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4\n%fake content here\n")

    info = get_file_info(f, SUPPORTED_FORMATS)

    assert info["name"] == "doc.pdf"
    assert info["suffix"] == ".pdf"
    assert info["size"] > 0
    assert info["size_str"] != "未知"
    assert info["type"] == "pdf"
    assert info["supported"] is True


def test_get_file_info_unsupported_suffix(tmp_path):
    f = tmp_path / "thing.xyz"
    f.write_bytes(b"12345")

    info = get_file_info(f, SUPPORTED_FORMATS)

    assert info["type"] is None
    assert info["supported"] is False


def test_get_file_info_missing_returns_zero_size(tmp_path):
    """文件不存在:size 保持 0,size_str 仍为'未知',但 name/suffix 仍返回。"""
    f = tmp_path / "ghost.pdf"

    info = get_file_info(f, SUPPORTED_FORMATS)

    assert info["name"] == "ghost.pdf"
    assert info["size"] == 0
    assert info["size_str"] == "未知"
    assert info["supported"] is True  # 后缀匹配但文件不存在


# --- _resize_to_fit ------------------------------------------------------------


def test_resize_to_fit_actual_size_unchanged():
    """scale_mode=actual_size 在 _fit_image_to_paper 中不缩放:这里直接验证
    _resize_to_fit 对小图返回原图(等比缩放比例 == 1 时不 resize)。"""
    from PIL import Image

    img = Image.new("RGB", (100, 200))
    out = _resize_to_fit(img, 100, 200)
    assert out.size == (100, 200)


def test_resize_to_fit_shrinks_oversized():
    """小目标框下应缩小到目标内,且保持宽高比。"""
    from PIL import Image

    img = Image.new("RGB", (400, 200))
    out = _resize_to_fit(img, 200, 100)
    assert out.size == (200, 100)


def test_resize_to_fit_enlarges_small_image():
    """_resize_to_fit 支持放大(与 thumbnail 不同)。"""
    from PIL import Image

    img = Image.new("RGB", (50, 50))
    out = _resize_to_fit(img, 200, 200)
    assert out.size == (200, 200)


# --- _fit_image_to_paper -------------------------------------------------------


def test_fit_image_to_paper_landscape_swap():
    """800x400(宽图)在 A4 portrait + auto 下应交换宽高:输出宽<=高(纵向画布容纳)。"""
    from PIL import Image

    img = Image.new("RGB", (800, 400))
    dpi = 72
    result = _fit_image_to_paper(img, "A4", "auto", dpi, scale_mode=SCALE_FIT_MARGIN)

    paper_w_mm, paper_h_mm = PAPER_SIZES["A4"]
    paper_w_px = int(paper_w_mm * dpi / 25.4)
    paper_h_px = int(paper_h_mm * dpi / 25.4)
    # auto + img.width>img.height => 交换 => 画布是 landscape 尺寸
    assert result.size == (paper_h_px, paper_w_px)


def test_fit_image_to_paper_actual_size_no_resize():
    """actual_size:画布尺寸 = 纸张像素,图片不缩放(直接居中,可能裁剪)。"""
    from PIL import Image

    img = Image.new("RGB", (50, 50))
    dpi = 72
    result = _fit_image_to_paper(img, "A4", "portrait", dpi, scale_mode=SCALE_ACTUAL_SIZE)

    paper_w_mm, paper_h_mm = PAPER_SIZES["A4"]
    expected_w = int(paper_w_mm * dpi / 25.4)
    expected_h = int(paper_h_mm * dpi / 25.4)
    assert result.size == (expected_w, expected_h)


def test_fit_image_to_paper_explicit_landscape():
    """orientation=landscape:无论图片比例都强制交换宽高。"""
    from PIL import Image

    img = Image.new("RGB", (100, 400))  # 纵向图,但指定 landscape
    dpi = 72
    result = _fit_image_to_paper(img, "A4", "landscape", dpi, scale_mode=SCALE_FIT_MARGIN)

    paper_w_mm, paper_h_mm = PAPER_SIZES["A4"]
    paper_w_px = int(paper_w_mm * dpi / 25.4)
    paper_h_px = int(paper_h_mm * dpi / 25.4)
    assert result.size == (paper_h_px, paper_w_px)


def test_fit_image_to_paper_shrink_oversized_default():
    """默认 shrink_oversized:大图缩进纸张内。"""
    from PIL import Image

    img = Image.new("RGB", (2000, 2000))
    dpi = 72
    result = _fit_image_to_paper(img, "A4", "portrait", dpi, scale_mode="shrink_oversized")

    paper_w_mm, paper_h_mm = PAPER_SIZES["A4"]
    paper_w_px = int(paper_w_mm * dpi / 25.4)
    paper_h_px = int(paper_h_mm * dpi / 25.4)
    # 画布始终为纸张像素尺寸
    assert result.size == (paper_w_px, paper_h_px)
