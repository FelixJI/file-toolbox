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


def test_excel_convert_hides_empty_sheets_and_restores(tmp_path):
    """空表(UsedRange None)被隐藏,导出后恢复 original_visibility。"""
    from file_toolbox.core.batch_pdf.constants import ORIENTATION_AUTO_DETECT

    src = _src(tmp_path, "a.xlsx")
    out = _out(tmp_path)

    em = MagicMock()
    empty_sheet = MagicMock()
    empty_sheet.UsedRange = None  # 空表 → 隐藏
    empty_sheet.Visible = 1  # 初始可见(MagicMock 属性可读写)

    wb = MagicMock()
    wb.Worksheets = [empty_sheet]  # 可迭代
    em.init_excel.return_value.Workbooks.Open.return_value = wb

    conv = ExcelConverter(em)
    # orientation=auto 触发 _detect_orientation(pragma,不执行真逻辑)
    ok, err = conv.convert(
        src, out, {"engine": "auto", "orientation": ORIENTATION_AUTO_DETECT}
    )
    assert ok is True
    assert err == ""


def test_excel_convert_sheet_usedrange_exception_swallowed(tmp_path):
    """遍历表时 UsedRange 访问抛异常 → except 吞掉,不崩。"""
    src = _src(tmp_path, "a.xlsx")
    out = _out(tmp_path)

    em = MagicMock()
    bad_sheet = MagicMock()
    type(bad_sheet).UsedRange = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("com boom"))
    )
    wb = MagicMock()
    wb.Worksheets = [bad_sheet]
    em.init_excel.return_value.Workbooks.Open.return_value = wb

    conv = ExcelConverter(em)
    ok, err = conv.convert(src, out, {"engine": "auto", "orientation": "portrait"})
    assert ok is True
    assert err == ""


def test_excel_convert_sets_paper_size(tmp_path):
    """paper_size 非 auto → 遍历可见表设 PageSetup.PaperSize(EXCEL_PAPER_MAP["A4"]=9)。"""
    src = _src(tmp_path, "a.xlsx")
    out = _out(tmp_path)

    em = MagicMock()
    sheet = MagicMock()
    sheet.Visible = True
    sheet.UsedRange = MagicMock()  # 非空 → 不隐藏
    wb = MagicMock()
    wb.Worksheets = [sheet]
    em.init_excel.return_value.Workbooks.Open.return_value = wb

    conv = ExcelConverter(em)
    ok, _ = conv.convert(src, out, {"engine": "auto", "paper_size": "A4"})
    assert ok is True
    assert sheet.PageSetup.PaperSize == 9


def test_excel_convert_unknown_paper_size_defaults_to_9(tmp_path):
    """paper_size 不在 EXCEL_PAPER_MAP → .get(weird, 9) 默认 9。"""
    src = _src(tmp_path, "a.xlsx")
    out = _out(tmp_path)

    em = MagicMock()
    sheet = MagicMock()
    sheet.Visible = True
    sheet.UsedRange = MagicMock()
    wb = MagicMock()
    wb.Worksheets = [sheet]
    em.init_excel.return_value.Workbooks.Open.return_value = wb

    conv = ExcelConverter(em)
    ok, _ = conv.convert(src, out, {"engine": "auto", "paper_size": "weird"})
    assert ok is True
    assert sheet.PageSetup.PaperSize == 9


def test_excel_convert_sets_orientation_landscape(tmp_path):
    """orientation=landscape → 设 Orientation=2。"""
    from file_toolbox.core.batch_pdf.constants import ORIENTATION_LANDSCAPE

    src = _src(tmp_path, "a.xlsx")
    out = _out(tmp_path)

    em = MagicMock()
    sheet = MagicMock()
    sheet.Visible = True
    sheet.UsedRange = MagicMock()
    wb = MagicMock()
    wb.Worksheets = [sheet]
    em.init_excel.return_value.Workbooks.Open.return_value = wb

    conv = ExcelConverter(em)
    ok, _ = conv.convert(
        src, out, {"engine": "auto", "orientation": ORIENTATION_LANDSCAPE}
    )
    assert ok is True
    assert sheet.PageSetup.Orientation == 2  # xlLandscape


def test_excel_convert_sets_orientation_portrait(tmp_path):
    """orientation=portrait → 设 Orientation=1。"""
    src = _src(tmp_path, "a.xlsx")
    out = _out(tmp_path)

    em = MagicMock()
    sheet = MagicMock()
    sheet.Visible = True
    sheet.UsedRange = MagicMock()
    wb = MagicMock()
    wb.Worksheets = [sheet]
    em.init_excel.return_value.Workbooks.Open.return_value = wb

    conv = ExcelConverter(em)
    ok, _ = conv.convert(src, out, {"engine": "auto", "orientation": "portrait"})
    assert ok is True
    assert sheet.PageSetup.Orientation == 1  # xlPortrait


def test_excel_convert_restore_visibility_suppresses_exception(tmp_path):
    """恢复可见性时抛异常 → contextlib.suppress 吞掉,不影响成功返回。

    用自定义类精确控制 Visible 的 get/set 行为(隐藏阶段设 False,
    恢复阶段设回原值时抛异常)。
    """

    class _RestoreBoomSheet:
        def __init__(self):
            self.UsedRange = None  # 空表
            self._visible = 1
            self._restore_attempted = False

        @property
        def Visible(self):
            return self._visible

        @Visible.setter
        def Visible(self, value):
            if self._restore_attempted:
                raise RuntimeError("restore boom")
            self._visible = value
            self._restore_attempted = True

    src = _src(tmp_path, "a.xlsx")
    out = _out(tmp_path)

    em = MagicMock()
    sheet = _RestoreBoomSheet()
    wb = MagicMock()
    wb.Worksheets = [sheet]
    em.init_excel.return_value.Workbooks.Open.return_value = wb

    conv = ExcelConverter(em)
    ok, err = conv.convert(src, out, {"engine": "auto", "orientation": "portrait"})
    # 恢复异常被 suppress,导出已成功 → ok=True
    assert ok is True
    assert err == ""


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


