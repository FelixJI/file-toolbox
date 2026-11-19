"""
PDF工具函数

包含PDF合并、PDF转图片型PDF、页面重排到指定纸张等功能
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import ArrayObject, FloatObject, NameObject, RectangleObject

from file_toolbox.common.file_utils import format_file_size

from .constants import (
    DPI_DEFAULT,
    ORIENTATION_AUTO_DETECT,
    ORIENTATION_LANDSCAPE,
    ORIENTATION_PORTRAIT,
    PAPER_SIZES,
    PRINT_MODE_DUPLEX,
    SCALE_ACTUAL_SIZE,
    SCALE_DEFAULT,
    SCALE_FIT_MARGIN,
)

if TYPE_CHECKING:
    from PIL import Image
    from pypdf import PageObject


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


def _paper_target_points(
    paper_size: str, orientation: str, src_w: float, src_h: float
) -> tuple[float, float]:
    """计算目标纸张尺寸(单位:点)。

    portrait/landscape 强制对应方向;orientation == "auto"(保持原样)时纸张
    长边对齐源页面长边(宽>高取横放),与图片路径的自动横竖语义一致。
    """
    paper_w_mm, paper_h_mm = PAPER_SIZES[paper_size]
    paper_w = paper_w_mm * 72 / 25.4
    paper_h = paper_h_mm * 72 / 25.4
    if orientation == ORIENTATION_LANDSCAPE:
        return paper_h, paper_w
    if orientation == ORIENTATION_PORTRAIT:
        return paper_w, paper_h
    return (paper_h, paper_w) if src_w > src_h else (paper_w, paper_h)


# 页面尺寸与目标纸张差值在该容差(点)内视为已达标,跳过重排保持内容流不变。
_PAPER_TOLERANCE_PT = 0.5


def _transform_annotations(
    page: "PageObject", scale: float, offset_x: float, offset_y: float
) -> None:
    """对页面注释应用与内容流相同的 CTM(x' = s*x + tx)。

    add_transformation 只包装内容流,不移动 /Annots 的 /Rect;若不同步变换,
    批注/链接/表单控件会停留在旧坐标系而错位。/QuadPoints(文本标记等)为
    x,y 交替序列,同样变换。
    """
    annots = page.get("/Annots")
    if not annots:
        return
    for annot_ref in annots:
        annot = annot_ref.get_object()
        rect = annot.get("/Rect")
        if rect is not None:
            x0, y0, x1, y1 = (float(v) for v in rect)
            annot[NameObject("/Rect")] = ArrayObject(
                [
                    FloatObject(x0 * scale + offset_x),
                    FloatObject(y0 * scale + offset_y),
                    FloatObject(x1 * scale + offset_x),
                    FloatObject(y1 * scale + offset_y),
                ]
            )
        quad_points = annot.get("/QuadPoints")
        if quad_points is not None:
            points = [float(v) for v in quad_points]
            annot[NameObject("/QuadPoints")] = ArrayObject(
                [
                    FloatObject(
                        x * scale + (offset_x if i % 2 == 0 else offset_y)
                    )  # 偶数位为 x,奇数位为 y
                    for i, x in enumerate(points)
                ]
            )


def _repaper_page(page: "PageObject", paper_size: str, orientation: str, scale_mode: str) -> None:
    """将已写入 writer 的页面原地重排到目标纸张。

    内容等比缩放并居中(缩放语义与图片型路径一致:fit_margin 留 5% 边距、
    actual_size 不缩放居中裁剪、shrink_oversized 缩放到正好放下),页面
    MediaBox/CropBox/TrimBox 等设为目标尺寸,注释矩形随同一变换移动;
    内容保持矢量,不栅格化。页面已达标时直接跳过。不处理 /Rotate 非零的
    页面方向差异(按 MediaBox 原始宽高对齐)。
    """
    src_w = float(page.mediabox.width)
    src_h = float(page.mediabox.height)
    target_w, target_h = _paper_target_points(paper_size, orientation, src_w, src_h)
    if (
        abs(src_w - target_w) <= _PAPER_TOLERANCE_PT
        and abs(src_h - target_h) <= _PAPER_TOLERANCE_PT
    ):
        return

    if scale_mode == SCALE_FIT_MARGIN:
        limit_w, limit_h = target_w * 0.95, target_h * 0.95
    else:  # SCALE_ACTUAL_SIZE / SCALE_SHRINK_OVERSIZED
        limit_w, limit_h = target_w, target_h
    scale = 1.0 if scale_mode == SCALE_ACTUAL_SIZE else min(limit_w / src_w, limit_h / src_h)

    # MediaBox 原点可能非 (0,0):先抵消原点再缩放,最后居中到目标画布。
    x0 = float(page.mediabox.left)
    y0 = float(page.mediabox.bottom)
    offset_x = (target_w - src_w * scale) / 2 - x0 * scale
    offset_y = (target_h - src_h * scale) / 2 - y0 * scale
    page.add_transformation(Transformation().scale(scale, scale).translate(offset_x, offset_y))
    _transform_annotations(page, scale, offset_x, offset_y)
    page.mediabox = RectangleObject([0.0, 0.0, target_w, target_h])
    page.cropbox = RectangleObject([0.0, 0.0, target_w, target_h])
    page.trimbox = RectangleObject([0.0, 0.0, target_w, target_h])
    page.bleedbox = RectangleObject([0.0, 0.0, target_w, target_h])
    page.artbox = RectangleObject([0.0, 0.0, target_w, target_h])


def merge_pdfs(
    pdf_files: list[Path],
    output_path: Path,
    print_mode: str = "single",
    paper_size: str = "auto",
    orientation: str = "auto",
    scale_mode: str = SCALE_DEFAULT,
) -> tuple[bool, str]:
    """
    合并多个PDF为一个

    Args:
        pdf_files: PDF文件列表
        output_path: 输出路径
        print_mode: 打印模式 ('single'单面, 'duplex'双面)
        paper_size: 纸张尺寸 ("auto"保持原样, 或 "A3"/"A4"/"A5"/"Letter"/"Legal");
            选定后所有页面统一重排到该纸张(含可编辑型内容,保持矢量)
        orientation: 纸张方向 ("auto"保持原样按每页长边对齐, "portrait", "landscape")
        scale_mode: 重排缩放模式(与图片型路径一致, 默认缩小过大页面)

    Returns:
        (是否成功, 错误消息)
    """
    try:
        existing_files = [pdf_file for pdf_file in pdf_files if pdf_file.exists()]
        if not existing_files:
            return False, "合并PDF失败: 没有可合并的PDF文件"

        repaper = paper_size in PAPER_SIZES
        writer = PdfWriter()
        try:
            for pdf_file in existing_files:
                with pdf_file.open("rb") as stream:
                    reader = PdfReader(stream)
                    start = len(writer.pages)
                    writer.append(reader)

                    if repaper:
                        for idx in range(start, len(writer.pages)):
                            _repaper_page(writer.pages[idx], paper_size, orientation, scale_mode)

                    if print_mode == PRINT_MODE_DUPLEX and len(reader.pages) % 2 == 1:
                        # 补白页与前一页重排后的最终尺寸一致
                        last_page = writer.pages[len(writer.pages) - 1]
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
