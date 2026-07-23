"""
PDF工具函数

包含PDF合并、PDF转图片型PDF等功能
"""

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
        # 尝试多种导入方式（兼容不同PyMuPDF版本）
        fitz = None
        with contextlib.suppress(ImportError):
            import fitz  # type: ignore[no-redef]

        if fitz is None:  # pragma: no cover - fitz 在依赖中已安装,此分支在测试环境不可达
            with contextlib.suppress(ImportError):
                import pymupdf as fitz  # type: ignore[assignment]

        if fitz is None:  # pragma: no cover - 同上,fitz 已安装
            return (
                False,
                "未安装 PyMuPDF 库，请运行: pip install PyMuPDF",
            )

        import io

        from PIL import Image

        # 打开PDF
        pdf_doc = fitz.open(str(input_pdf))
        images = []

        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            # 渲染为图片
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)

            # 转换为PIL Image
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))

            # 转换为RGB模式
            if img.mode != "RGB":
                img = img.convert("RGB")

            # 如果指定了纸张尺寸，将图片适应到纸张上
            if paper_size != "auto" and paper_size in PAPER_SIZES:
                img = _fit_image_to_paper(img, paper_size, orientation, dpi, scale_mode)

            images.append(img)

        pdf_doc.close()

        if not images:
            return False, "PDF无内容"

        # 保存为图片型PDF
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

        return True, ""

    except ImportError as e:  # pragma: no cover - 依赖已安装,ImportError 在测试环境不可达
        return False, f"缺少依赖库: {e!s}，请确保已安装 PyMuPDF 和 Pillow"
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
        # 尝试多种导入方式（兼容不同PyMuPDF版本）
        fitz = None
        with contextlib.suppress(ImportError):
            import fitz  # type: ignore[no-redef]

        if fitz is None:  # pragma: no cover - fitz 在依赖中已安装,此分支在测试环境不可达
            with contextlib.suppress(ImportError):
                import pymupdf as fitz  # type: ignore[assignment]

        if fitz is None:  # pragma: no cover - 同上,fitz 已安装
            return (
                False,
                "未安装 PyMuPDF 库，请运行: pip install PyMuPDF",
            )

        # 创建新文档用于合并
        merged_doc = fitz.open()

        for pdf_file in pdf_files:
            if pdf_file.exists():
                src_doc = fitz.open(str(pdf_file))

                # 双面打印模式下,为奇数页文档添加空白页
                if print_mode == PRINT_MODE_DUPLEX:
                    page_count = len(src_doc)

                    # 如果页数是奇数,需要添加空白页
                    if page_count % 2 == 1:
                        # 获取最后一页的尺寸
                        last_page = src_doc[-1]
                        rect = last_page.rect

                        # 添加所有原始页面到合并文档
                        merged_doc.insert_pdf(src_doc)

                        # 添加空白页
                        merged_doc.new_page(width=rect.width, height=rect.height)
                    else:
                        # 页数为偶数,直接合并
                        merged_doc.insert_pdf(src_doc)
                else:
                    # 单面打印模式,直接合并
                    merged_doc.insert_pdf(src_doc)

                src_doc.close()

        merged_doc.save(str(output_path))
        merged_doc.close()

        return True, ""

    except ImportError:  # pragma: no cover - 依赖已安装,ImportError 在测试环境不可达
        return False, "未安装 PyMuPDF 库，请运行: pip install PyMuPDF"
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
