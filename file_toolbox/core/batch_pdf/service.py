"""批量生成 PDF 核心逻辑:多格式转 PDF、合并、图片型、纸张/方向控制。"""

import contextlib
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.common.operation_errors import preserve_history_result

from .constants import (
    DPI_DEFAULT,
    OUTPUT_MERGE,
    OUTPUT_SEPARATE,
    PDF_TYPE_EDITABLE,
    PDF_TYPE_IMAGE,
    PRINT_MODE_SINGLE,
    SCALE_DEFAULT,
    SUPPORTED_FORMATS,
)
from .converters.excel_converter import ExcelConverter
from .converters.image_converter import ImageConverter
from .converters.ppt_converter import PptConverter
from .converters.word_converter import WordConverter
from .engine_manager import EngineManager

# 注意:pdf_utils(顶层导入 pypdfium2/pypdf,连带 PIL)不在模块顶层导入——构造
# 服务/打开生成 PDF 页只需轻量对象组装,该链冷导入合计可达数百 ms;合并、
# 图片型转换、文件信息等能力在首次调用时按需导入(Issue #124 首切响应预算)。


class PDFGeneratorService:
    """PDF生成服务"""

    def __init__(self, history_store: JsonHistoryStore | None = None) -> None:
        self._history_store = history_store
        self._engine_manager = EngineManager()
        self._word_converter = WordConverter(self._engine_manager)
        self._excel_converter = ExcelConverter(self._engine_manager)
        self._ppt_converter = PptConverter(self._engine_manager)
        self._image_converter = ImageConverter()
        self.temp_files: list[Path] = []
        self._cleanup_errors: list[Exception] = []

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

    def detect_engines_async(self, callback: Callable[[str], None] | None = None) -> None:
        """异步检测引擎（在后台线程调用）"""
        self._engine_manager.detect_engines_async(callback)

    def generate_pdf_from_word(
        self, file_path: Path, output_path: Path, config: dict[str, Any]
    ) -> tuple[bool, str]:  # pragma: no cover
        """从Word文档生成PDF"""
        return self._word_converter.convert(file_path, output_path, config)

    def generate_pdf_from_excel(
        self, file_path: Path, output_path: Path, config: dict[str, Any]
    ) -> tuple[bool, str]:  # pragma: no cover
        """从Excel文档生成PDF"""
        return self._excel_converter.convert(file_path, output_path, config)

    def generate_pdf_from_ppt(
        self, file_path: Path, output_path: Path, config: dict[str, Any]
    ) -> tuple[bool, str]:  # pragma: no cover
        """从PowerPoint文档生成PDF"""
        return self._ppt_converter.convert(file_path, output_path, config)

    def generate_pdf_from_image(
        self, file_path: Path, output_path: Path, config: dict[str, Any]
    ) -> tuple[bool, str]:  # pragma: no cover
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
        from .pdf_utils import convert_pdf_to_image_pdf  # 按需导入(见模块顶部说明)

        return convert_pdf_to_image_pdf(
            input_pdf, output_pdf, dpi, paper_size, orientation, scale_mode
        )

    def generate_pdf(
        self, file_path: Path, output_path: Path, config: dict[str, Any]
    ) -> tuple[bool, str]:
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
            temp_pdf = self._new_temp_pdf(output_path.name)
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

                return success, error
            except Exception as e:
                return False, f"生成图片型PDF失败: {e!s}"
            finally:
                self._cleanup_temp_pdf(temp_pdf)
        else:
            # 可编辑型：直接生成
            return self._generate_editable_pdf(file_path, output_path, config)

    def _generate_editable_pdf(
        self, file_path: Path, output_path: Path, config: dict[str, Any]
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
        from .pdf_utils import merge_pdfs  # 按需导入(见模块顶部说明)

        return merge_pdfs(pdf_files, output_path, print_mode)

    def batch_generate(
        self,
        files: list[Path],
        config: dict[str, Any],
        progress_callback: Callable[[int, int, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """
        批量生成PDF

        Args:
            files: 文件列表
            config: 配置字典
            progress_callback: 进度回调函数 (current, total, message)
            cancel_check: 取消检查回调(返回 True 则中断循环,已生成的结果照常返回)。
                默认 None,行为与旧版完全一致(其它调用方零影响)。

        Returns:
            结果列表 [{'source': Path, 'output': Path, 'success': bool, 'error': str}, ...]
        """
        results: list[dict[str, Any]] = []
        total = len(files)
        output_mode = config.get("output_mode", OUTPUT_SEPARATE)
        output_dir = config.get("output_dir")
        same_as_source = config.get("same_as_source", True)

        temp_pdfs = []  # 用于合并模式

        for idx, file_path in enumerate(files):
            # 取消检查:在处理下一个文件前判断(已完成的文件照常计入 results)
            if cancel_check and cancel_check():
                break

            if progress_callback:
                progress_callback(idx, total, f"正在处理: {file_path.name}")

            # 确定输出目录
            out_dir = file_path.parent if same_as_source else output_dir

            # 确定输出文件名
            if output_mode == OUTPUT_MERGE:
                # 合并模式：先输出到临时目录
                output_path = self._new_temp_pdf(f"{file_path.stem}_{idx}.pdf")
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

            # 每个输入的成功状态表示最终产物,不能指向即将删除的中间文件。
            for result in results:
                if result["success"]:
                    result["output"] = merge_output
                    result["success"] = success
                    result["error"] = error

        for temp_pdf in list(self.temp_files):
            self._cleanup_temp_pdf(temp_pdf)

        if progress_callback:
            progress_callback(total, total, "完成")

        # 记录历史(执行后):从 results 汇总 ok/fail(逻辑同 PDFController.summarize_results),
        # config 取审计子集。形状与原 GUI pdf_tab 内联写入 / PDFController.build_history_record
        # 完全一致。此处可能在工作线程(PdfGenerateWorker)内执行,add_record 由
        # JsonHistoryStore 的文件事务锁(线程 + 跨进程)保护。
        if self._history_store is not None:
            ok = sum(1 for r in results if r.get("success"))
            fail = len(results) - ok
            with preserve_history_result(results):
                self._history_store.add_record(
                    "pdf",
                    {
                        "files": [str(f) for f in files],
                        "success": ok,
                        "failed": fail,
                        "config": {
                            "pdf_type": config.get("pdf_type"),
                            "output_mode": config.get("output_mode"),
                            "engine": config.get("engine"),
                            "dpi": config.get("dpi"),
                        },
                    },
                )
        return results

    def get_file_info(self, file_path: Path) -> dict[str, Any]:
        """
        获取文件信息

        Args:
            file_path: 文件路径

        Returns:
            文件信息字典
        """
        from .pdf_utils import get_file_info  # 按需导入(见模块顶部说明)

        return get_file_info(file_path, SUPPORTED_FORMATS)

    def _new_temp_pdf(self, name: str) -> Path:
        # 每个中间文件拥有独立目录,不覆盖或清理其他调用的临时文件。
        path = Path(tempfile.mkdtemp(prefix="file-toolbox-pdf-")) / name
        self.temp_files.append(path)
        return path

    def _cleanup_temp_pdf(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
            path.parent.rmdir()
        except Exception as error:
            self._cleanup_errors.append(error)
        else:
            self.temp_files.remove(path)

    def close(self, _from_del: bool = False, *, strict: bool = False) -> None:
        """释放本次临时文件和 Office;析构时不触发文件清理或嵌套 GC。"""
        if _from_del:
            with contextlib.suppress(Exception):
                self._engine_manager.close(_from_del=True)
            return
        for path in list(self.temp_files):
            self._cleanup_temp_pdf(path)
        errors, self._cleanup_errors = self._cleanup_errors, []
        try:
            if strict:
                self._engine_manager.close(strict=True)
            else:
                self._engine_manager.close()
        except Exception as error:
            errors.append(error)
        if strict and errors:
            raise ExceptionGroup("PDF 资源释放失败: " + "; ".join(map(str, errors)), errors)

    def __del__(self) -> None:  # pragma: no cover
        """析构函数"""
        with contextlib.suppress(Exception):
            self.close(_from_del=True)
