"""file_toolbox.core.batch_pdf.pdf_utils 单元测试。

覆盖 convert_pdf_to_image_pdf / merge_pdfs / get_file_info 以及
_resize_to_fit / _fit_image_to_paper 等纯逻辑函数。
使用 pypdf 与 PIL 直接生成 fixture,不依赖任何 Office COM。
"""

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

pytest.importorskip("pypdfium2")
pytest.importorskip("PIL")  # noqa: E402

from unittest.mock import MagicMock

from file_toolbox.core.batch_pdf import pdf_utils  # noqa: E402
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
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=300)
    writer.write(path)
    writer.close()
    return path


# --- convert_pdf_to_image_pdf --------------------------------------------------


def test_convert_pdf_to_image_pdf(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=1)
    out = tmp_path / "out.pdf"

    ok, msg = convert_pdf_to_image_pdf(src, out)

    assert ok is True
    assert msg == ""
    assert out.exists()
    assert len(PdfReader(out).pages) == 1


def test_convert_pdf_to_image_pdf_multipage(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=3)
    out = tmp_path / "out.pdf"

    ok, msg = convert_pdf_to_image_pdf(src, out)

    assert ok, msg
    assert len(PdfReader(out).pages) == 3


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
    assert len(PdfReader(out).pages) == 2


def test_merge_pdfs_duplex_inserts_blank_for_odd(tmp_path):
    """单面源(1 页)在 duplex 模式下应补一张空白页(共 2 页)。"""
    odd = _make_pdf(tmp_path / "odd.pdf", pages=1)
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([odd], out, print_mode=PRINT_MODE_DUPLEX)

    assert ok, msg
    assert len(PdfReader(out).pages) == 2  # 原页 + 补的空白页


def test_merge_pdfs_duplex_even_pages_no_blank(tmp_path):
    """偶数页源在 duplex 模式下不应插入额外空白页。"""
    even = _make_pdf(tmp_path / "even.pdf", pages=2)
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([even], out, print_mode=PRINT_MODE_DUPLEX)

    assert ok, msg
    assert len(PdfReader(out).pages) == 2  # 不补页


def test_merge_pdfs_missing_file_skipped(tmp_path):
    """列表中不存在的文件应被跳过,不报错。"""
    a = _make_pdf(tmp_path / "a.pdf", pages=1)
    missing = tmp_path / "does_not_exist.pdf"
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([a, missing], out)

    assert ok, msg
    assert len(PdfReader(out).pages) == 1


def test_merge_pdfs_empty_list_fails_cleanly(tmp_path):
    """空列表不产生 PDF 文件，并返回失败与中文提示。"""
    out = tmp_path / "empty.pdf"
    ok, msg = merge_pdfs([], out)
    assert ok is False
    assert "合并PDF失败" in msg
    assert not out.exists()


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


# ---------------------------------------------------------------------------
# get_file_info:stat 抛异常(行 308-309)
# ---------------------------------------------------------------------------


def test_get_file_info_stat_exception_swallowed(tmp_path, monkeypatch):
    """file 存在但 stat 抛异常 → except pass,info 保留默认 size=0(行 308-309)。"""
    f = tmp_path / "a.pdf"
    f.write_bytes(b"fake")
    monkeypatch.setattr(
        Path, "stat", lambda self, **kw: (_ for _ in ()).throw(PermissionError("stat"))
    )
    supported = {"pdf": [".pdf"]}
    info = get_file_info(f, supported)
    assert info["supported"] is True
    # stat 异常被吞,size 保持默认 0,size_str 保持 '未知'
    assert info["size"] == 0
    assert info["size_str"] == "未知"


# ---------------------------------------------------------------------------
# convert_pdf_to_image_pdf:空 PDF(行 97)
# ---------------------------------------------------------------------------


def test_convert_pdf_to_image_pdf_empty_returns_error(tmp_path, monkeypatch):
    """0 页 PDF → images 空 → (False, 'PDF无内容')(行 97)。

    用 mock PdfDocument 返回一个 len()=0 的假文档。
    """
    src = tmp_path / "empty.pdf"
    src.write_bytes(b"fake")
    out = tmp_path / "out.pdf"

    fake_doc = MagicMock()
    fake_doc.__len__ = lambda self: 0  # 0 页
    fake_doc.__enter__.return_value = fake_doc
    monkeypatch.setattr(pdf_utils.pdfium, "PdfDocument", lambda *a, **k: fake_doc)

    ok, err = convert_pdf_to_image_pdf(src, out, dpi=72)
    assert ok is False
    assert "PDF无内容" in err


# ---------------------------------------------------------------------------
# convert_pdf_to_image_pdf:通用 except(行 115-116)
# ---------------------------------------------------------------------------


def test_convert_pdf_to_image_pdf_generic_exception(tmp_path, monkeypatch):
    """PdfDocument 抛异常 → 通用 except → (False, '转换图片型PDF失败: ...')。"""
    src = tmp_path / "a.pdf"
    src.write_bytes(b"fake")
    out = tmp_path / "out.pdf"

    monkeypatch.setattr(
        pdf_utils.pdfium,
        "PdfDocument",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pdfium boom")),
    )
    ok, err = convert_pdf_to_image_pdf(src, out, dpi=72)
    assert ok is False
    assert "转换图片型PDF失败" in err
    assert "pdfium boom" in err


def test_convert_pdf_to_image_pdf_non_rgb_converted(tmp_path, monkeypatch):
    """像素图产生非 RGB 图像 → convert("RGB")(行 86)。

    用 mock bitmap.to_pil 返回灰度图(模式 'L'),触发 convert 分支。
    """
    from PIL import Image

    gray_img = Image.new("L", (5, 5), 128)

    src = tmp_path / "a.pdf"
    src.write_bytes(b"fake")
    out = tmp_path / "out.pdf"

    fake_bitmap = MagicMock()
    fake_bitmap.to_pil.return_value = gray_img
    fake_page = MagicMock()
    fake_page.render.return_value = fake_bitmap
    fake_doc = MagicMock()
    fake_doc.__len__ = lambda self: 1
    fake_doc.__getitem__ = lambda self, i: fake_page
    fake_doc.__enter__.return_value = fake_doc
    monkeypatch.setattr(pdf_utils.pdfium, "PdfDocument", lambda *a, **k: fake_doc)

    ok, err = convert_pdf_to_image_pdf(src, out, dpi=72)
    assert ok is True
    assert err == ""


# ---------------------------------------------------------------------------
# merge_pdfs:通用 except(行 272-273)
# ---------------------------------------------------------------------------


def test_merge_pdfs_generic_exception(tmp_path, monkeypatch):
    """PdfWriter 抛异常 → 通用 except → (False, '合并PDF失败: ...')。"""
    src = tmp_path / "a.pdf"
    src.write_bytes(b"fake")
    out = tmp_path / "merged.pdf"

    monkeypatch.setattr(
        pdf_utils,
        "PdfWriter",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("merge boom")),
    )
    ok, err = merge_pdfs([src], out)
    assert ok is False
    assert "合并PDF失败" in err
    assert "merge boom" in err
