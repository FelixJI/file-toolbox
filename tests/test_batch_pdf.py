from pathlib import Path

from file_toolbox.core.batch_pdf import PDFGeneratorService
from file_toolbox.core.batch_pdf.constants import SUPPORTED_FORMATS


def test_get_file_type_word():
    svc = PDFGeneratorService()
    assert svc.get_file_type(Path("a.docx")) == "word"
    assert svc.get_file_type(Path("a.doc")) == "word"


def test_get_file_type_excel():
    svc = PDFGeneratorService()
    assert svc.get_file_type(Path("a.xlsx")) == "excel"


def test_get_file_type_image():
    svc = PDFGeneratorService()
    assert svc.get_file_type(Path("a.png")) == "image"


def test_get_file_type_pdf():
    svc = PDFGeneratorService()
    assert svc.get_file_type(Path("a.pdf")) == "pdf"


def test_get_file_type_unsupported():
    svc = PDFGeneratorService()
    assert svc.get_file_type(Path("a.xyz")) is None


def test_is_supported():
    svc = PDFGeneratorService()
    assert svc.is_supported(Path("a.docx")) is True
    assert svc.is_supported(Path("a.xyz")) is False


def test_get_output_filename(tmp_path):
    svc = PDFGeneratorService()
    src = tmp_path / "report.docx"
    out = svc.get_output_filename(src)
    assert out.name == "report.pdf"


def test_get_output_filename_avoids_collision(tmp_path):
    svc = PDFGeneratorService()
    src = tmp_path / "report.docx"
    (tmp_path / "report.pdf").write_bytes(b"%PDF-1.4")
    out = svc.get_output_filename(src)
    assert out.name == "report_1.pdf"


def test_supported_formats_complete():
    assert "word" in SUPPORTED_FORMATS
    assert ".docx" in SUPPORTED_FORMATS["word"]
    assert ".pptx" in SUPPORTED_FORMATS["powerpoint"]
