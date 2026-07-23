"""Word/Excel/PPT 转 PDF 转换器的纯逻辑方法单元测试。

覆盖:
- `_get_paper_size_word` / `_get_orientation_word`(WordConverter:纯字典查找/分支)
- `PptConverter.PAPER_SIZES_POINTS`(类级常量)
- `_detect_orientation`(三者):仅读取少量可 stub 的属性
  (doc.Sections.Count / .Sections(1).PageSetup 等),用 SimpleNamespace 构造假对象。

`convert()` 及 `__init__` 依赖 COM 的部分不在本测试范围。
通过 `Converter.__new__(Converter)` 绕过 `__init__`(其注入 engine_manager)。
"""

from types import SimpleNamespace

from file_toolbox.core.batch_pdf.constants import (
    ORIENTATION_LANDSCAPE,
    WORD_PAPER_MAP,
)
from file_toolbox.core.batch_pdf.converters.excel_converter import ExcelConverter
from file_toolbox.core.batch_pdf.converters.ppt_converter import PptConverter
from file_toolbox.core.batch_pdf.converters.word_converter import WordConverter


def _word_converter() -> WordConverter:
    return WordConverter.__new__(WordConverter)


def _excel_converter() -> ExcelConverter:
    return ExcelConverter.__new__(ExcelConverter)


def _ppt_converter() -> PptConverter:
    return PptConverter.__new__(PptConverter)


# ---------------------------------------------------------------------------
# 假 COM 对象构造器(仅暴露 _detect_orientation 实际读取的属性)
# ---------------------------------------------------------------------------


class _FakeWordSections:
    """模拟 Word doc.Sections:既有 .Count 又可调用 Sections(1)。"""

    def __init__(self, count: int, page_width: float, page_height: float):
        self.Count = count
        self._section = SimpleNamespace(
            PageSetup=SimpleNamespace(PageWidth=page_width, PageHeight=page_height)
        )

    def __call__(self, idx):  # COM 集合是可调用的:Sections(1)
        return self._section


def _make_word_doc(page_width: float, page_height: float, section_count: int = 1):
    return SimpleNamespace(Sections=_FakeWordSections(section_count, page_width, page_height))


class _FakeExcelSheets:
    """模拟 Excel wb.Worksheets:既有 .Count 又可调用 Worksheets(1)。"""

    def __init__(self, count: int, cols: int, rows: int):
        self.Count = count
        self._sheet = SimpleNamespace(
            UsedRange=SimpleNamespace(
                Columns=SimpleNamespace(Count=cols),
                Rows=SimpleNamespace(Count=rows),
            )
        )

    def __call__(self, idx):
        return self._sheet


def _make_excel_wb(cols: int, rows: int, sheet_count: int = 1):
    return SimpleNamespace(Worksheets=_FakeExcelSheets(sheet_count, cols, rows))


def _make_ppt(slide_width: float, slide_height: float, slide_count: int = 1):
    return SimpleNamespace(
        Slides=SimpleNamespace(Count=slide_count),
        PageSetup=SimpleNamespace(SlideWidth=slide_width, SlideHeight=slide_height),
    )


# ===========================================================================
# WordConverter: _get_paper_size_word / _get_orientation_word
# ===========================================================================


def test_word_get_paper_size_known():
    h = _word_converter()
    # 与 WORD_PAPER_MAP 常量逐项对照
    for name, expected in WORD_PAPER_MAP.items():
        assert h._get_paper_size_word(name) == expected, f"{name} mismatch"


def test_word_get_paper_size_a4():
    h = _word_converter()
    assert h._get_paper_size_word("A4") == 7  # wdPaperA4


def test_word_get_paper_size_a3():
    h = _word_converter()
    assert h._get_paper_size_word("A3") == 8  # wdPaperA3


def test_word_get_paper_size_unknown_defaults_to_a4():
    """未知纸张名 → 默认 A4 (7)。"""
    h = _word_converter()
    assert h._get_paper_size_word("bogus") == 7


def test_word_get_paper_size_empty_string_defaults_to_a4():
    h = _word_converter()
    assert h._get_paper_size_word("") == 7


def test_word_get_orientation_landscape():
    """landscape → 1 (wdOrientLandscape)。"""
    h = _word_converter()
    assert h._get_orientation_word(ORIENTATION_LANDSCAPE) == 1


def test_word_get_orientation_non_landscape_is_portrait():
    """任何非 landscape 字符串 → 0 (wdOrientPortrait)。"""
    h = _word_converter()
    assert h._get_orientation_word("portrait") == 0
    assert h._get_orientation_word("auto") == 0
    assert h._get_orientation_word("anything_else") == 0


# ===========================================================================
# WordConverter: _detect_orientation
# ===========================================================================


def test_word_detect_orientation_landscape():
    """宽 > 高 → landscape。"""
    h = _word_converter()
    assert h._detect_orientation(_make_word_doc(page_width=1000, page_height=500)) == (
        ORIENTATION_LANDSCAPE
    )


def test_word_detect_orientation_portrait():
    """宽 < 高 → portrait(默认)。"""
    h = _word_converter()
    assert h._detect_orientation(_make_word_doc(page_width=500, page_height=1000)) == "portrait"


def test_word_detect_orientation_equal_dimensions_portrait():
    """宽 == 高:不触发 landscape 分支 → portrait。"""
    h = _word_converter()
    assert h._detect_orientation(_make_word_doc(page_width=500, page_height=500)) == "portrait"


def test_word_detect_orientation_zero_sections_portrait():
    """Sections.Count == 0 → 跳过判断 → portrait。"""
    h = _word_converter()
    assert h._detect_orientation(_make_word_doc(1000, 500, section_count=0)) == "portrait"


