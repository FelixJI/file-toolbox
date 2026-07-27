"""Word/Excel/PPT 转 PDF 转换器 convert() 的 COM 调度逻辑测试。

用 MagicMock 模拟 engine_manager.init_* 返回的 app 与 Documents/Workbooks/Presentations
.Open 返回的文档对象,验证 convert() 的控制流契约:
- 成功路径:调用正确的导出方法 + Close,返回 (True, "")
- Open 失败 / 导出失败:被 except 捕获,返回 (False, "...失败: ..."),不崩溃

局限(见 plan 风险提示):MagicMock 自动接受任意属性访问,本测试验证的是**控制流顺序
与异常兜底**,不保证 ExportAsFixedFormat 的参数签名与真实 Office COM 一致——后者依赖
本地真 Office 手测或 self-hosted runner。
"""

from pathlib import Path
from unittest.mock import MagicMock

from file_toolbox.core.batch_pdf.converters.excel_converter import ExcelConverter
from file_toolbox.core.batch_pdf.converters.ppt_converter import PptConverter
from file_toolbox.core.batch_pdf.converters.word_converter import WordConverter


def _src(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"fake office file")
    return p


def _out(tmp_path: Path, name: str = "out.pdf") -> Path:
    return tmp_path / name


# ===========================================================================
# WordConverter.convert
# ===========================================================================


def test_word_convert_success(tmp_path):
    """成功路径:init_word → Open → ExportAsFixedFormat → Close,返回 (True, "")。"""
    src = _src(tmp_path, "a.docx")
    out = _out(tmp_path)

    em = MagicMock()
    doc = MagicMock()
    em.init_word.return_value.Documents.Open.return_value = doc

    conv = WordConverter(em)
    ok, err = conv.convert(
        src, out, {"engine": "auto", "paper_size": "auto", "orientation": "auto"}
    )
    assert ok is True
    assert err == ""
    em.init_word.assert_called_once_with("auto")
    em.init_word.return_value.Documents.Open.assert_called_once()
    doc.ExportAsFixedFormat.assert_called_once()
    doc.Close.assert_called_once_with(False)


def test_word_convert_open_failure(tmp_path):
    """Documents.Open 抛异常 → (False, "Word转PDF失败: ...")。"""
    src = _src(tmp_path, "a.docx")
    out = _out(tmp_path)

    em = MagicMock()
    em.init_word.return_value.Documents.Open.side_effect = RuntimeError("open boom")

    conv = WordConverter(em)
    ok, err = conv.convert(src, out, {"engine": "auto"})
    assert ok is False
    assert "Word转PDF失败" in err
    assert "open boom" in err


def test_word_convert_export_failure(tmp_path):
    """ExportAsFixedFormat 抛异常 → (False, ...),被 except 兜底不崩溃。"""
    src = _src(tmp_path, "a.docx")
    out = _out(tmp_path)

    em = MagicMock()
    doc = MagicMock()
    doc.ExportAsFixedFormat.side_effect = RuntimeError("export boom")
    em.init_word.return_value.Documents.Open.return_value = doc

    conv = WordConverter(em)
    ok, err = conv.convert(src, out, {"engine": "auto"})
    assert ok is False
    assert "export boom" in err


def test_word_convert_sets_paper_and_orientation(tmp_path):
    """paper_size/orientation 非 auto 时,遍历 Sections 设置 PageSetup(赋值不报错即可)。"""
    src = _src(tmp_path, "a.docx")
    out = _out(tmp_path)

    em = MagicMock()
    section = MagicMock()
    doc = MagicMock()
    doc.Sections = [section]  # 可迭代 + 含 PageSetup(MagicMock 自动接受赋值)
    em.init_word.return_value.Documents.Open.return_value = doc

    conv = WordConverter(em)
    ok, _err = conv.convert(
        src, out, {"engine": "auto", "paper_size": "A4", "orientation": "portrait"}
    )
    assert ok is True


# ===========================================================================
# ExcelConverter.convert
# ===========================================================================