def test_ppt_convert_orientation_auto_detect(tmp_path):
    """orientation=auto → 调用 _detect_orientation(pragma,不执行真逻辑)。"""
    from file_toolbox.core.batch_pdf.constants import ORIENTATION_AUTO_DETECT

    src = _src(tmp_path, "a.pptx")
    out = _out(tmp_path)

    em = MagicMock()
    presentation = MagicMock()
    presentation.Slides.Count = 0
    em.init_ppt.return_value.Presentations.Open.return_value = presentation

    conv = PptConverter(em)
    ok, err = conv.convert(
        src, out, {"engine": "auto", "orientation": ORIENTATION_AUTO_DETECT}
    )
    assert ok is True
    assert err == ""


def test_ppt_convert_paper_size_portrait(tmp_path):
    """paper_size=A4, orientation=portrait → 不交换宽高,设 SlideWidth/Height。"""
    src = _src(tmp_path, "a.pptx")
    out = _out(tmp_path)

    em = MagicMock()
    presentation = MagicMock()
    presentation.Slides.Count = 0
    em.init_ppt.return_value.Presentations.Open.return_value = presentation

    conv = PptConverter(em)
    ok, _ = conv.convert(
        src, out, {"engine": "auto", "paper_size": "A4", "orientation": "portrait"}
    )
    assert ok is True
    # A4 = (595.28, 841.89), portrait 不交换
    assert presentation.PageSetup.SlideWidth == 595.28
    assert presentation.PageSetup.SlideHeight == 841.89


def test_ppt_convert_paper_size_landscape(tmp_path):
    """paper_size=A4, orientation=landscape → 交换宽高。"""
    from file_toolbox.core.batch_pdf.constants import ORIENTATION_LANDSCAPE

    src = _src(tmp_path, "a.pptx")
    out = _out(tmp_path)

    em = MagicMock()
    presentation = MagicMock()
    presentation.Slides.Count = 0
    em.init_ppt.return_value.Presentations.Open.return_value = presentation

    conv = PptConverter(em)
    ok, _ = conv.convert(
        src, out, {"engine": "auto", "paper_size": "A4", "orientation": ORIENTATION_LANDSCAPE}
    )
    assert ok is True
    # A4 = (595.28, 841.89), landscape 交换 → (841.89, 595.28)
    assert presentation.PageSetup.SlideWidth == 841.89
    assert presentation.PageSetup.SlideHeight == 595.28


def test_ppt_convert_paper_size_auto_orientation_swaps_by_ratio(tmp_path):
    """paper_size=A4, orientation=auto, 幻灯片宽>高 → 按 SlideWidth/Height 比例交换。"""
    src = _src(tmp_path, "a.pptx")
    out = _out(tmp_path)

    em = MagicMock()
    presentation = MagicMock()
    presentation.Slides.Count = 0
    presentation.PageSetup.SlideWidth = 1000  # 宽 > 高 → 横向 → 交换纸张
    presentation.PageSetup.SlideHeight = 500
    em.init_ppt.return_value.Presentations.Open.return_value = presentation

    conv = PptConverter(em)
    ok, _ = conv.convert(
        src, out, {"engine": "auto", "paper_size": "A4", "orientation": "auto"}
    )
    assert ok is True
    # auto + 宽>高 → 交换 A4 → (841.89, 595.28)
    assert presentation.PageSetup.SlideWidth == 841.89
    assert presentation.PageSetup.SlideHeight == 595.28


def test_ppt_convert_paper_size_auto_orientation_no_swap_when_tall(tmp_path):
    """paper_size=A4, orientation=auto, 幻灯片高>宽 → 不交换。"""
    src = _src(tmp_path, "a.pptx")
    out = _out(tmp_path)

    em = MagicMock()
    presentation = MagicMock()
    presentation.Slides.Count = 0
    presentation.PageSetup.SlideWidth = 500  # 高 > 宽 → 纵向 → 不交换
    presentation.PageSetup.SlideHeight = 1000
    em.init_ppt.return_value.Presentations.Open.return_value = presentation

    conv = PptConverter(em)
    ok, _ = conv.convert(
        src, out, {"engine": "auto", "paper_size": "A4", "orientation": "auto"}
    )
    assert ok is True
    # auto + 高>宽 → 不交换 → (595.28, 841.89)
    assert presentation.PageSetup.SlideWidth == 595.28
    assert presentation.PageSetup.SlideHeight == 841.89


def test_ppt_convert_paper_size_not_in_map_skips_setting(tmp_path):
    """paper_size 不在 PAPER_SIZES_POINTS → 不设 PageSetup(跳过 if 块)。"""
    src = _src(tmp_path, "a.pptx")
    out = _out(tmp_path)

    em = MagicMock()
    presentation = MagicMock()
    presentation.Slides.Count = 0
    em.init_ppt.return_value.Presentations.Open.return_value = presentation

    conv = PptConverter(em)
    ok, _ = conv.convert(
        src, out, {"engine": "auto", "paper_size": "weird", "orientation": "portrait"}
    )
    assert ok is True
    # PageSetup.SlideWidth/Height 未被赋值(MagicMock 无副作用即可)