def test_word_detect_orientation_attribute_error_swallowed():
    """读取属性抛异常时被 except 捕获,返回默认 portrait。"""
    h = _word_converter()

    class Boom:
        @property
        def Sections(self):  # noqa: N802 - 模拟 COM 属性名
            raise RuntimeError("COM exploded")

    assert h._detect_orientation(Boom()) == "portrait"


# ===========================================================================
# ExcelConverter: _detect_orientation
# ===========================================================================


def test_excel_detect_orientation_many_columns():
    """列数 > 6 → landscape(无论行列比例)。"""
    h = _excel_converter()
    assert h._detect_orientation(_make_excel_wb(cols=10, rows=2)) == ORIENTATION_LANDSCAPE


def test_excel_detect_orientation_seven_columns():
    """列数恰好 7(> 6 阈值)→ landscape。"""
    h = _excel_converter()
    assert h._detect_orientation(_make_excel_wb(cols=7, rows=2)) == ORIENTATION_LANDSCAPE


def test_excel_detect_orientation_ratio_wide():
    """列数 > 行数 * 1.5 → landscape(即便列数 <= 6)。"""
    h = _excel_converter()
    # 6 cols, 3 rows → 6 > 3*1.5=4.5 → landscape
    assert h._detect_orientation(_make_excel_wb(cols=6, rows=3)) == ORIENTATION_LANDSCAPE


def test_excel_detect_orientation_narrow_portrait():
    """列数少、行列比不满足横向条件 → portrait。"""
    h = _excel_converter()
    # 3 cols, 2 rows → 3 > 2*1.5=3? no. 3 > 6? no → portrait
    assert h._detect_orientation(_make_excel_wb(cols=3, rows=2)) == "portrait"


def test_excel_detect_orientation_six_columns_portrait():
    """列数恰好 6(不 > 6),且不满足比例 → portrait。"""
    h = _excel_converter()
    # 6 cols, 5 rows → 6 > 5*1.5=7.5? no. 6 > 6? no → portrait
    assert h._detect_orientation(_make_excel_wb(cols=6, rows=5)) == "portrait"


def test_excel_detect_orientation_zero_sheets_portrait():
    """Worksheets.Count == 0 → portrait。"""
    h = _excel_converter()
    assert (
        h._detect_orientation(_make_excel_wb(cols=10, rows=1, sheet_count=0)) == "portrait"
    )


def test_excel_detect_orientation_attribute_error_swallowed():
    """异常被吞 → portrait。"""
    h = _excel_converter()

    class Boom:
        @property
        def Worksheets(self):  # noqa: N802
            raise RuntimeError("COM exploded")

    assert h._detect_orientation(Boom()) == "portrait"


# ===========================================================================
# PptConverter: PAPER_SIZES_POINTS 常量 + _detect_orientation
# ===========================================================================


def test_ppt_paper_sizes_points_class_var_present():
    """PAPER_SIZES_POINTS 是 ClassVar dict,包含全部支持纸张。"""
    sizes = PptConverter.PAPER_SIZES_POINTS
    assert isinstance(sizes, dict)
    for name in ("A3", "A4", "A5", "Letter", "Legal"):
        assert name in sizes
        w, h = sizes[name]
        # 纵向纸张:宽 < 高
        assert w < h, f"{name} 应为纵向(宽<高)"


def test_ppt_paper_sizes_a4_value():
    """A4 = (595.28, 841.89) 磅(210x297mm 换算)。"""
    assert PptConverter.PAPER_SIZES_POINTS["A4"] == (595.28, 841.89)


def test_ppt_paper_sizes_letter_value():
    """Letter = 612 x 792 磅(8.5" x 11")。"""
    assert PptConverter.PAPER_SIZES_POINTS["Letter"] == (612, 792)


def test_ppt_detect_orientation_landscape():
    """SlideWidth > SlideHeight → landscape。"""
    h = _ppt_converter()
    assert h._detect_orientation(_make_ppt(slide_width=1000, slide_height=500)) == (
        ORIENTATION_LANDSCAPE
    )


def test_ppt_detect_orientation_portrait():
    """SlideWidth < SlideHeight → portrait。"""
    h = _ppt_converter()
    assert h._detect_orientation(_make_ppt(slide_width=500, slide_height=1000)) == "portrait"


def test_ppt_detect_orientation_equal_dimensions_portrait():
    """宽 == 高:不触发 landscape → portrait。"""
    h = _ppt_converter()
    assert h._detect_orientation(_make_ppt(slide_width=500, slide_height=500)) == "portrait"


def test_ppt_detect_orientation_zero_slides_portrait():
    """Slides.Count == 0 → portrait。"""
    h = _ppt_converter()
    assert h._detect_orientation(_make_ppt(1000, 500, slide_count=0)) == "portrait"


def test_ppt_detect_orientation_attribute_error_swallowed():
    """异常被吞 → portrait。"""
    h = _ppt_converter()

    class Boom:
        @property
        def Slides(self):  # noqa: N802
            raise RuntimeError("COM exploded")

    assert h._detect_orientation(Boom()) == "portrait"


# ===========================================================================
# 跨实现一致性:_detect_orientation 三者默认 portrait
# ===========================================================================


def test_all_converters_default_orientation_is_portrait():
    """三个 converter 在缺省/异常场景都返回 "portrait"(非 ORIENTATION_PORTRAIT 常量,
    而是源码中硬编码的字面值)。"""
    assert _word_converter()._detect_orientation(
        _make_word_doc(500, 1000)
    ) == "portrait"
    assert _excel_converter()._detect_orientation(_make_excel_wb(3, 2)) == "portrait"
    assert _ppt_converter()._detect_orientation(_make_ppt(500, 1000)) == "portrait"
