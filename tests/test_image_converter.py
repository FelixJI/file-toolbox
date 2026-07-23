"""file_toolbox.core.batch_pdf.converters.image_converter 单元测试。

覆盖 ImageConverter.convert / _detect_orientation / _apply_scale / _resize_to_fit。
仅依赖 PIL,不触发任何 Office COM。
"""

from pathlib import Path

import pytest

pytest.importorskip("PIL")  # noqa: E402

from PIL import Image  # noqa: E402

from file_toolbox.core.batch_pdf.constants import (  # noqa: E402
    ORIENTATION_AUTO_DETECT,
    ORIENTATION_LANDSCAPE,
    PAPER_SIZES,
    SCALE_ACTUAL_SIZE,
    SCALE_FIT_MARGIN,
)
from file_toolbox.core.batch_pdf.converters.image_converter import (  # noqa: E402
    ImageConverter,
)

# --- fixture -------------------------------------------------------------------


@pytest.fixture
def converter() -> ImageConverter:
    return ImageConverter()


def _make_png(path: Path, w: int, h: int, mode: str = "RGB") -> Path:
    """生成一个纯色 PNG(可指定颜色模式,如 RGBA)。"""
    Image.new(mode, (w, h)).save(str(path))
    return path


# --- convert -------------------------------------------------------------------


def test_convert_png_to_pdf(converter, tmp_path):
    src = _make_png(tmp_path / "a.png", 200, 100)
    out = tmp_path / "a.pdf"

    ok, msg = converter.convert(
        src,
        out,
        config={"paper_size": "auto", "orientation": "auto", "scale_mode": "shrink_oversized"},
    )

    assert ok, msg
    assert out.exists()
    assert out.stat().st_size > 0


def test_convert_png_to_pdf_minimal_config(converter, tmp_path):
    """空 config:走全部默认值(paper_size=auto 跳过 _apply_scale)。"""
    src = _make_png(tmp_path / "b.png", 50, 50)
    out = tmp_path / "b.pdf"

    ok, msg = converter.convert(src, out, config={})

    assert ok, msg
    assert out.exists()


def test_convert_rgba_png(converter, tmp_path):
    """RGBA 图片:走 alpha 合成到白底的分支。"""
    src = _make_png(tmp_path / "rgba.png", 100, 100, mode="RGBA")
    out = tmp_path / "rgba.pdf"

    ok, msg = converter.convert(src, out, config={})

    assert ok, msg
    assert out.exists()


def test_convert_palette_png(converter, tmp_path):
    """P 模式图片:走 convert('RGBA') 后合成分支。"""
    src = _make_png(tmp_path / "p.png", 80, 80, mode="P")
    out = tmp_path / "p.pdf"

    ok, msg = converter.convert(src, out, config={})

    assert ok, msg
    assert out.exists()


def test_convert_with_paper_and_auto_detect(converter, tmp_path):
    """指定 A4 + orientation=auto_detect + actual_size,触发 _detect_orientation
    + _apply_scale 双分支。"""
    src = _make_png(tmp_path / "wide.png", 400, 100)  # 宽图 -> landscape
    out = tmp_path / "wide.pdf"

    ok, msg = converter.convert(
        src,
        out,
        config={
            "paper_size": "A4",
            "orientation": ORIENTATION_AUTO_DETECT,
            "scale_mode": SCALE_ACTUAL_SIZE,
            "dpi": 72,
        },
    )

    assert ok, msg
    assert out.exists()


def test_convert_with_paper_portrait_fit_margin(converter, tmp_path):
    """A4 portrait + fit_margin + 显式 dpi:覆盖 fit_margin 缩放分支。"""
    src = _make_png(tmp_path / "tall.png", 100, 400)  # 高图
    out = tmp_path / "tall.pdf"

    ok, msg = converter.convert(
        src,
        out,
        config={
            "paper_size": "A4",
            "orientation": "portrait",
            "scale_mode": SCALE_FIT_MARGIN,
            "dpi": 150,
        },
    )

    assert ok, msg
    assert out.exists()


def test_convert_nonexistent_file_returns_error(converter, tmp_path):
    out = tmp_path / "x.pdf"

    ok, msg = converter.convert(tmp_path / "nope.png", out, config={})

    assert ok is False
    assert msg != ""


# --- _detect_orientation -------------------------------------------------------


def test_detect_orientation_wide(converter, tmp_path):
    src = _make_png(tmp_path / "wide.png", 400, 100)
    assert converter._detect_orientation(src) == ORIENTATION_LANDSCAPE


def test_detect_orientation_tall(converter, tmp_path):
    src = _make_png(tmp_path / "tall.png", 100, 400)
    assert converter._detect_orientation(src) == "portrait"


def test_detect_orientation_square_is_portrait(converter, tmp_path):
    """正方形图片:width 不大于 height => portrait。"""
    src = _make_png(tmp_path / "sq.png", 200, 200)
    assert converter._detect_orientation(src) == "portrait"


def test_detect_orientation_invalid_file_defaults_portrait(converter, tmp_path):
    """损坏/非图片文件:except 分支吞掉异常,返回默认 'portrait'。"""
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not a real png")
    assert converter._detect_orientation(bad) == "portrait"


# --- _apply_scale --------------------------------------------------------------


def test_apply_scale_actual_size(converter):
    """actual_size:返回的画布尺寸 = 传入的 paper 像素。"""
    img = Image.new("RGB", (50, 50))
    result = converter._apply_scale(img, 600, 800, SCALE_ACTUAL_SIZE)
    assert result.size == (600, 800)


def test_apply_scale_fit_margin(converter):
    """fit_margin:返回画布 = 原纸张尺寸(缩放在内部完成)。"""
    img = Image.new("RGB", (2000, 2000))
    result = converter._apply_scale(img, 600, 800, SCALE_FIT_MARGIN)
    assert result.size == (600, 800)


def test_apply_scale_shrink_oversized(converter):
    """默认 shrink_oversized:画布尺寸 = 传入的 paper 像素。"""
    img = Image.new("RGB", (2000, 2000))
    result = converter._apply_scale(img, 600, 800, "shrink_oversized")
    assert result.size == (600, 800)


# --- _resize_to_fit (staticmethod) ---------------------------------------------


def test_resize_to_fit_unchanged(converter):
    """图片尺寸已等于目标:返回原图。"""
    img = Image.new("RGB", (100, 200))
    assert converter._resize_to_fit(img, 100, 200).size == (100, 200)


def test_resize_to_fit_enlarges(converter):
    """支持放大(区别于 thumbnail)。"""
    img = Image.new("RGB", (50, 50))
    assert converter._resize_to_fit(img, 200, 200).size == (200, 200)


def test_resize_to_fit_keeps_aspect_ratio(converter):
    """等比缩放保持宽高比。"""
    img = Image.new("RGB", (400, 200))  # 2:1
    out = converter._resize_to_fit(img, 200, 100)
    assert out.size == (200, 100)  # 仍为 2:1


# --- 辅助:确保 A4 像素尺寸常量与计算一致(回归) -----------------------------


def test_a4_paper_pixel_size_at_72dpi():
    """回归:A4 在 72dpi 下的整数像素尺寸,用于 _apply_scale 期望值校验。"""
    paper_w_mm, paper_h_mm = PAPER_SIZES["A4"]
    w = int(paper_w_mm * 72 / 25.4)
    h = int(paper_h_mm * 72 / 25.4)
    assert (w, h) == (595, 841)
