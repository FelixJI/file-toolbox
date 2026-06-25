"""批量生成 PDF 核心逻辑:多格式转 PDF、合并、图片型、纸张/方向控制。"""

import contextlib
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from .constants import (
    ALL_SUPPORTED_EXTENSIONS,
    DPI_DEFAULT,
    DPI_OPTIONS,
    ENGINE_AUTO,
    ENGINE_MS_OFFICE,
    ENGINE_WPS,
    ORIENTATION_AUTO,
    ORIENTATION_AUTO_DETECT,
    ORIENTATION_LANDSCAPE,
    ORIENTATION_PORTRAIT,
    OUTPUT_MERGE,
    OUTPUT_SEPARATE,
    PAPER_SIZES,
    PDF_TYPE_EDITABLE,
    PDF_TYPE_IMAGE,
    PRINT_MODE_DUPLEX,
    PRINT_MODE_SINGLE,
    SCALE_DEFAULT,
    SUPPORTED_FORMATS,
)
from .converters.excel_converter import ExcelConverter
from .converters.image_converter import ImageConverter
from .converters.ppt_converter import PptConverter
from .converters.word_converter import WordConverter
from .engine_manager import EngineManager
from .pdf_utils import convert_pdf_to_image_pdf, get_file_info, merge_pdfs


