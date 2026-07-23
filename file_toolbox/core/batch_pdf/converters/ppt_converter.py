"""
PowerPoint转PDF转换器

将PowerPoint文档(.ppt, .pptx)转换为PDF
"""

from pathlib import Path
from typing import ClassVar

from ..constants import (
    ORIENTATION_AUTO_DETECT,
    ORIENTATION_LANDSCAPE,
)
from ..engine_manager import EngineManager


class PptConverter:
    """PowerPoint转PDF转换器"""

    # 纸张尺寸（单位：磅，1英寸=72磅）
    # PPT使用磅作为单位，所以直接转换
    PAPER_SIZES_POINTS: ClassVar[dict[str, tuple[float, float]]] = {
        "A3": (841.89, 1190.55),  # 297mm x 420mm
        "A4": (595.28, 841.89),  # 210mm x 297mm
        "A5": (419.53, 595.28),  # 148mm x 210mm
        "Letter": (612, 792),  # 8.5" x 11"
        "Legal": (612, 1008),  # 8.5" x 14"
    }

    def __init__(self, engine_manager: EngineManager):
        self._engine_manager = engine_manager

    def _detect_orientation(self, presentation) -> str:  # pragma: no cover
        """
        检测PPT应该使用的方向
        根据幻灯片宽高比判断
        """
        try:
            if presentation.Slides.Count > 0:
                page_setup = presentation.PageSetup
                if page_setup.SlideWidth > page_setup.SlideHeight:
                    return ORIENTATION_LANDSCAPE
        except Exception:
            pass
        return "portrait"

    def convert(
        self, file_path: Path, output_path: Path, config: dict
    ) -> tuple[bool, str]:  # pragma: no cover
        """
        从PowerPoint文档生成PDF

        Args:
            file_path: PPT文件路径
            output_path: 输出PDF路径
            config: 配置字典

        Returns:
            (是否成功, 错误消息)
        """
        try:
            engine = config.get("engine", "auto")
            ppt = self._engine_manager.init_ppt(engine)
            # msoFalse = 0, msoTrue = -1
            presentation = ppt.Presentations.Open(
                str(file_path.absolute()),
                True,  # ReadOnly
                False,  # Untitled
                False,  # WithWindow
            )

            paper_size = config.get("paper_size", "auto")
            orientation = config.get("orientation", "auto")

            # 自动检测方向
            if orientation == ORIENTATION_AUTO_DETECT:
                orientation = self._detect_orientation(presentation)

            # 设置纸张大小和方向
            if paper_size != "auto" and paper_size in self.PAPER_SIZES_POINTS:
                paper_w, paper_h = self.PAPER_SIZES_POINTS[paper_size]

                # 根据方向调整
                if orientation == ORIENTATION_LANDSCAPE:
                    paper_w, paper_h = paper_h, paper_w
                elif (
                    orientation in ("auto", ORIENTATION_AUTO_DETECT)
                    and presentation.PageSetup.SlideWidth > presentation.PageSetup.SlideHeight
                ):
                    # 根据当前幻灯片比例决定方向
                    paper_w, paper_h = paper_h, paper_w
                # orientation == "portrait" 时不交换，保持原始宽高

                # 设置幻灯片大小
                presentation.PageSetup.SlideWidth = paper_w
                presentation.PageSetup.SlideHeight = paper_h

            # 导出为PDF (ppSaveAsPDF = 32)
            presentation.ExportAsFixedFormat(
                str(output_path.absolute()),
                32,  # ppSaveAsPDF
            )

            presentation.Close()
            return True, ""

        except Exception as e:
            return False, f"PPT转PDF失败: {e!s}"
