from pathlib import Path

import pytest

from file_toolbox.core.batch_pdf import PDFGeneratorService
from file_toolbox.core.batch_pdf.constants import (
    OUTPUT_MERGE,
    OUTPUT_SEPARATE,
    PDF_TYPE_EDITABLE,
    PDF_TYPE_IMAGE,
    SUPPORTED_FORMATS,
)


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


# ---------------------------------------------------------------------------
# generate_pdf:文件类型分发与 PDF 复制/图片型分支(mock 掉 COM 转换器)
# ---------------------------------------------------------------------------


@pytest.fixture
def svc_stubbable():
    """构造 service(转换器未 mock,generate_pdf 内部分发可被单独 stub)。"""
    return PDFGeneratorService()


def test_generate_pdf_unsupported_type(svc_stubbable, tmp_path):
    ok, err = svc_stubbable.generate_pdf(tmp_path / "a.xyz", tmp_path / "out.pdf", {})
    assert ok is False
    assert "不支持" in err


def test_generate_pdf_pdf_editable_copies(svc_stubbable, tmp_path):
    """已存在 PDF + editable → 直接复制到输出。"""
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 dummy")
    out = tmp_path / "out.pdf"
    ok, err = svc_stubbable.generate_pdf(src, out, {"pdf_type": PDF_TYPE_EDITABLE})
    assert ok is True
    assert out.exists()
    assert out.read_bytes() == src.read_bytes()


def test_generate_pdf_pdf_editable_copy_failure(svc_stubbable, tmp_path):
    """PDF 复制失败(目标目录不存在)→ 返回错误。"""
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4")
    out = tmp_path / "no_such_dir" / "out.pdf"
    ok, err = svc_stubbable.generate_pdf(src, out, {"pdf_type": PDF_TYPE_EDITABLE})
    assert ok is False
    assert "复制PDF失败" in err


def test_generate_pdf_image_type_for_office(svc_stubbable, tmp_path, monkeypatch):
    """图片型 + 非 PDF 文件 → 走临时 PDF + 转 image 分支(stub 两个转换)。"""
    src = tmp_path / "a.docx"
    src.write_bytes(b"stub")
    out = tmp_path / "out.pdf"
    monkeypatch.setattr(svc_stubbable, "_generate_editable_pdf", lambda s, o, c: (True, ""))
    monkeypatch.setattr(svc_stubbable, "_convert_pdf_to_image_pdf", lambda *a, **k: (True, ""))
    ok, err = svc_stubbable.generate_pdf(src, out, {"pdf_type": PDF_TYPE_IMAGE})
    assert ok is True


def test_generate_pdf_image_type_editable_gen_fails(svc_stubbable, tmp_path, monkeypatch):
    """图片型但可编辑 PDF 生成失败 → 提前返回错误(不进入转换)。"""
    src = tmp_path / "a.docx"
    src.write_bytes(b"stub")
    out = tmp_path / "out.pdf"
    monkeypatch.setattr(
        svc_stubbable, "_generate_editable_pdf", lambda s, o, c: (False, "no office")
    )
    ok, err = svc_stubbable.generate_pdf(src, out, {"pdf_type": PDF_TYPE_IMAGE})
    assert ok is False
    assert err == "no office"


def test_generate_pdf_image_type_convert_raises(svc_stubbable, tmp_path, monkeypatch):
    """图片型,转换抛异常 → 走 except 清理临时文件并报错。"""
    src = tmp_path / "a.docx"
    src.write_bytes(b"stub")
    out = tmp_path / "out.pdf"

    def boom(*a, **k):
        raise RuntimeError("convert blew up")

    monkeypatch.setattr(svc_stubbable, "_generate_editable_pdf", lambda s, o, c: (True, ""))
    monkeypatch.setattr(svc_stubbable, "_convert_pdf_to_image_pdf", boom)
    ok, err = svc_stubbable.generate_pdf(src, out, {"pdf_type": PDF_TYPE_IMAGE})
    assert ok is False
    assert "图片型PDF" in err


def test_generate_editable_pdf_unknown_type(svc_stubbable, tmp_path):
    """_generate_editable_pdf 收到未知类型 → 返回错误(覆盖 else 分支)。"""
    ok, err = svc_stubbable._generate_editable_pdf(tmp_path / "a.xyz", tmp_path / "out.pdf", {})
    assert ok is False
    assert "未知" in err


def test_generate_pdf_editable_word_dispatch(svc_stubbable, tmp_path, monkeypatch):
    """editable + word 文件 → 调用 generate_pdf_from_word(确认分发命中)。"""
    src = tmp_path / "a.docx"
    src.write_bytes(b"stub")
    out = tmp_path / "out.pdf"
    called = {}

    def fake_word(s, o, c):
        called["word"] = True
        return True, ""

    monkeypatch.setattr(svc_stubbable, "generate_pdf_from_word", fake_word)
    ok, err = svc_stubbable.generate_pdf(src, out, {"pdf_type": PDF_TYPE_EDITABLE})
    assert ok is True
    assert called.get("word") is True


