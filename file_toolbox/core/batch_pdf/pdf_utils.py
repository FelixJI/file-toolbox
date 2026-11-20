"""
PDF工具函数

包含PDF合并、PDF转图片型PDF、页面重排到指定纸张等功能
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import ArrayObject, FloatObject, NameObject, NumberObject, RectangleObject

from file_toolbox.common.file_utils import format_file_size

from .constants import (
    DPI_DEFAULT,
    ORIENTATION_AUTO_DETECT,
    ORIENTATION_LANDSCAPE,
    ORIENTATION_PORTRAIT,
    PAPER_SIZES,
    PRINT_MODE_DUPLEX,
    ROTATE_AUTO,
    ROTATE_DEFAULT,
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
    rotate: str = ROTATE_DEFAULT,
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
        rotate: 页面旋转 ("none" 不旋转, "auto" 自动旋转匹配纸张方向)

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
                            img, paper_size, orientation, dpi, scale_mode, rotate
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


def _rotate_image_to_match(img: "Image.Image", orientation: str, rotate: str) -> "Image.Image":
    """强制方向且开启自动旋转时,若图片长边方向与纸张相反则转 90° 对齐。

    方向为保持原样(auto)时纸张本就跟随图片长边,旋转无意义,原样返回。
    """
    from PIL import Image

    if rotate != ROTATE_AUTO or orientation not in (ORIENTATION_PORTRAIT, ORIENTATION_LANDSCAPE):
        return img
    img_landscape = img.width > img.height
    sheet_landscape = orientation == ORIENTATION_LANDSCAPE
    if img_landscape == sheet_landscape or img.width == img.height:
        return img
    return img.transpose(Image.Transpose.ROTATE_90)


def _fit_image_to_paper(
    img: "Image.Image",
    paper_size: str,
    orientation: str,
    dpi: int,
    scale_mode: str = SCALE_DEFAULT,
    rotate: str = ROTATE_DEFAULT,
) -> "Image.Image":
    """
    将图片适应到指定纸张尺寸

    Args:
        img: PIL Image对象
        paper_size: 纸张尺寸名称
        orientation: 纸张方向
        dpi: DPI值
        scale_mode: 缩放模式
        rotate: 页面旋转 ("none" 不旋转, "auto" 自动旋转匹配纸张方向)

    Returns:
        适应后的PIL Image对象
    """
    from PIL import Image

    img = _rotate_image_to_match(img, orientation, rotate)

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
    paper_size: str, orientation: str, vis_w: float, vis_h: float
) -> tuple[float, float]:
    """计算目标纸张尺寸(单位:点)。

    portrait/landscape 强制对应方向;orientation == "auto"(保持原样)时纸张
    长边对齐页面**视觉**长边(vis_w/vis_h 已含 /Rotate 影响),与图片路径的
    自动横竖语义一致。
    """
    paper_w_mm, paper_h_mm = PAPER_SIZES[paper_size]
    paper_w = paper_w_mm * 72 / 25.4
    paper_h = paper_h_mm * 72 / 25.4
    if orientation == ORIENTATION_LANDSCAPE:
        return paper_h, paper_w
    if orientation == ORIENTATION_PORTRAIT:
        return paper_w, paper_h
    return (paper_h, paper_w) if vis_w > vis_h else (paper_w, paper_h)


# 页面尺寸与目标纸张差值在该容差(点)内视为已达标,跳过重排保持内容流不变。
_PAPER_TOLERANCE_PT = 0.5


def _page_view_rotation(page: "PageObject") -> int:
    """读取页面 /Rotate 并归一到 0/90/180/270(顺时针显示旋转)。

    缺失、非法或非 90° 整数倍的值按 0 处理:非 90° 倍数无法用仿射网格表达,
    且此类值在真实文档中属病态输入。
    """
    try:
        rotate = int(page.get("/Rotate", 0)) % 360
    except (TypeError, ValueError):
        return 0
    return rotate if rotate % 90 == 0 else 0


def _transform_annotations(
    page: "PageObject",
    a: float,
    b: float,
    c: float,
    d: float,
    e: float,
    f: float,
) -> None:
    """对页面注释应用与内容流相同的仿射 CTM(x' = a*x + c*y + e; y' = b*x + d*y + f)。

    add_transformation 只包装内容流,不移动 /Annots 的 /Rect;若不同步变换,
    批注/链接/表单控件会停留在旧坐标系而错位。旋转 90°/270° 时轴对齐性保持
    (变换仅由均匀缩放与 90° 网格旋转复合),/Rect 变换对角后取 min/max 规整;
    /QuadPoints(文本标记等)为 x,y 交替序列,逐点变换。
    """
    annots = page.get("/Annots")
    if not annots:
        return

    def _apply(x: float, y: float) -> tuple[float, float]:
        return a * x + c * y + e, b * x + d * y + f

    for annot_ref in annots:
        annot = annot_ref.get_object()
        rect = annot.get("/Rect")
        if rect is not None:
            x0, y0, x1, y1 = (float(v) for v in rect)
            rx0, ry0 = _apply(x0, y0)
            rx1, ry1 = _apply(x1, y1)
            annot[NameObject("/Rect")] = ArrayObject(
                [
                    FloatObject(min(rx0, rx1)),
                    FloatObject(min(ry0, ry1)),
                    FloatObject(max(rx0, rx1)),
                    FloatObject(max(ry0, ry1)),
                ]
            )
        quad_points = annot.get("/QuadPoints")
        if quad_points is not None:
            points = [float(v) for v in quad_points]
            transformed: list[FloatObject] = []
            for i in range(0, len(points) - 1, 2):
                qx, qy = _apply(points[i], points[i + 1])
                transformed.extend((FloatObject(qx), FloatObject(qy)))
            annot[NameObject("/QuadPoints")] = ArrayObject(transformed)


def _repaper_page(
    page: "PageObject",
    paper_size: str,
    orientation: str,
    scale_mode: str,
    rotate: str = ROTATE_DEFAULT,
) -> None:
    """将已写入 writer 的页面原地重排到目标纸张。

    内容按总旋转角 T(顺时针)旋转、等比缩放并居中(缩放语义与图片型路径一致:
    fit_margin 留 5% 边距、actual_size 不缩放居中裁剪、shrink_oversized 缩放到
    正好放下),页面 MediaBox/CropBox/TrimBox 等设为目标尺寸,注释矩形随同一
    变换移动;内容保持矢量,不栅格化。

    T 由两部分复合:原页面 /Rotate 先烘焙进内容(输出页 /Rotate 归零,横竖判定
    一律以视觉宽高为准);rotate == "auto" 且方向为强制纵向/横向时,内容视觉
    长边与纸张长边相反则再加 90°(长宽匹配纸张)。未旋转且尺寸已达标时跳过,
    保持内容流不变。
    """
    src_x0 = float(page.mediabox.left)
    src_y0 = float(page.mediabox.bottom)
    src_w = float(page.mediabox.width)
    src_h = float(page.mediabox.height)
    view_rot = _page_view_rotation(page)
    vis_w, vis_h = (src_h, src_w) if view_rot in (90, 270) else (src_w, src_h)
    target_w, target_h = _paper_target_points(paper_size, orientation, vis_w, vis_h)

    extra_rot = 0
    if rotate == ROTATE_AUTO and orientation in (ORIENTATION_PORTRAIT, ORIENTATION_LANDSCAPE):
        sheet_landscape = target_w > target_h
        content_landscape = vis_w > vis_h
        if vis_w != vis_h and sheet_landscape != content_landscape:
            extra_rot = 90
    total_rot = (view_rot + extra_rot) % 360

    # 旋转后内容盒尺寸:0/180 度保持 (w,h),90/270 交换为 (h,w)。
    box_w, box_h = (src_h, src_w) if total_rot in (90, 270) else (src_w, src_h)
    if (
        total_rot == 0
        and abs(box_w - target_w) <= _PAPER_TOLERANCE_PT
        and abs(box_h - target_h) <= _PAPER_TOLERANCE_PT
    ):
        return

    if scale_mode == SCALE_FIT_MARGIN:
        limit_w, limit_h = target_w * 0.95, target_h * 0.95
    else:  # SCALE_ACTUAL_SIZE / SCALE_SHRINK_OVERSIZED
        limit_w, limit_h = target_w, target_h
    scale = 1.0 if scale_mode == SCALE_ACTUAL_SIZE else min(limit_w / box_w, limit_h / box_h)
    off_x = (target_w - box_w * scale) / 2
    off_y = (target_h - box_h * scale) / 2

    # 内容坐标 → 旋转盒坐标(顺时针 T 度,抵消 MediaBox 原点),再缩放居中到
    # 目标画布。PDF CTM: x' = a*x + c*y + e; y' = b*x + d*y + f。
    s = scale
    if total_rot == 90:
        # X = y - y0, Y = x0 + w - x
        a, b, c, d = 0.0, -s, s, 0.0
        e, f = off_x - s * src_y0, off_y + s * (src_x0 + src_w)
    elif total_rot == 180:
        # X = x0 + w - x, Y = y0 + h - y
        a, b, c, d = -s, 0.0, 0.0, -s
        e, f = off_x + s * (src_x0 + src_w), off_y + s * (src_y0 + src_h)
    elif total_rot == 270:
        # X = y0 + h - y, Y = x - x0
        a, b, c, d = 0.0, s, -s, 0.0
        e, f = off_x + s * (src_y0 + src_h), off_y - s * src_x0
    else:
        # X = x - x0, Y = y - y0
        a, b, c, d = s, 0.0, 0.0, s
        e, f = off_x - s * src_x0, off_y - s * src_y0

    page.add_transformation(Transformation((a, b, c, d, e, f)))
    _transform_annotations(page, a, b, c, d, e, f)
    page[NameObject("/Rotate")] = NumberObject(0)
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
    rotate: str = ROTATE_DEFAULT,
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
        rotate: 页面旋转 ("none"不旋转, "auto"方向强制时内容长边对齐纸张长边)

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
                            _repaper_page(
                                writer.pages[idx], paper_size, orientation, scale_mode, rotate
                            )

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
