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
    ROTATE_AUTO,
    ROTATE_NONE,
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


def _make_pdf(path: Path, pages: int = 1, width: float = 200, height: float = 300) -> Path:
    """生成一个指定页数与页面尺寸(点)的空白 PDF,默认 200x300。"""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=height)
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


# --- 纸张重排(paper_size/orientation) ------------------------------------------


def _a4_points() -> tuple[float, float]:
    """A4 尺寸(点),与 _paper_target_points 的 mm→pt 换算一致。"""
    return 210 * 72 / 25.4, 297 * 72 / 25.4


def test_merge_pdfs_paper_size_unifies_mixed_pages(tmp_path):
    """选定 A4 后,不同尺寸源页面统一重排到 A4(核心回归:可编辑型合并)。"""
    a4_w, a4_h = _a4_points()
    small = _make_pdf(tmp_path / "small.pdf", pages=1)  # 200x300
    big = _make_pdf(tmp_path / "big.pdf", pages=1, width=400, height=200)  # 横版
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([small, big], out, paper_size="A4")

    assert ok, msg
    pages = PdfReader(out).pages
    assert len(pages) == 2
    # 方向保持原样(auto):每页对齐到同尺寸纸张,横版页取横向、纵版页取纵向
    assert float(pages[0].mediabox.width) == pytest.approx(a4_w, abs=0.5)  # 200x300 → 纵向
    assert float(pages[0].mediabox.height) == pytest.approx(a4_h, abs=0.5)
    assert float(pages[1].mediabox.width) == pytest.approx(a4_h, abs=0.5)  # 400x200 → 横向
    assert float(pages[1].mediabox.height) == pytest.approx(a4_w, abs=0.5)


def test_merge_pdfs_paper_auto_keeps_original_sizes(tmp_path):
    """paper_size=auto(保持原样)时页面尺寸不变(默认行为回归)。"""
    a = _make_pdf(tmp_path / "a.pdf", pages=1)  # 200x300
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([a], out, paper_size="auto")

    assert ok, msg
    page = PdfReader(out).pages[0]
    assert float(page.mediabox.width) == pytest.approx(200, abs=0.1)
    assert float(page.mediabox.height) == pytest.approx(300, abs=0.1)


def test_merge_pdfs_orientation_auto_aligns_long_edge(tmp_path):
    """方向保持原样(auto):横版页面对齐到横向 A4,纵版页面对齐到纵向 A4。"""
    a4_w, a4_h = _a4_points()
    wide = _make_pdf(tmp_path / "wide.pdf", pages=1, width=400, height=200)
    tall = _make_pdf(tmp_path / "tall.pdf", pages=1)  # 200x300
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([wide, tall], out, paper_size="A4", orientation="auto")

    assert ok, msg
    pages = PdfReader(out).pages
    # 宽>高 → 横向 A4(长边对长边)
    assert float(pages[0].mediabox.width) == pytest.approx(a4_h, abs=0.5)
    assert float(pages[0].mediabox.height) == pytest.approx(a4_w, abs=0.5)
    # 高>宽 → 纵向 A4
    assert float(pages[1].mediabox.width) == pytest.approx(a4_w, abs=0.5)
    assert float(pages[1].mediabox.height) == pytest.approx(a4_h, abs=0.5)


def test_merge_pdfs_orientation_forced_portrait_letterboxes(tmp_path):
    """强制纵向:横版页面统一到纵向 A4(信盒式留白,不旋转内容)。"""
    a4_w, a4_h = _a4_points()
    wide = _make_pdf(tmp_path / "wide.pdf", pages=1, width=400, height=200)
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([wide], out, paper_size="A4", orientation="portrait")

    assert ok, msg
    page = PdfReader(out).pages[0]
    assert float(page.mediabox.width) == pytest.approx(a4_w, abs=0.5)
    assert float(page.mediabox.height) == pytest.approx(a4_h, abs=0.5)