def test_generate_pdf_editable_excel_image_dispatch(svc_stubbable, tmp_path, monkeypatch):
    """editable 分发命中 excel/image 分支(覆盖 _generate_editable_pdf 全部分支)。"""
    # excel
    src_x = tmp_path / "a.xlsx"
    src_x.write_bytes(b"stub")
    monkeypatch.setattr(svc_stubbable, "generate_pdf_from_excel", lambda s, o, c: (True, ""))
    ok, _ = svc_stubbable.generate_pdf(src_x, tmp_path / "o1.pdf", {"pdf_type": PDF_TYPE_EDITABLE})
    assert ok is True

    # image
    src_i = tmp_path / "a.png"
    src_i.write_bytes(b"stub")
    monkeypatch.setattr(svc_stubbable, "generate_pdf_from_image", lambda s, o, c: (True, ""))
    ok, _ = svc_stubbable.generate_pdf(src_i, tmp_path / "o2.pdf", {"pdf_type": PDF_TYPE_EDITABLE})
    assert ok is True

    # powerpoint
    src_p = tmp_path / "a.pptx"
    src_p.write_bytes(b"stub")
    monkeypatch.setattr(svc_stubbable, "generate_pdf_from_ppt", lambda s, o, c: (True, ""))
    ok, _ = svc_stubbable.generate_pdf(src_p, tmp_path / "o3.pdf", {"pdf_type": PDF_TYPE_EDITABLE})
    assert ok is True


# ---------------------------------------------------------------------------
# batch_generate:合并模式 / 进度回调 / 输出目录 选择
# ---------------------------------------------------------------------------


def test_batch_generate_merge_mode_success(tmp_path, monkeypatch):
    svc = PDFGeneratorService()
    files = [tmp_path / "a.docx", tmp_path / "b.docx"]
    for f in files:
        f.write_bytes(b"stub")
    monkeypatch.setattr(svc, "generate_pdf", lambda src, out, cfg: (True, ""))
    monkeypatch.setattr(svc, "merge_pdfs", lambda pdfs, out, mode: (True, ""))

    config = {
        "output_mode": OUTPUT_MERGE,
        "same_as_source": True,
        "merge_filename": "Merged.pdf",
    }
    progress = []
    results = svc.batch_generate(files, config, progress_callback=lambda *a: progress.append(a))

    # 两个源文件,合并后它们的 output 都指向合并文件
    assert all(r["success"] for r in results)
    assert all(r["output"].name == "Merged.pdf" for r in results)
    assert progress  # 进度回调被调用


def test_batch_generate_merge_failure_appends_error(tmp_path, monkeypatch):
    svc = PDFGeneratorService()
    files = [tmp_path / "a.docx"]
    files[0].write_bytes(b"stub")
    monkeypatch.setattr(svc, "generate_pdf", lambda src, out, cfg: (True, ""))
    monkeypatch.setattr(svc, "merge_pdfs", lambda pdfs, out, mode: (False, "merge broke"))

    config = {"output_mode": OUTPUT_MERGE, "same_as_source": True, "merge_filename": "M.pdf"}
    results = svc.batch_generate(files, config)

    # 合并失败 → 末尾追加一个失败结果
    assert results[-1]["success"] is False
    assert results[-1]["error"] == "merge broke"


def test_batch_generate_merge_output_dir_collision(tmp_path, monkeypatch):
    """合并输出文件已存在 → 自动加序号。"""
    svc = PDFGeneratorService()
    files = [tmp_path / "a.docx"]
    files[0].write_bytes(b"stub")
    (tmp_path / "Merged.pdf").write_bytes(b"existing")  # 制造冲突
    monkeypatch.setattr(svc, "generate_pdf", lambda src, out, cfg: (True, ""))

    captured = {}

    def fake_merge(pdfs, out, mode):
        captured["out"] = out
        return True, ""

    monkeypatch.setattr(svc, "merge_pdfs", fake_merge)
    config = {"output_mode": OUTPUT_MERGE, "same_as_source": True, "merge_filename": "Merged.pdf"}
    svc.batch_generate(files, config)
    assert captured["out"].name == "Merged_1.pdf"


def test_batch_generate_merge_explicit_output_dir(tmp_path, monkeypatch):
    """same_as_source=False → 合并输出到指定 output_dir。"""
    svc = PDFGeneratorService()
    files = [tmp_path / "a.docx"]
    files[0].write_bytes(b"stub")
    out_dir = tmp_path / "outdir"
    out_dir.mkdir()
    monkeypatch.setattr(svc, "generate_pdf", lambda src, out, cfg: (True, ""))

    captured = {}

    def fake_merge(pdfs, out, mode):
        captured["out"] = out
        return True, ""

    monkeypatch.setattr(svc, "merge_pdfs", fake_merge)
    config = {
        "output_mode": OUTPUT_MERGE,
        "same_as_source": False,
        "output_dir": out_dir,
        "merge_filename": "X.pdf",
    }
    svc.batch_generate(files, config)
    assert captured["out"] == out_dir / "X.pdf"


def test_batch_generate_separate_progress_callback(tmp_path, monkeypatch):
    svc = PDFGeneratorService()
    files = [tmp_path / "a.docx", tmp_path / "b.docx"]
    for f in files:
        f.write_bytes(b"stub")
    monkeypatch.setattr(svc, "generate_pdf", lambda src, out, cfg: (True, ""))
    calls = []
    svc.batch_generate(
        files,
        {"output_mode": OUTPUT_SEPARATE, "same_as_source": True},
        progress_callback=lambda i, t, m: calls.append((i, t, m)),
    )
    assert calls[-1][0] == 2  # 末尾 progress_callback(total,total,...)


def test_batch_generate_failed_file_not_added_to_merge(tmp_path, monkeypatch):
    svc = PDFGeneratorService()
    files = [tmp_path / "a.docx"]
    files[0].write_bytes(b"stub")
    monkeypatch.setattr(svc, "generate_pdf", lambda src, out, cfg: (False, "fail"))
    monkeypatch.setattr(svc, "merge_pdfs", lambda pdfs, out, mode: (True, ""))
    config = {"output_mode": OUTPUT_MERGE, "same_as_source": True}
    # 没有成功的 PDF → 不进入合并分支,merge_pdfs 不应被调用
    results = svc.batch_generate(files, config)
    assert len(results) == 1
    assert results[0]["success"] is False
