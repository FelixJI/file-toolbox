"""文件格式转换服务:doc→docx、xls→xlsx,通过 Windows COM 调用 Office。

每个转换在调用线程内独立初始化 COM 并创建一次性 Office 应用实例,
用完即关 —— 不复用 batch_pdf 的 EngineManager 缓存实例,因为后者为
共享/缓存设计,而 COM 应用绑定创建它的 STA 线程,跨线程复用会失效。
"""

import contextlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class _LegacySpec:
    """旧格式→新格式转换的规格(差异点参数化,消除两份近乎复制的代码)。"""

    prog_id: str                       # Office 应用 ProgID
    new_suffix: str                    # 目标扩展名,如 ".docx"
    file_format: int                   # SaveAs/SaveAs2 的 FileFormat 常量
    open_doc: Callable                 # open_doc(app, abs_path) -> document/workbook
    save_doc: Callable                 # save_doc(doc, abs_path, file_format) -> None
    error_label: str                   # 错误提示名


class FileConverterService:
    """文件格式转换服务"""

    def __init__(self):
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
    ) -> tuple[bool, Path, str]:
        """doc→docx / xls→xlsx 的通用实现,由两个公开方法复用。

        每次调用:本线程 CoInitialize → 新建一次性 Office 应用 → 转换 → 关闭 → CoUninitialize。
        """
        if sys.platform != "win32":
            return False, src_path, "此功能仅支持 Windows 系统"

        try:
            import pythoncom
            import win32com.client
        except ImportError:
            return False, src_path, "未安装 pywin32 库，请运行: pip install pywin32"

        app = None
        try:
            pythoncom.CoInitialize()
            try:
                # 生成输出路径
                if output_path is None:
                    output_path = src_path.with_suffix(spec.new_suffix)
                    # 目标已存在:先尝试删除,被锁定则用时间戳建新文件
                    if output_path.exists():
                        try:
                            output_path.unlink()
                        except PermissionError:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            output_path = src_path.with_name(
                                f"{src_path.stem}_{timestamp}{spec.new_suffix}"
                            )

                # 每次创建新的应用实例,避免 COM 对象失效问题
                app = win32com.client.Dispatch(spec.prog_id)
                app.Visible = False
                app.DisplayAlerts = False

                doc = spec.open_doc(app, str(src_path.absolute()))
                spec.save_doc(doc, str(output_path.absolute()), spec.file_format)
                doc.Close()

                self.temp_files.append(output_path)
                return True, output_path, ""
            finally:
                if app is not None:
                    with contextlib.suppress(Exception):
                        app.Quit()
                pythoncom.CoUninitialize()
        except Exception as e:
            return False, src_path, f"{spec.error_label}转换失败: {e!s}"

    def convert_doc_to_docx(
        self, doc_path: Path, output_path: Path | None = None
    ) -> tuple[bool, Path, str]:
        """
        将 .doc 转换为 .docx

        Args:
            doc_path: doc文件路径
            output_path: 输出路径（可选，默认为同目录下的 .docx 文件）

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
            output_path: 输出路径（可选，默认为同目录下的 .xlsx 文件）

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

    def cleanup_temp_files(self):
        """清理临时转换文件"""
        # 检查Python是否正在关闭
        import sys

        try:
            # 如果解释器正在关闭，跳过清理
            if not hasattr(sys, "modules") or not sys.modules.get("sys"):
                return
        except Exception:
            return

        for temp_file in self.temp_files:
            max_attempts = 2
            for attempt in range(max_attempts):
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                    break
                except PermissionError:
                    # 文件可能被锁定，不等待，直接跳过
                    if attempt < max_attempts - 1:
                        continue
                    break
                except Exception:
                    # 静默处理错误，避免在关闭时抛出异常
                    break
        self.temp_files.clear()

    def close(self):
        """关闭服务，清理临时文件"""
        self.cleanup_temp_files()

    def __del__(self):
        """析构函数"""
        # 不执行任何操作，避免在Python关闭时导致崩溃
        # 清理由close()方法显式调用
        pass
