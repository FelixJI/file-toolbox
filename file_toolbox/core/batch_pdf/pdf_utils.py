"""
PDF工具函数

包含PDF合并、PDF转图片型PDF等功能
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter

from file_toolbox.common.file_utils import format_file_size

from .constants import (
    DPI_DEFAULT,
    ORIENTATION_AUTO_DETECT,
    ORIENTATION_LANDSCAPE,
    PAPER_SIZES,
    PRINT_MODE_DUPLEX,
    SCALE_ACTUAL_SIZE,
    SCALE_DEFAULT,
    SCALE_FIT_MARGIN,
)

if TYPE_CHECKING:
    from PIL import Image


def convert_pdf_to_image_pdf(
    input_pdf: Path,
    output_pdf: Path,
    dpi: int = DPI_DEFAULT,
    paper_size: str = "auto",
    orientation: str = "auto",
    scale_mode: str = SCALE_DEFAULT,
) -> tuple[bool, str]:
    """
    将可编辑PDF转换为图片型PDF

    Args:
        input_pdf: 输入PDF路径
        output_pdf: 输出PDF路径
        dpi: 渲染DPI（越高越清晰，但文件越大）
        paper_size: 纸张尺寸 ("auto", "A3", "A4", "A5", "Letter", "Legal")
        orientation: 纸张方向 ("auto", "portrait", "landscape", "auto_detect")
        scale_mode: 缩放模式 ("fit_margin", "actual_size", "shrink_oversized")

    Returns:
        (是否成功, 错误消息)
    """
    try:
        from PIL import Image

        images: list[Image.Image] = []
        try:
            with pdfium.PdfDocument(str(input_pdf)) as pdf_doc:
                if len(pdf_doc) == 0:
                    return False, "PDF无内容"

                for page_num in range(len(pdf_doc)):
                    page = pdf_doc[page_num]
                    try:
                        bitmap = page.render(scale=dpi / 72)
                        try:
                            # pypdfium2 对常见格式返回共享 bitmap 内存的 PIL Image；
                            # 关闭 bitmap 前复制，避免后续保存读取已释放内存。
                            img = bitmap.to_pil().copy()
                        finally:
                            bitmap.close()
                    finally:
                        page.close()

                    if img.mode != "RGB":
                        rgb_img = img.convert("RGB")
                        img.close()
                        img = rgb_img

                    if paper_size != "auto" and paper_size in PAPER_SIZES:
                        fitted_img = _fit_image_to_paper(
                            img, paper_size, orientation, dpi, scale_mode
                        )
                        if fitted_img is not img:
                            img.close()
                        img = fitted_img

                    images.append(img)

            if len(images) == 1:
                images[0].save(str(output_pdf), "PDF", resolution=dpi)
            else:
                images[0].save(
                    str(output_pdf),
                    "PDF",
                    resolution=dpi,
                    save_all=True,
                    append_images=images[1:],
                )
        finally:
            for image in images:
                image.close()

        return True, ""

    except ImportError as e:  # pragma: no cover - 依赖已安装,ImportError 在测试环境不可达
        return False, f"缺少依赖库: {e!s}，请确保已安装 pypdfium2 和 Pillow"
    except Exception as e:
        return False, f"转换图片型PDF失败: {e!s}"


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


def _fit_image_to_paper(
    img: "Image.Image",
    paper_size: str,
    orientation: str,
    dpi: int,
    scale_mode: str = SCALE_DEFAULT,
) -> "Image.Image":
    """
    将图片适应到指定纸张尺寸

    Args:
        img: PIL Image对象
        paper_size: 纸张尺寸名称
        orientation: 纸张方向
        dpi: DPI值
        scale_mode: 缩放模式

    Returns:
        适应后的PIL Image对象
    """
    from PIL import Image

    paper_w_mm, paper_h_mm = PAPER_SIZES[paper_size]
    # 转换为像素
    paper_w_px = int(paper_w_mm * dpi / 25.4)
    paper_h_px = int(paper_h_mm * dpi / 25.4)

    # 根据方向调整纸张尺寸
    if orientation == ORIENTATION_LANDSCAPE:
        paper_w_px, paper_h_px = paper_h_px, paper_w_px
    elif orientation in ("auto", ORIENTATION_AUTO_DETECT) and img.width > img.height:
        # 根据图片比例决定方向
        paper_w_px, paper_h_px = paper_h_px, paper_w_px
    # orientation == "portrait" 时不交换，保持原始宽高

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
        img_resized = _resize_to_fit(img, int(paper_w_px * margin), int(paper_h_px * margin))
        canvas = Image.new("RGB", (paper_w_px, paper_h_px), (255, 255, 255))
        offset_x = (paper_w_px - img_resized.width) // 2
        offset_y = (paper_h_px - img_resized.height) // 2
        canvas.paste(img_resized, (offset_x, offset_y))
        return canvas

    else:  # SCALE_SHRINK_OVERSIZED
        # 缩小过大页面：超出时缩小，小于纸张时放大填满
        img_resized = _resize_to_fit(img, paper_w_px, paper_h_px)
        canvas = Image.new("RGB", (paper_w_px, paper_h_px), (255, 255, 255))
        offset_x = (paper_w_px - img_resized.width) // 2
        offset_y = (paper_h_px - img_resized.height) // 2
        canvas.paste(img_resized, (offset_x, offset_y))
        return canvas


def merge_pdfs(
    pdf_files: list[Path], output_path: Path, print_mode: str = "single"
) -> tuple[bool, str]:
    """
    合并多个PDF为一个

    Args:
        pdf_files: PDF文件列表
        output_path: 输出路径
        print_mode: 打印模式 ('single'单面, 'duplex'双面)

    Returns:
        (是否成功, 错误消息)
    """
    try:
        existing_files = [pdf_file for pdf_file in pdf_files if pdf_file.exists()]
        if not existing_files:
            return False, "合并PDF失败: 没有可合并的PDF文件"

        writer = PdfWriter()
        try:
            for pdf_file in existing_files:
                with pdf_file.open("rb") as stream:
                    reader = PdfReader(stream)
                    writer.append(reader)

                    if print_mode == PRINT_MODE_DUPLEX and len(reader.pages) % 2 == 1:
                        last_page = reader.pages[-1]
                        writer.add_blank_page(
                            width=float(last_page.mediabox.width),
                            height=float(last_page.mediabox.height),
                        )

            writer.write(output_path)
        finally:
            writer.close()

        return True, ""

    except ImportError:  # pragma: no cover - 依赖已安装,ImportError 在测试环境不可达
        return False, "未安装 pypdf 库，请运行: uv sync --frozen"
    except Exception as e:
        return False, f"合并PDF失败: {e!s}"


def get_file_info(file_path: Path, supported_formats: dict[str, list[str]]) -> dict[str, Any]:
    """
    获取文件信息

    Args:
        file_path: 文件路径
        supported_formats: 支持的格式字典

    Returns:
        文件信息字典
    """
    suffix = file_path.suffix.lower()
    file_type = None
    for ftype, extensions in supported_formats.items():
        if suffix in extensions:
            file_type = ftype
            break

    info = {
        "name": file_path.name,
        "suffix": suffix,
        "size": 0,
        "size_str": "未知",
        "type": file_type,
        "supported": file_type is not None,
    }

    try:
        if file_path.exists():
            size = file_path.stat().st_size
            info["size"] = size
            info["size_str"] = format_file_size(size)
    except Exception:
        pass

    return info