def test_merge_pdfs_duplex_blank_matches_repapered_size(tmp_path):
    """duplex 补白页尺寸跟随重排后的目标纸张,而不是源页面原始尺寸。"""
    a4_w, a4_h = _a4_points()
    odd = _make_pdf(tmp_path / "odd.pdf", pages=1)  # 200x300,单页
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([odd], out, print_mode=PRINT_MODE_DUPLEX, paper_size="A4")

    assert ok, msg
    pages = PdfReader(out).pages
    assert len(pages) == 2
    blank = pages[1]
    assert float(blank.mediabox.width) == pytest.approx(a4_w, abs=0.5)
    assert float(blank.mediabox.height) == pytest.approx(a4_h, abs=0.5)


def test_repaper_page_fast_path_skips_matching_page():
    """页面已等于目标纸张时跳过重排,不注入变换矩阵。"""
    from pypdf import PdfWriter

    from file_toolbox.core.batch_pdf.pdf_utils import _repaper_page

    a4_w, a4_h = _a4_points()
    writer = PdfWriter()
    page = writer.add_blank_page(width=a4_w, height=a4_h)
    try:
        _repaper_page(page, "A4", "auto", "shrink_oversized")
        # 未发生重排:页面无内容流(空白页),也未写入 MediaBox 变换
        assert page.get_contents() is None
    finally:
        writer.close()


def test_merge_pdfs_paper_size_preserves_text_content(make_text_pdf, tmp_path):
    """重排保持内容:文字经 cm 变换后仍可提取(可编辑型不丢内容)。"""
    src = make_text_pdf("src.pdf", ["hello paper"])  # 612x792 Letter
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([src], out, paper_size="A4")

    assert ok, msg
    page = PdfReader(out).pages[0]
    assert "hello paper" in (page.extract_text() or "")
    a4_w, a4_h = _a4_points()
    assert float(page.mediabox.width) == pytest.approx(a4_w, abs=0.5)


def test_merge_pdfs_paper_size_moves_annotations(tmp_path):
    """重排时注释 /Rect 与 /QuadPoints 随内容同一 CTM 缩放,不留在旧坐标系。"""
    from pypdf import PdfWriter
    from pypdf.annotations import Link
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject

    a4_w, a4_h = _a4_points()
    src = tmp_path / "annotated.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)  # Letter 纵向
    highlight = DictionaryObject()
    highlight[NameObject("/Type")] = NameObject("/Annot")
    highlight[NameObject("/Subtype")] = NameObject("/Highlight")
    highlight[NameObject("/Rect")] = ArrayObject([FloatObject(v) for v in (60, 610, 190, 630)])
    highlight[NameObject("/QuadPoints")] = ArrayObject(
        [FloatObject(v) for v in (60, 630, 190, 630, 60, 610, 190, 610)]
    )
    page[NameObject("/Annots")] = ArrayObject([highlight])
    # add_annotation 会在现有 /Annots 基础上追加,先放 highlight 再加 Link
    writer.add_annotation(0, Link(rect=(50, 600, 200, 650), url="https://example.com"))
    writer.write(src)
    writer.close()
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([src], out, paper_size="A4")

    assert ok, msg
    result_page = PdfReader(out).pages[0]
    annots = {str(a.get_object()["/Subtype"]): a.get_object() for a in result_page["/Annots"]}
    # shrink_oversized → s = min(A4/Letter)
    scale = min(a4_w / 612, a4_h / 792)
    link_rect = [float(v) for v in annots["/Link"]["/Rect"]]
    assert (link_rect[2] - link_rect[0]) == pytest.approx(150 * scale, abs=0.6)
    assert (link_rect[3] - link_rect[1]) == pytest.approx(50 * scale, abs=0.6)
    assert 0 <= link_rect[0] < link_rect[2] <= a4_w + 0.6
    assert 0 <= link_rect[1] < link_rect[3] <= a4_h + 0.6
    quad = [float(v) for v in annots["/Highlight"]["/QuadPoints"]]
    x_span = max(quad[0::2]) - min(quad[0::2])
    y_span = max(quad[1::2]) - min(quad[1::2])
    assert x_span == pytest.approx(130 * scale, abs=0.6)
    assert y_span == pytest.approx(20 * scale, abs=0.6)


