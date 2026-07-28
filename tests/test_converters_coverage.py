"""image_converter / word_converter 未覆盖分支补充测试。

image_converter:
- 行 138: 非 RGB/RGBA/LA/P 模式(如 'L' 灰度)→ convert("RGB")
- 行 164: paper_size + orientation=auto + 宽>高 → 交换纸张

word_converter:
- 行 73: orientation=auto_detect → _detect_orientation
"""

from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image

from file_toolbox.core.batch_pdf.constants import ORIENTATION_AUTO_DETECT
from file_toolbox.core.batch_pdf.converters.image_converter import ImageConverter
from file_toolbox.core.batch_pdf.converters.word_converter import WordConverter


def _make_png(path: Path, w: int, h: int, mode: str = "RGB") -> Path:
    Image.new(mode, (w, h), (128, 128, 128) if mode == "RGB" else 128).save(str(path))
    return path


# ===========================================================================
# ImageConverter
# ===========================================================================


def test_image_convert_grayscale_mode_converts_to_rgb(tmp_path):
    """灰度 PNG(模式 'L')→ 非 RGB/RGBA/LA/P → convert("RGB")(行 137-138)。"""
    src = _make_png(tmp_path / "gray.png", 50, 50, mode="L")
    out = tmp_path / "gray.pdf"
    conv = ImageConverter()
    ok, msg = conv.convert(
        src,
        out,
        config={"paper_size": "auto", "orientation": "auto"},
    )
    assert ok, msg
    assert out.exists()


def test_image_convert_paper_auto_orientation_wide_swaps(tmp_path):
    """paper_size=A4 + orientation=auto + 宽>高 → 交换纸张宽高(行 162-164)。"""
    src = _make_png(tmp_path / "wide.png", 400, 100)  # 宽 > 高
    out = tmp_path / "wide.pdf"
    conv = ImageConverter()
    ok, msg = conv.convert(
        src,
        out,
        config={
            "paper_size": "A4",
            "orientation": "auto",
            "scale_mode": "shrink_oversized",
            "dpi": 72,
        },
    )
    assert ok, msg
    assert out.exists()


def test_image_convert_paper_auto_orientation_tall_no_swap(tmp_path):
    """paper_size=A4 + orientation=auto + 高>宽 → 不交换(行 162 False)。"""
    src = _make_png(tmp_path / "tall.png", 100, 400)  # 高 > 宽
    out = tmp_path / "tall.pdf"
    conv = ImageConverter()
    ok, msg = conv.convert(
        src,
        out,
        config={
            "paper_size": "A4",
            "orientation": "auto",
            "scale_mode": "shrink_oversized",
            "dpi": 72,
        },
    )
    assert ok, msg
    assert out.exists()


# ===========================================================================
# WordConverter
# ===========================================================================


def test_word_convert_orientation_auto_detect(tmp_path):
    """orientation=auto_detect → 调用 _detect_orientation(行 72-73)。"""
    src = tmp_path / "a.docx"
    src.write_bytes(b"fake")
    out = tmp_path / "out.pdf"

    em = MagicMock()
    section = MagicMock()
    doc = MagicMock()
    doc.Sections = [section]
    em.init_word.return_value.Documents.Open.return_value = doc

    conv = WordConverter(em)
    ok, _ = conv.convert(
        src,
        out,
        config={"engine": "auto", "orientation": ORIENTATION_AUTO_DETECT, "paper_size": "A4"},
    )
    assert ok is True