def test_excel_convert_success(tmp_path):
    """成功路径:init_excel → Open → ExportAsFixedFormat → Close,返回 (True, "")。"""
    src = _src(tmp_path, "a.xlsx")
    out = _out(tmp_path)

    em = MagicMock()
    wb = MagicMock()
    # Worksheets 可迭代(空表检测循环);Worksheets() 调用返回 sheet(_detect_orientation 用)
    wb.Worksheets = MagicMock()
    wb.Worksheets.__iter__ = lambda self: iter([])
    wb.Worksheets.Count = 0
    em.init_excel.return_value.Workbooks.Open.return_value = wb

    conv = ExcelConverter(em)
    ok, err = conv.convert(src, out, {"engine": "auto", "orientation": "auto"})
    assert ok is True
    assert err == ""
    em.init_excel.assert_called_once_with("auto")
    wb.ExportAsFixedFormat.assert_called_once()
    wb.Close.assert_called_once_with(False)


def test_excel_convert_open_failure(tmp_path):
    """Workbooks.Open 抛异常 → (False, "Excel转PDF失败: ...")。"""
    src = _src(tmp_path, "a.xlsx")
    out = _out(tmp_path)

    em = MagicMock()
    em.init_excel.return_value.Workbooks.Open.side_effect = RuntimeError("open boom")

    conv = ExcelConverter(em)
    ok, err = conv.convert(src, out, {"engine": "auto"})
    assert ok is False
    assert "Excel转PDF失败" in err


def test_excel_convert_export_failure(tmp_path):
    """ExportAsFixedFormat 抛异常 → (False, ...),兜底不崩溃。"""
    src = _src(tmp_path, "a.xlsx")
    out = _out(tmp_path)

    em = MagicMock()
    wb = MagicMock()
    wb.ExportAsFixedFormat.side_effect = RuntimeError("export boom")
    wb.Worksheets = MagicMock()
    wb.Worksheets.__iter__ = lambda self: iter([])
    em.init_excel.return_value.Workbooks.Open.return_value = wb

    conv = ExcelConverter(em)
    ok, err = conv.convert(src, out, {"engine": "auto"})
    assert ok is False
    assert "export boom" in err


# ===========================================================================
# PptConverter.convert
# ===========================================================================


def test_ppt_convert_success(tmp_path):
    """成功路径:init_ppt → Open → ExportAsFixedFormat → Close,返回 (True, "")。"""
    src = _src(tmp_path, "a.pptx")
    out = _out(tmp_path)

    em = MagicMock()
    presentation = MagicMock()
    presentation.Slides.Count = 0
    em.init_ppt.return_value.Presentations.Open.return_value = presentation

    conv = PptConverter(em)
    ok, err = conv.convert(src, out, {"engine": "auto", "orientation": "auto"})
    assert ok is True
    assert err == ""
    em.init_ppt.assert_called_once_with("auto")
    presentation.ExportAsFixedFormat.assert_called_once()
    presentation.Close.assert_called_once()


def test_ppt_convert_open_failure(tmp_path):
    """Presentations.Open 抛异常 → (False, "PPT转PDF失败: ...")。"""
    src = _src(tmp_path, "a.pptx")
    out = _out(tmp_path)

    em = MagicMock()
    em.init_ppt.return_value.Presentations.Open.side_effect = RuntimeError("open boom")

    conv = PptConverter(em)
    ok, err = conv.convert(src, out, {"engine": "auto"})
    assert ok is False
    assert "PPT转PDF失败" in err


def test_ppt_convert_export_failure(tmp_path):
    """ExportAsFixedFormat 抛异常 → (False, ...),兜底不崩溃。"""
    src = _src(tmp_path, "a.pptx")
    out = _out(tmp_path)

    em = MagicMock()
    presentation = MagicMock()
    presentation.ExportAsFixedFormat.side_effect = RuntimeError("export boom")
    presentation.Slides.Count = 0
    em.init_ppt.return_value.Presentations.Open.return_value = presentation

    conv = PptConverter(em)
    ok, err = conv.convert(src, out, {"engine": "auto"})
    assert ok is False
    assert "export boom" in err