# --- 页面旋转与 /Rotate 归一化 -------------------------------------------------


def _make_annotated_link_pdf(path: Path, width: float = 612, height: float = 792) -> Path:
    """生成带 Link 注释(150x50)的页,用于验证内容与注释随同一旋转变换。"""
    from pypdf.annotations import Link

    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    writer.add_annotation(0, Link(rect=(50, 600, 200, 650), url="https://example.com"))
    writer.write(path)
    writer.close()
    return path


def _with_view_rotation(src: Path, dst: Path, degrees: int) -> Path:
    """给 PDF 每页写入 /Rotate(模拟扫描件/Office 导出的显示旋转页)。"""
    from pypdf.generic import NameObject, NumberObject

    writer = PdfWriter(clone_from=src)
    for page in writer.pages:
        page[NameObject("/Rotate")] = NumberObject(degrees)
    writer.write(dst)
    writer.close()
    return dst


def test_merge_pdfs_rotate_auto_turns_content_to_match_sheet(tmp_path):
    """强制横向 + 自动旋转:纵向内容转 90° 长边对齐,注释宽高交换(150x50 → 50x150)。"""
    a4_w, a4_h = _a4_points()
    src = _make_annotated_link_pdf(tmp_path / "portrait.pdf")  # 612x792 Letter 纵向
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([src], out, paper_size="A4", orientation="landscape", rotate=ROTATE_AUTO)

    assert ok, msg
    page = PdfReader(out).pages[0]
    assert float(page.mediabox.width) == pytest.approx(a4_h, abs=0.5)
    assert float(page.mediabox.height) == pytest.approx(a4_w, abs=0.5)
    # 旋转盒 792x612 → 横向 A4;注释 150 宽 50 高 → 旋转后宽高交换
    scale = min(a4_h / 792, a4_w / 612)
    rect = [float(v) for v in page["/Annots"][0].get_object()["/Rect"]]
    assert (rect[2] - rect[0]) == pytest.approx(50 * scale, abs=0.6)
    assert (rect[3] - rect[1]) == pytest.approx(150 * scale, abs=0.6)


def test_merge_pdfs_rotate_none_keeps_content_axes(tmp_path):
    """不旋转(默认):强制横向时纵向内容等比缩小居中留白,注释宽高不交换。"""
    a4_w, a4_h = _a4_points()
    src = _make_annotated_link_pdf(tmp_path / "portrait.pdf")
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([src], out, paper_size="A4", orientation="landscape", rotate=ROTATE_NONE)

    assert ok, msg
    page = PdfReader(out).pages[0]
    scale = min(a4_h / 612, a4_w / 792)  # 内容盒 612x792 信盒式放进横向 A4
    rect = [float(v) for v in page["/Annots"][0].get_object()["/Rect"]]
    assert (rect[2] - rect[0]) == pytest.approx(150 * scale, abs=0.6)
    assert (rect[3] - rect[1]) == pytest.approx(50 * scale, abs=0.6)


def test_merge_pdfs_view_rotation_visual_orientation_wins(make_text_pdf, tmp_path):
    """/Rotate 90 页按视觉横版对齐(修复前按 MediaBox 误判纵向),旋转烘焙进内容。"""
    a4_w, a4_h = _a4_points()
    src = _with_view_rotation(make_text_pdf("src.pdf", ["rotated"]), tmp_path / "r90.pdf", 90)
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([src], out, paper_size="A4", orientation="auto")

    assert ok, msg
    page = PdfReader(out).pages[0]
    # 视觉 792x612 横版 → 横向 A4,且 /Rotate 归零(不再依赖查看器旋转)
    assert float(page.mediabox.width) == pytest.approx(a4_h, abs=0.5)
    assert float(page.mediabox.height) == pytest.approx(a4_w, abs=0.5)
    assert int(page.get("/Rotate", 0)) == 0
    assert "rotated" in (page.extract_text() or "")


