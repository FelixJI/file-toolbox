"""
Word转PDF转换器

将Word文档(.doc, .docx)转换为PDF
"""

from pathlib import Path

from ..constants import (
    ORIENTATION_AUTO_DETECT,
    ORIENTATION_LANDSCAPE,
    WORD_PAPER_MAP,
)
from ..engine_manager import EngineManager


class WordConverter:
    """Word转PDF转换器"""

    def __init__(self, engine_manager: EngineManager):
        self._engine_manager = engine_manager

    def _get_paper_size_word(self, paper_size: str) -> int:
        """获取Word纸张尺寸常量"""
        return WORD_PAPER_MAP.get(paper_size, 7)  # 默认A4

    def _get_orientation_word(self, orientation: str) -> int:
        """获取Word纸张方向常量"""
        # wdOrientPortrait = 0, wdOrientLandscape = 1
        return 1 if orientation == ORIENTATION_LANDSCAPE else 0

    def _detect_orientation(self, doc) -> str:  # pragma: no cover
        """
        检测Word文档应该使用的方向
        根据页面宽高比例判断
        """
        try:
            if doc.Sections.Count > 0:
                page_setup = doc.Sections(1).PageSetup
                page_width = page_setup.PageWidth
                page_height = page_setup.PageHeight
                if page_width > page_height:
                    return ORIENTATION_LANDSCAPE
        except Exception:
            pass
        return "portrait"

    def convert(
        self, file_path: Path, output_path: Path, config: dict
    ) -> tuple[bool, str]:  # pragma: no cover
        """
        从Word文档生成PDF

        Args:
            file_path: Word文件路径
            output_path: 输出PDF路径
            config: 配置字典

        Returns:
            (是否成功, 错误消息)
        """
        try:
            engine = config.get("engine", "auto")
            word = self._engine_manager.init_word(engine)
            doc = word.Documents.Open(str(file_path.absolute()))

            paper_size = config.get("paper_size", "auto")
            orientation = config.get("orientation", "auto")

            # 自动检测方向
            if orientation == ORIENTATION_AUTO_DETECT:
                orientation = self._detect_orientation(doc)

            if paper_size != "auto":
                for section in doc.Sections:
                    section.PageSetup.PaperSize = self._get_paper_size_word(paper_size)

            if orientation != "auto":
                for section in doc.Sections:
                    section.PageSetup.Orientation = self._get_orientation_word(orientation)

            # 导出为PDF
            # wdExportFormatPDF = 17
            # wdExportOptimizeForPrint = 0 (高质量打印)
            doc.ExportAsFixedFormat(
                OutputFileName=str(output_path.absolute()),
                ExportFormat=17,  # wdExportFormatPDF
                OpenAfterExport=False,
                OptimizeFor=0,  # wdExportOptimizeForPrint
                Range=0,  # wdExportAllDocument
                From=1,
                To=1,
                Item=0,  # wdExportDocumentContent
                IncludeDocProps=True,
                KeepIRM=True,
                CreateBookmarks=0,  # wdExportCreateNoBookmarks
                DocStructureTags=True,
                BitmapMissingFonts=True,
                UseISO19005_1=False,
            )

            doc.Close(False)
            return True, ""

        except Exception as e:
            return False, f"Word转PDF失败: {e!s}"
