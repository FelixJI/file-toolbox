"""batch_pdf service 未覆盖分支补充测试。

覆盖行:
- 82: get_output_filename _1.pdf 也存在 → counter += 1 找 _2.pdf
- 88: get_engine_info 委托
- 92: detect_engines_async 委托
- 128: _convert_pdf_to_image_pdf 委托
- 156-160: generate_pdf pdf + image 分支(显式参数)
- 244: merge_pdfs_service 委托
- 367: get_file_info_service 委托
"""

from unittest.mock import MagicMock

from file_toolbox.core.batch_pdf.constants import PDF_TYPE_IMAGE
from file_toolbox.core.batch_pdf.service import PDFGeneratorService

# ---------------------------------------------------------------------------
# get_output_filename:counter += 1(行 82)
# ---------------------------------------------------------------------------


def test_get_output_filename_increments_past_existing(tmp_path):
    """report.pdf 和 report_1.pdf 都存在 → 找 report_2.pdf(行 82)。"""
    svc = PDFGeneratorService()
    src = tmp_path / "report.docx"
    (tmp_path / "report.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "report_1.pdf").write_bytes(b"%PDF-1.4")
    out = svc.get_output_filename(src)
    assert out.name == "report_2.pdf"


def test_get_output_filename_increments_multiple(tmp_path):
    """三个已存在 → _3.pdf。"""
    svc = PDFGeneratorService()
    src = tmp_path / "doc.docx"
    (tmp_path / "doc.pdf").write_bytes(b"x")
    (tmp_path / "doc_1.pdf").write_bytes(b"x")
    (tmp_path / "doc_2.pdf").write_bytes(b"x")
    out = svc.get_output_filename(src)
    assert out.name == "doc_3.pdf"


def test_get_output_filename_explicit_output_dir(tmp_path):
    """显式 output_dir(行 70-71 已覆盖,补确认)。"""
    svc = PDFGeneratorService()
    src = tmp_path / "report.docx"
    out_dir = tmp_path / "sub"
    out_dir.mkdir()
    out = svc.get_output_filename(src, out_dir)
    assert out.parent == out_dir
    assert out.name == "report.pdf"


# ---------------------------------------------------------------------------
# get_engine_info / detect_engines_async 委托(行 88, 92)
# ---------------------------------------------------------------------------


def test_get_engine_info_delegates():
    svc = PDFGeneratorService()
    svc._engine_manager = MagicMock()
    svc._engine_manager.get_engine_info.return_value = "Word"
    assert svc.get_engine_info() == "Word"
    svc._engine_manager.get_engine_info.assert_called_once()


def test_detect_engines_async_delegates():
    svc = PDFGeneratorService()
    svc._engine_manager = MagicMock()

    def cb(info: str) -> None:
        return None

    svc.detect_engines_async(cb)
    svc._engine_manager.detect_engines_async.assert_called_once_with(cb)


# ---------------------------------------------------------------------------
# _convert_pdf_to_image_pdf 委托(行 128)
# ---------------------------------------------------------------------------


def test_convert_pdf_to_image_pdf_delegates(tmp_path, monkeypatch):
    """_convert_pdf_to_image_pdf 委托 convert_pdf_to_image_pdf(行 128)。"""
    from file_toolbox.core.batch_pdf import service as svc_mod

    monkeypatch.setattr(
        svc_mod, "convert_pdf_to_image_pdf", lambda *a, **k: (True, "ok")
    )
    svc = PDFGeneratorService()
    ok, err = svc._convert_pdf_to_image_pdf(
        tmp_path / "in.pdf", tmp_path / "out.pdf", dpi=72
    )
    assert (ok, err) == (True, "ok")


# ---------------------------------------------------------------------------
# generate_pdf:pdf + image 分支显式参数(行 152-165)
# ---------------------------------------------------------------------------


def test_generate_pdf_image_type_explicit_config(tmp_path, monkeypatch):
    """pdf + pdf_type=image → _convert_pdf_to_image_pdf 用显式 dpi/paper 等(行 154-165)。"""
    svc = PDFGeneratorService()
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4")
    out = tmp_path / "out.pdf"

    captured = {}

    def fake_convert(in_pdf, out_pdf, **kwargs):
        captured.update(kwargs)
        return True, ""

    monkeypatch.setattr(svc, "_convert_pdf_to_image_pdf", fake_convert)
    ok, err = svc.generate_pdf(
        src,
        out,
        {
            "pdf_type": PDF_TYPE_IMAGE,
            "dpi": 300,
            "paper_size": "A4",
            "orientation": "portrait",
            "scale_mode": "fit_margin",
        },
    )
    assert ok is True
    assert captured["dpi"] == 300
    assert captured["paper_size"] == "A4"
    assert captured["orientation"] == "portrait"
    assert captured["scale_mode"] == "fit_margin"


# ---------------------------------------------------------------------------
# merge_pdfs_service 委托(行 244)
# ---------------------------------------------------------------------------


def test_merge_pdfs_service_delegates(tmp_path, monkeypatch):
    from file_toolbox.core.batch_pdf import service as svc_mod

    monkeypatch.setattr(svc_mod, "merge_pdfs", lambda *a, **k: (True, ""))
    svc = PDFGeneratorService()
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4")
    ok, err = svc.merge_pdfs([src], tmp_path / "merged.pdf")
    assert (ok, err) == (True, "")


# ---------------------------------------------------------------------------
# get_file_info_service 委托(行 367)
# ---------------------------------------------------------------------------


def test_get_file_info_service_returns_dict(tmp_path):
    """get_file_info 委托 get_file_info(行 367)。"""
    svc = PDFGeneratorService()
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    info = svc.get_file_info(f)
    assert isinstance(info, dict)
    assert info["name"] == "a.docx"
    assert info["supported"] is True
