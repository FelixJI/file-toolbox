"""
Excel转PDF转换器

将Excel文档(.xls, .xlsx)转换为PDF
自动过滤空工作表，避免生成空白页
"""

import contextlib
from pathlib import Path

from ..constants import (
    EXCEL_PAPER_MAP,
    ORIENTATION_AUTO_DETECT,
    ORIENTATION_LANDSCAPE,
)
from ..engine_manager import EngineManager


class ExcelConverter:
    """Excel转PDF转换器"""

    def __init__(self, engine_manager: EngineManager):
        self._engine_manager = engine_manager

    def _detect_orientation(self, wb) -> str:
        """
        检测Excel文档应该使用的方向
        根据内容宽度判断
        """
        try:
            if wb.Worksheets.Count > 0:
                sheet = wb.Worksheets(1)
                used_range = sheet.UsedRange
                # 如果列数远大于行数，使用横向
                if used_range.Columns.Count > used_range.Rows.Count * 1.5:
                    return ORIENTATION_LANDSCAPE
                # 如果列数超过6列，建议横向
                if used_range.Columns.Count > 6:
                    return ORIENTATION_LANDSCAPE
        except Exception:
            pass
        return "portrait"

    def convert(self, file_path: Path, output_path: Path, config: dict) -> tuple[bool, str]:
        """
        从Excel文档生成PDF

        Args:
            file_path: Excel文件路径
            output_path: 输出PDF路径
            config: 配置字典

        Returns:
            (是否成功, 错误消息)
        """
        try:
            engine = config.get("engine", "auto")
            excel = self._engine_manager.init_excel(engine)
            wb = excel.Workbooks.Open(str(file_path.absolute()))

            paper_size = config.get("paper_size", "auto")
            orientation = config.get("orientation", "auto")

            # 自动检测方向
            if orientation == ORIENTATION_AUTO_DETECT:
                orientation = self._detect_orientation(wb)

            # 检测并隐藏空表（避免在PDF中显示空白页）
            hidden_sheets = []  # 记录被隐藏的工作表信息 (sheet, original_visibility)

            for sheet in wb.Worksheets:
                try:
                    used_range = sheet.UsedRange
                    if used_range is None:
                        hidden_sheets.append((sheet, sheet.Visible))
                        sheet.Visible = False
                except Exception:
                    pass

            if paper_size != "auto":
                for sheet in wb.Worksheets:
                    if sheet.Visible:
                        sheet.PageSetup.PaperSize = EXCEL_PAPER_MAP.get(paper_size, 9)

            if orientation != "auto":
                # xlPortrait = 1, xlLandscape = 2
                orient_value = 2 if orientation == ORIENTATION_LANDSCAPE else 1
                for sheet in wb.Worksheets:
                    if sheet.Visible:
                        sheet.PageSetup.Orientation = orient_value

            # 导出为PDF (xlTypePDF = 0)
            wb.ExportAsFixedFormat(
                0,  # xlTypePDF
                str(output_path.absolute()),
            )

            # 恢复所有工作表的可见性（不修改原文件）
            for sheet, original_visibility in hidden_sheets:
                with contextlib.suppress(Exception):
                    sheet.Visible = original_visibility

            wb.Close(False)
            return True, ""

        except Exception as e:
            return False, f"Excel转PDF失败: {e!s}"