def test_repaper_view_rotated_page_not_skipped_even_if_dims_match(tmp_path):
    """/Rotate 90 且 MediaBox 恰为目标纵向尺寸:不因尺寸相等跳过,仍归一化。"""
    from pypdf.generic import NameObject, NumberObject

    a4_w, a4_h = _a4_points()
    writer = PdfWriter()
    page = writer.add_blank_page(width=a4_w, height=a4_h)
    page[NameObject("/Rotate")] = NumberObject(90)
    src = tmp_path / "r90.pdf"
    writer.write(src)
    writer.close()
    out = tmp_path / "merged.pdf"

    ok, msg = merge_pdfs([src], out, paper_size="A4", orientation="auto")

    assert ok, msg
    result = PdfReader(out).pages[0]
    assert float(result.mediabox.width) == pytest.approx(a4_h, abs=0.5)
    assert int(result.get("/Rotate", 0)) == 0


def test_page_view_rotation_normalizes_values():
    """/Rotate 归一:模 360 落到 0/90/180/270 网格,非法与非 90 倍数按 0。"""
    from pypdf.generic import NameObject, NumberObject

    from file_toolbox.core.batch_pdf.pdf_utils import _page_view_rotation

    writer = PdfWriter()
    try:
        cases = ((90, 90), (270, 270), (-90, 270), (360, 0), (450, 90), (45, 0))
        for raw, expected in cases:
            page = writer.add_blank_page(width=100, height=100)
            page[NameObject("/Rotate")] = NumberObject(raw)
            assert _page_view_rotation(page) == expected, raw
        assert _page_view_rotation(writer.add_blank_page(width=100, height=100)) == 0
    finally:
        writer.close()


def test_rotate_image_to_match_matrix():
    """_rotate_image_to_match:仅强制方向 + auto 旋转 + 长边相反时转置。"""
    from PIL import Image

    from file_toolbox.core.batch_pdf.pdf_utils import _rotate_image_to_match

    wide = Image.new("RGB", (400, 200))
    tall = Image.new("RGB", (200, 400))
    square = Image.new("RGB", (300, 300))
    try:
        assert _rotate_image_to_match(wide, "portrait", "auto").size == (200, 400)
        assert _rotate_image_to_match(tall, "landscape", "auto").size == (400, 200)
        assert _rotate_image_to_match(wide, "landscape", "auto") is wide  # 长边已对齐
        assert _rotate_image_to_match(wide, "portrait", "none") is wide  # 未开启旋转
        assert _rotate_image_to_match(wide, "auto", "auto") is wide  # 方向保持原样
        assert _rotate_image_to_match(square, "portrait", "auto") is square  # 方图
    finally:
        wide.close()
        tall.close()
        square.close()


def test_convert_pdf_to_image_pdf_rotate_auto(tmp_path):
    """图片型:强制横向 + 自动旋转 → 输出横向 A4 画布(内容长边对齐纸张长边)。"""
    src = _make_pdf(tmp_path / "src.pdf", pages=1)  # 200x300 纵向
    out = tmp_path / "out.pdf"

    ok, msg = convert_pdf_to_image_pdf(
        src, out, paper_size="A4", orientation="landscape", rotate=ROTATE_AUTO
    )

    assert ok, msg
    page = PdfReader(out).pages[0]
    assert float(page.mediabox.width) > float(page.mediabox.height)


def test_paper_target_points_orientation_matrix():
    """_paper_target_points:三种方向 + auto 长边对齐的尺寸选择。"""
    from file_toolbox.core.batch_pdf.pdf_utils import _paper_target_points

    a4_w, a4_h = _a4_points()
    assert _paper_target_points("A4", "portrait", 400, 200) == (a4_w, a4_h)
    assert _paper_target_points("A4", "landscape", 200, 300) == (a4_h, a4_w)
    # auto:源页面宽>高 → 横放;否则纵放
    assert _paper_target_points("A4", "auto", 400, 200) == (a4_h, a4_w)
    assert _paper_target_points("A4", "auto", 200, 400) == (a4_w, a4_h)


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
