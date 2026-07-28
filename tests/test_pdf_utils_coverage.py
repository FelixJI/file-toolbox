"""pdf_utils 未覆盖分支补充测试。

覆盖行:
- 86: convert_pdf_to_image_pdf 图片非 RGB → convert("RGB")
- 97: 空 PDF(0 页)→ "PDF无内容"
- 115-116: convert_pdf_to_image_pdf 通用 except
- 272-273: merge_pdfs 通用 except
- 308-309: get_file_info stat 抛异常 → except pass
"""

from pathlib import Path
from unittest.mock import MagicMock

from file_toolbox.core.batch_pdf.pdf_utils import (
    convert_pdf_to_image_pdf,
    get_file_info,
    merge_pdfs,
)


def _make_pdf(path: Path, pages: int = 1) -> Path:
    import fitz

    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


# ---------------------------------------------------------------------------
# get_file_info:stat 抛异常(行 308-309)
# ---------------------------------------------------------------------------


def test_get_file_info_stat_exception_swallowed(tmp_path, monkeypatch):
    """file 存在但 stat 抛异常 → except pass,info 保留默认 size=0(行 308-309)。"""
    f = tmp_path / "a.pdf"
    f.write_bytes(b"fake")
    monkeypatch.setattr(Path, "stat", lambda self: (_ for _ in ()).throw(PermissionError("stat")))
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

    用 mock fitz.open 返回一个 len()=0 的假文档(真实 fitz 不能 save 0 页)。
    """
    src = tmp_path / "empty.pdf"
    src.write_bytes(b"fake")
    out = tmp_path / "out.pdf"

    import fitz

    fake_doc = MagicMock()
    fake_doc.__len__ = lambda self: 0  # 0 页
    monkeypatch.setattr(fitz, "open", lambda *a, **k: fake_doc)

    ok, err = convert_pdf_to_image_pdf(src, out, dpi=72)
    assert ok is False
    assert "PDF无内容" in err


# ---------------------------------------------------------------------------
# convert_pdf_to_image_pdf:通用 except(行 115-116)
# ---------------------------------------------------------------------------


def test_convert_pdf_to_image_pdf_generic_exception(tmp_path, monkeypatch):
    """fitz.open 抛异常 → 通用 except → (False, '转换图片型PDF失败: ...')(行 115-116)。"""
    src = tmp_path / "a.pdf"
    src.write_bytes(b"fake")
    out = tmp_path / "out.pdf"

    import fitz

    monkeypatch.setattr(
        fitz, "open", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fitz boom"))
    )
    ok, err = convert_pdf_to_image_pdf(src, out, dpi=72)
    assert ok is False
    assert "转换图片型PDF失败" in err
    assert "fitz boom" in err


def test_convert_pdf_to_image_pdf_non_rgb_converted(tmp_path, monkeypatch):
    """像素图产生非 RGB 图像 → convert("RGB")(行 86)。

    用 mock page.get_pixmap 返回灰度 PNG(模式 'L'),触发 convert 分支。
    """
    import io as _io

    from PIL import Image

    # 造一张灰度 PNG 字节(模式 'L',非 RGB)
    gray_img = Image.new("L", (5, 5), 128)
    buf = _io.BytesIO()
    gray_img.save(buf, format="PNG")
    gray_png_bytes = buf.getvalue()

    src = tmp_path / "a.pdf"
    src.write_bytes(b"fake")
    out = tmp_path / "out.pdf"

    import fitz

    fake_pix = MagicMock()
    fake_pix.tobytes.return_value = gray_png_bytes
    fake_page = MagicMock()
    fake_page.get_pixmap.return_value = fake_pix
    fake_doc = MagicMock()
    fake_doc.__len__ = lambda self: 1
    fake_doc.__getitem__ = lambda self, i: fake_page
    monkeypatch.setattr(fitz, "open", lambda *a, **k: fake_doc)
    monkeypatch.setattr(fitz, "Matrix", lambda x, y: MagicMock())

    ok, err = convert_pdf_to_image_pdf(src, out, dpi=72)
    assert ok is True
    assert err == ""


# ---------------------------------------------------------------------------
# merge_pdfs:通用 except(行 272-273)
# ---------------------------------------------------------------------------


def test_merge_pdfs_generic_exception(tmp_path, monkeypatch):
    """fitz.open 抛异常 → 通用 except → (False, '合并PDF失败: ...')(行 272-273)。"""
    src = tmp_path / "a.pdf"
    src.write_bytes(b"fake")
    out = tmp_path / "merged.pdf"

    import fitz

    monkeypatch.setattr(
        fitz, "open", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("merge boom"))
    )
    ok, err = merge_pdfs([src], out)
    assert ok is False
    assert "合并PDF失败" in err
    assert "merge boom" in err
