"""文件格式转换服务:doc→docx、xls→xlsx,通过 Windows COM 调用 Office。

每个转换在调用线程内独立初始化 COM 并创建一次性 Office 应用实例,
用完即关 —— 不复用 batch_pdf 的 EngineManager 缓存实例,因为后者为
共享/缓存设计,而 COM 应用绑定创建它的 STA 线程,跨线程复用会失效。
"""

import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from file_toolbox.common.office_session import ComSession, dispose_office_app, init_office_app


@dataclass(frozen=True)
class _LegacySpec:
    """旧格式→新格式转换的规格(差异点参数化,消除两份近乎复制的代码)。"""

    prog_id: str  # Office 应用 ProgID
    new_suffix: str  # 目标扩展名,如 ".docx"
    file_format: int  # SaveAs/SaveAs2 的 FileFormat 常量
    # open_doc(app, abs_path) -> document/workbook;app/doc 为 win32com 未类型化对象
    open_doc: Callable[[Any, str], Any]
    # save_doc(doc, abs_path, file_format) -> None
    save_doc: Callable[[Any, str, int], None]
    error_label: str  # 错误提示名


class FileConverterService:
    """文件格式转换服务"""

    def __init__(self) -> None:
        self.temp_files: list[Path] = []  # 记录临时文件

    def is_conversion_needed(self, file_path: Path) -> bool:
        """
        判断文件是否需要转换

        Args:
            file_path: 文件路径

        Returns:
            是否需要转换（.doc 和 .xls 需要转换）
        """
        suffix = file_path.suffix.lower()
        return suffix in [".doc", ".xls"]

    def _convert_legacy_format(
        self, src_path: Path, spec: _LegacySpec, output_path: Path | None = None
    ) -> tuple[bool, Path, str]:  # pragma: no cover
        """doc→docx / xls→xlsx 的通用实现,由两个公开方法复用。

        每次调用:本线程 CoInitialize → 新建一次性 Office 应用 → 转换 → 关闭 → CoUninitialize。
        """
        if sys.platform != "win32":
            return False, src_path, "此功能仅支持 Windows 系统"

        # 缺少 pywin32 时保留专用错误；不触碰目标文件。
        try:
            __import__("pythoncom")
        except ImportError:
            return False, src_path, "未安装 pywin32 库，请运行: pip install pywin32"

        app = None
        doc = None
        try:
            # 默认预览只拥有独立临时文件，不占用或删除原文件旁的同名文档。
            # 显式输出在同目录暂存，COM/文档收尾成功后再原子晋升。
            fd, name = tempfile.mkstemp(
                prefix="file-toolbox-convert-",
                suffix=spec.new_suffix,
                dir=output_path.parent if output_path is not None else None,
            )
            os.close(fd)
            staged = Path(name)
            self.temp_files.append(staged)
            session = ComSession()
            session.__enter__()
            try:
                app = init_office_app(spec.prog_id)
                doc = spec.open_doc(app, str(src_path.absolute()))
                spec.save_doc(doc, str(staged.absolute()), spec.file_format)
                doc.Close(False)
                doc = None
            finally:
                cleanup_errors: list[Exception] = []
                if doc is not None:
                    try:
                        doc.Close(False)
                    except Exception as cleanup_error:
                        cleanup_errors.append(cleanup_error)
                doc = None
                try:
                    dispose_office_app(app, spec.prog_id, raise_on_error=True)
                except Exception as cleanup_error:
                    cleanup_errors.append(cleanup_error)
                app = None
                session.__exit__(None, None, None)
                if cleanup_errors:
                    raise RuntimeError("Office 清理失败: " + "; ".join(map(str, cleanup_errors)))
            if not staged.is_file() or staged.stat().st_size == 0:
                raise RuntimeError("Office 未生成有效的转换文件")
            if output_path is not None:
                staged.replace(output_path)
                self.temp_files.remove(staged)
                return True, output_path, ""
            return True, staged, ""
        except Exception as error:
            return False, src_path, f"{spec.error_label}转换失败: {error}"

    def convert_doc_to_docx(
        self, doc_path: Path, output_path: Path | None = None
    ) -> tuple[bool, Path, str]:
        """
        将 .doc 转换为 .docx

        Args:
            doc_path: doc文件路径
            output_path: 输出路径（可选，默认返回由本服务清理的独立临时 .docx 文件）

        Returns:
            (是否成功, 转换后的文件路径, 错误消息)
        """
        spec = _LegacySpec(
            prog_id="Word.Application",
            new_suffix=".docx",
            file_format=16,  # docx
            open_doc=lambda app, p: app.Documents.Open(p),
            save_doc=lambda doc, p, fmt: doc.SaveAs2(p, FileFormat=fmt),
            error_label="doc→docx",
        )
        return self._convert_legacy_format(doc_path, spec, output_path)

    def convert_xls_to_xlsx(
        self, xls_path: Path, output_path: Path | None = None
    ) -> tuple[bool, Path, str]:
        """
        将 .xls 转换为 .xlsx

        Args:
            xls_path: xls文件路径
            output_path: 输出路径（可选，默认返回由本服务清理的独立临时 .xlsx 文件）

        Returns:
            (是否成功, 转换后的文件路径, 错误消息)
        """
        spec = _LegacySpec(
            prog_id="Excel.Application",
            new_suffix=".xlsx",
            file_format=51,  # xlsx
            open_doc=lambda app, p: app.Workbooks.Open(p),
            save_doc=lambda wb, p, fmt: wb.SaveAs(p, FileFormat=fmt),
            error_label="xls→xlsx",
        )
        return self._convert_legacy_format(xls_path, spec, output_path)

    def auto_convert_if_needed(self, file_path: Path) -> tuple[bool, Path, str]:
        """
        自动判断并转换文件（如果需要）

        Args:
            file_path: 文件路径

        Returns:
            (是否成功, 处理后的文件路径, 错误消息)
        """
        suffix = file_path.suffix.lower()

        if suffix == ".doc":
            return self.convert_doc_to_docx(file_path)
        elif suffix == ".xls":
            return self.convert_xls_to_xlsx(file_path)
        else:
            # 不需要转换
            return True, file_path, ""

    def cleanup_temp_files(self, *, strict: bool = False) -> None:
        """清理临时转换文件"""
        # 检查Python是否正在关闭
        import sys

        try:
            # 如果解释器正在关闭，跳过清理
            if not hasattr(sys, "modules") or not sys.modules.get("sys"):
                return
        except Exception:
            return

        errors: list[Exception] = []
        remaining: list[Path] = []
        for temp_file in self.temp_files:
            for attempt in range(2):
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                    break
                except PermissionError as error:
                    if attempt == 0:
                        continue
                    errors.append(error)
                    remaining.append(temp_file)
                except Exception as error:
                    errors.append(error)
                    remaining.append(temp_file)
                    break
        # 保留未清理项供显式 close 重试,不能丢失失败证据。
        self.temp_files[:] = remaining
        if strict and errors:
            raise ExceptionGroup("临时文件释放失败: " + "; ".join(map(str, errors)), errors)

    def close(self, *, strict: bool = False) -> None:
        """关闭服务;CLI 的严格关闭会报告未能清理的临时文件。"""
        self.cleanup_temp_files(strict=strict)

    def __del__(self) -> None:
        """析构函数"""
        # 不执行任何操作，避免在Python关闭时导致崩溃
        # 清理由close()方法显式调用
        pass