class PDFGeneratorService:
    """PDF生成服务"""

    # 类属性，保持向后兼容
    SUPPORTED_FORMATS = SUPPORTED_FORMATS
    ALL_SUPPORTED_EXTENSIONS = ALL_SUPPORTED_EXTENSIONS
    PAPER_SIZES = PAPER_SIZES
    ORIENTATION_PORTRAIT = ORIENTATION_PORTRAIT
    ORIENTATION_LANDSCAPE = ORIENTATION_LANDSCAPE
    ORIENTATION_AUTO = ORIENTATION_AUTO
    ORIENTATION_AUTO_DETECT = ORIENTATION_AUTO_DETECT
    PDF_TYPE_IMAGE = PDF_TYPE_IMAGE
    PDF_TYPE_EDITABLE = PDF_TYPE_EDITABLE
    OUTPUT_SEPARATE = OUTPUT_SEPARATE
    OUTPUT_MERGE = OUTPUT_MERGE
    PRINT_MODE_SINGLE = PRINT_MODE_SINGLE
    PRINT_MODE_DUPLEX = PRINT_MODE_DUPLEX
    ENGINE_AUTO = ENGINE_AUTO
    ENGINE_MS_OFFICE = ENGINE_MS_OFFICE
    ENGINE_WPS = ENGINE_WPS
    DPI_OPTIONS = DPI_OPTIONS
    DPI_DEFAULT = DPI_DEFAULT

    def __init__(self):
        self._engine_manager = EngineManager()
        self._word_converter = WordConverter(self._engine_manager)
        self._excel_converter = ExcelConverter(self._engine_manager)
        self._ppt_converter = PptConverter(self._engine_manager)
        self._image_converter = ImageConverter()
        self.temp_files: list[Path] = []

    def get_file_type(self, file_path: Path) -> str | None:
        """
        获取文件类型

        Args:
            file_path: 文件路径

        Returns:
            文件类型 ('word', 'excel', 'powerpoint', 'image', 'pdf') 或 None
        """
        suffix = file_path.suffix.lower()
        for file_type, extensions in SUPPORTED_FORMATS.items():
            if suffix in extensions:
                return file_type
        return None

    def is_supported(self, file_path: Path) -> bool:
        """判断文件是否支持转换"""
        return self.get_file_type(file_path) is not None

    def get_output_filename(self, source_path: Path, output_dir: Path | None = None) -> Path:
        """
        获取输出文件名

        Args:
            source_path: 源文件路径
            output_dir: 输出目录（None则使用源文件目录）

        Returns:
            输出PDF路径
        """
        if output_dir is None:
            output_dir = source_path.parent

        output_path = output_dir / f"{source_path.stem}.pdf"

        # 如果文件已存在，添加序号
        if output_path.exists():
            counter = 1
            while True:
                output_path = output_dir / f"{source_path.stem}_{counter}.pdf"
                if not output_path.exists():
                    break
                counter += 1

        return output_path

    def get_engine_info(self, use_cache: bool = True) -> str:
        """获取当前引擎信息"""
        return self._engine_manager.get_engine_info(use_cache)

    def detect_engines_async(self, callback=None):
        """异步检测引擎（在后台线程调用）"""
        self._engine_manager.detect_engines_async(callback)

    def generate_pdf_from_word(
        self, file_path: Path, output_path: Path, config: dict
    ) -> tuple[bool, str]:
        """从Word文档生成PDF"""
        return self._word_converter.convert(file_path, output_path, config)

    def generate_pdf_from_excel(
        self, file_path: Path, output_path: Path, config: dict
    ) -> tuple[bool, str]:
        """从Excel文档生成PDF"""
        return self._excel_converter.convert(file_path, output_path, config)

    def generate_pdf_from_ppt(
        self, file_path: Path, output_path: Path, config: dict
    ) -> tuple[bool, str]:
        """从PowerPoint文档生成PDF"""
        return self._ppt_converter.convert(file_path, output_path, config)

    def generate_pdf_from_image(
        self, file_path: Path, output_path: Path, config: dict
    ) -> tuple[bool, str]:
        """从图片生成PDF"""
        return self._image_converter.convert(file_path, output_path, config)

    def _convert_pdf_to_image_pdf(
        self,
        input_pdf: Path,
        output_pdf: Path,
        dpi: int = DPI_DEFAULT,
        paper_size: str = "auto",
        orientation: str = "auto",
        scale_mode: str = SCALE_DEFAULT,
    ) -> tuple[bool, str]:
        """将可编辑PDF转换为图片型PDF"""
        return convert_pdf_to_image_pdf(
            input_pdf, output_pdf, dpi, paper_size, orientation, scale_mode
        )

    def generate_pdf(self, file_path: Path, output_path: Path, config: dict) -> tuple[bool, str]:
        """
        生成PDF（自动判断文件类型）

        Args:
            file_path: 源文件路径
            output_path: 输出PDF路径
            config: 配置字典

        Returns:
            (是否成功, 错误消息)
        """
        file_type = self.get_file_type(file_path)
        pdf_type = config.get("pdf_type", PDF_TYPE_EDITABLE)

        if file_type is None:
            return False, f"不支持的文件类型: {file_path.suffix}"

        if file_type == "pdf":
            # 如果已经是PDF
            if pdf_type == PDF_TYPE_IMAGE:
                # 需要转换为图片型
                dpi = config.get("dpi", DPI_DEFAULT)
                paper_size = config.get("paper_size", "auto")
                orientation = config.get("orientation", "auto")
                scale_mode = config.get("scale_mode", SCALE_DEFAULT)
                return self._convert_pdf_to_image_pdf(
                    file_path,
                    output_path,
                    dpi=dpi,
                    paper_size=paper_size,
                    orientation=orientation,
                    scale_mode=scale_mode,
                )
            else:
                # 直接复制
                try:
                    shutil.copy2(file_path, output_path)
                    return True, ""
                except Exception as e:
                    return False, f"复制PDF失败: {e!s}"

        # 对于其他文件类型，先生成可编辑PDF
        if pdf_type == PDF_TYPE_IMAGE:
            # 图片型：先生成临时可编辑PDF，再转换
            temp_pdf = output_path.parent / f"_temp_{output_path.name}"
            try:
                success, error = self._generate_editable_pdf(file_path, temp_pdf, config)
                if not success:
                    return False, error

                # 转换为图片型
                dpi = config.get("dpi", DPI_DEFAULT)
                paper_size = config.get("paper_size", "auto")
                orientation = config.get("orientation", "auto")
                scale_mode = config.get("scale_mode", SCALE_DEFAULT)
                success, error = self._convert_pdf_to_image_pdf(
                    temp_pdf,
                    output_path,
                    dpi=dpi,
                    paper_size=paper_size,
                    orientation=orientation,
                    scale_mode=scale_mode,
                )

                # 清理临时文件
                with contextlib.suppress(Exception):
                    temp_pdf.unlink()

                return success, error
            except Exception as e:
                # 清理临时文件
                with contextlib.suppress(Exception):
                    temp_pdf.unlink()
                return False, f"生成图片型PDF失败: {e!s}"
        else:
            # 可编辑型：直接生成
            return self._generate_editable_pdf(file_path, output_path, config)

    def _generate_editable_pdf(
        self, file_path: Path, output_path: Path, config: dict
    ) -> tuple[bool, str]:
        """生成可编辑型PDF（内部方法）"""
        file_type = self.get_file_type(file_path)

        if file_type == "word":
            return self.generate_pdf_from_word(file_path, output_path, config)
        elif file_type == "excel":
            return self.generate_pdf_from_excel(file_path, output_path, config)
        elif file_type == "powerpoint":
            return self.generate_pdf_from_ppt(file_path, output_path, config)
        elif file_type == "image":
            return self.generate_pdf_from_image(file_path, output_path, config)
        else:
            return False, f"未知的文件类型: {file_type}"

    def merge_pdfs(
        self, pdf_files: list[Path], output_path: Path, print_mode: str = "single"
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
        return merge_pdfs(pdf_files, output_path, print_mode)

    def batch_generate(
        self,
        files: list[Path],
        config: dict,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[dict]:
        """
        批量生成PDF

        Args:
            files: 文件列表
            config: 配置字典
            progress_callback: 进度回调函数 (current, total, message)

        Returns:
            结果列表 [{'source': Path, 'output': Path, 'success': bool, 'error': str}, ...]
        """
        results = []
        total = len(files)
        output_mode = config.get("output_mode", OUTPUT_SEPARATE)
        output_dir = config.get("output_dir")
        same_as_source = config.get("same_as_source", True)

        temp_pdfs = []  # 用于合并模式

        for idx, file_path in enumerate(files):
            if progress_callback:
                progress_callback(idx, total, f"正在处理: {file_path.name}")

            # 确定输出目录
            out_dir = file_path.parent if same_as_source else output_dir

            # 确定输出文件名
            if output_mode == OUTPUT_MERGE:
                # 合并模式：先输出到临时目录
                temp_dir = Path(tempfile.gettempdir()) / "pdf_generator"
                temp_dir.mkdir(exist_ok=True)
                output_path = temp_dir / f"{file_path.stem}_{idx}.pdf"
            else:
                output_path = self.get_output_filename(file_path, out_dir)

            # 生成PDF
            success, error = self.generate_pdf(file_path, output_path, config)

            result = {
                "source": file_path,
                "output": output_path,
                "success": success,
                "error": error,
            }
            results.append(result)

            if success and output_mode == OUTPUT_MERGE:
                temp_pdfs.append(output_path)

        # 合并模式：合并所有PDF
        if output_mode == OUTPUT_MERGE and temp_pdfs:
            if progress_callback:
                progress_callback(total, total, "正在合并PDF...")

            merge_filename = config.get("merge_filename", "合并文档.pdf")
            if same_as_source and files:
                merge_output = files[0].parent / merge_filename
            else:
                merge_output = output_dir / merge_filename

            # 确保输出路径不存在
            if merge_output.exists():
                counter = 1
                stem = merge_output.stem
                while merge_output.exists():
                    merge_output = merge_output.parent / f"{stem}_{counter}.pdf"
                    counter += 1

            success, error = self.merge_pdfs(
                temp_pdfs, merge_output, config.get("print_mode", PRINT_MODE_SINGLE)
            )

            # 清理临时文件
            for temp_pdf in temp_pdfs:
                with contextlib.suppress(Exception):
                    temp_pdf.unlink()

            if success:
                # 更新结果
                for result in results:
                    if result["success"]:
                        result["output"] = merge_output
            else:
                # 合并失败
                results.append(
                    {
                        "source": Path("合并操作"),
                        "output": merge_output,
                        "success": False,
                        "error": error,
                    }
                )

        if progress_callback:
            progress_callback(total, total, "完成")

        return results

    def get_file_info(self, file_path: Path) -> dict:
        """
        获取文件信息

        Args:
            file_path: 文件路径

        Returns:
            文件信息字典
        """
        return get_file_info(file_path, SUPPORTED_FORMATS)

    def close(self):
        """关闭Office应用"""
        with contextlib.suppress(Exception):
            self._engine_manager.close()

    def __del__(self):
        """析构函数"""
        with contextlib.suppress(Exception):
            self.close()
