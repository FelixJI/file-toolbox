"""
图片转PDF转换器

将图片文件(.jpg, .png, .bmp等)转换为PDF
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..constants import (
    DPI_DEFAULT,
    ORIENTATION_AUTO_DETECT,
    ORIENTATION_LANDSCAPE,
    PAPER_SIZES,
    SCALE_ACTUAL_SIZE,
    SCALE_DEFAULT,
    SCALE_FIT_MARGIN,
)

if TYPE_CHECKING:
    from PIL import Image


class ImageConverter:
    """图片转PDF转换器"""

    @staticmethod
    def _resize_to_fit(img: "Image.Image", max_w: int, max_h: int) -> "Image.Image":
        """
        等比缩放图片以适应目标尺寸，支持放大和缩小。
        与 thumbnail() 不同，当图片小于目标尺寸时会放大。
        """
        from PIL import Image

        img_w, img_h = img.size
        ratio = min(max_w / img_w, max_h / img_h)
        new_w = max(1, int(img_w * ratio))
        new_h = max(1, int(img_h * ratio))
        if new_w == img_w and new_h == img_h:
            return img
        return img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    def _detect_orientation(self, file_path: Path) -> str:
        """
        检测图片应该使用的方向
        根据图片宽高比判断
        """
        try:
            from PIL import Image

            with Image.open(file_path) as img:
                if img.width > img.height:
                    return ORIENTATION_LANDSCAPE
        except Exception:
            pass
        return "portrait"

    def _apply_scale(
        self, img: "Image.Image", paper_w_px: int, paper_h_px: int, scale_mode: str
    ) -> "Image.Image":
        """
        应用缩放逻辑

        Args:
            img: PIL Image对象
            paper_w_px: 纸张宽度（像素）
            paper_h_px: 纸张高度（像素）
            scale_mode: 缩放模式

        Returns:
            缩放后的PIL Image对象
        """
        from PIL import Image

        img_w, img_h = img.size

        if scale_mode == SCALE_ACTUAL_SIZE:
            # 实际大小：不缩放，直接居中放置在画布上（可能超出部分会被裁剪）
            canvas = Image.new("RGB", (paper_w_px, paper_h_px), (255, 255, 255))
            # 计算居中位置
            offset_x = max(0, (paper_w_px - img_w) // 2)
            offset_y = max(0, (paper_h_px - img_h) // 2)
            # 只粘贴画布范围内的部分
            paste_w = min(img_w, paper_w_px)
            paste_h = min(img_h, paper_h_px)
            canvas.paste(img.crop((0, 0, paste_w, paste_h)), (offset_x, offset_y))
            return canvas

        elif scale_mode == SCALE_FIT_MARGIN:
            # 适合打印边距：始终缩放到纸张内（留5%边距）
            margin = 0.95
            img_resized = self._resize_to_fit(
                img, int(paper_w_px * margin), int(paper_h_px * margin)
            )
            canvas = Image.new("RGB", (paper_w_px, paper_h_px), (255, 255, 255))
            offset_x = (paper_w_px - img_resized.width) // 2
            offset_y = (paper_h_px - img_resized.height) // 2
            canvas.paste(img_resized, (offset_x, offset_y))
            return canvas

        else:  # SCALE_SHRINK_OVERSIZED
            # 缩小过大页面：超出时缩小，小于纸张时放大填满
            img_resized = self._resize_to_fit(img, paper_w_px, paper_h_px)
            canvas = Image.new("RGB", (paper_w_px, paper_h_px), (255, 255, 255))
            offset_x = (paper_w_px - img_resized.width) // 2
            offset_y = (paper_h_px - img_resized.height) // 2
            canvas.paste(img_resized, (offset_x, offset_y))
            return canvas

    def convert(
        self, file_path: Path, output_path: Path, config: dict[str, Any]
    ) -> tuple[bool, str]:
        """
        从图片生成PDF

        Args:
            file_path: 图片文件路径
            output_path: 输出PDF路径
            config: 配置字典

        Returns:
            (是否成功, 错误消息)
        """
        try:
            from PIL import Image

            # 打开图片
            img: Image.Image = Image.open(file_path)

            # 转换为RGB（PDF不支持RGBA）
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # 获取纸张设置
            paper_size = config.get("paper_size", "auto")
            orientation = config.get("orientation", "auto")
            scale_mode = config.get("scale_mode", SCALE_DEFAULT)

            # 自动检测方向
            if orientation == ORIENTATION_AUTO_DETECT:
                orientation = self._detect_orientation(file_path)

            # 使用用户配置的 DPI 或默认值
            target_dpi = config.get("dpi", DPI_DEFAULT)

            # 如果指定纸张大小，创建固定大小的画布
            if paper_size != "auto" and paper_size in PAPER_SIZES:
                paper_w, paper_h = PAPER_SIZES[paper_size]
                # 转换为像素
                paper_w_px = int(paper_w * target_dpi / 25.4)
                paper_h_px = int(paper_h * target_dpi / 25.4)

                # 根据方向调整纸张尺寸
                if orientation == ORIENTATION_LANDSCAPE:
                    paper_w_px, paper_h_px = paper_h_px, paper_w_px
                elif orientation in ("auto", ORIENTATION_AUTO_DETECT) and img.width > img.height:
                    # 根据图片比例决定方向
                    paper_w_px, paper_h_px = paper_h_px, paper_w_px
                # orientation == "portrait" 时不交换，保持原始宽高

                # 应用缩放逻辑
                img = self._apply_scale(img, paper_w_px, paper_h_px, scale_mode)

            # 保存为PDF，使用目标DPI确保输出质量
            img.save(str(output_path), "PDF", resolution=float(target_dpi))

            return True, ""

        except ImportError:  # pragma: no cover - Pillow 在依赖中已安装,此分支在测试环境不可达
            return False, "未安装 Pillow 库，请运行: pip install Pillow"
        except Exception as e:
            return False, f"图片转PDF失败: {e!s}"
