"""文件格式转换服务:doc↔docx、xls↔xlsx,通过 Windows COM 调用 Office。"""

import contextlib
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import ClassVar


class FileConverterService:
    """文件格式转换服务"""

    # 支持的转换格式
    SUPPORTED_CONVERSIONS: ClassVar[dict[str, str]] = {
        ".doc": ".docx",
        ".xls": ".xlsx",
        ".docx": ".doc",
        ".xlsx": ".xls",
    }

    def __init__(self):
        self.temp_files: list[Path] = []  # 记录临时文件
        self._word_app = None
        self._excel_app = None
        self._thread_id = None  # 记录创建 COM 对象的线程ID

    def _ensure_com_initialized(self):
        """
        确保 COM 在当前线程中正确初始化
        如果线程切换了，需要重新创建 COM 对象
        """
        current_thread_id = threading.current_thread().ident
        if self._thread_id is not None and self._thread_id != current_thread_id:
            # 线程已切换，需要释放旧的 COM 对象并重新初始化
            self._release_com_objects()
        self._thread_id = current_thread_id

    def _release_com_objects(self):
        """释放 COM 对象（不调用 Quit，因为可能已经失效）"""
        self._word_app = None
        self._excel_app = None
        self._thread_id = None

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

    def get_target_format(self, file_path: Path) -> str | None:
        """
        获取目标转换格式

        Args:
            file_path: 文件路径

        Returns:
            目标格式后缀，如果不支持转换返回 None
        """
        suffix = file_path.suffix.lower()
        return self.SUPPORTED_CONVERSIONS.get(suffix)

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
        if sys.platform != "win32":
            return False, doc_path, "此功能仅支持 Windows 系统"

        word_app = None
        try:
            import pythoncom
            import win32com.client

            # 初始化当前线程的 COM
            pythoncom.CoInitialize()

            try:
                # 生成输出路径
                if output_path is None:
                    output_path = doc_path.with_suffix(".docx")
                    # 如果目标文件已存在，先尝试删除旧的临时文件
                    if output_path.exists():
                        try:
                            output_path.unlink()
                        except PermissionError:
                            # 文件被锁定，才使用时间戳创建新文件
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            output_path = doc_path.with_name(f"{doc_path.stem}_{timestamp}.docx")

                # 每次创建新的 Word 应用实例，避免 COM 对象失效问题
                word_app = win32com.client.Dispatch("Word.Application")
                word_app.Visible = False
                word_app.DisplayAlerts = False

                # 打开 doc 文件
                doc = word_app.Documents.Open(str(doc_path.absolute()))

                # 保存为 docx (FileFormat=16 for docx)
                doc.SaveAs2(str(output_path.absolute()), FileFormat=16)
                doc.Close()

                self.temp_files.append(output_path)
                return True, output_path, ""
            finally:
                # 关闭 Word 应用
                if word_app is not None:
                    with contextlib.suppress(Exception):
                        word_app.Quit()
                pythoncom.CoUninitialize()

        except ImportError:
            return False, doc_path, "未安装 pywin32 库，请运行: pip install pywin32"
        except Exception as e:
            return False, doc_path, f"转换失败: {e!s}"

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
        if sys.platform != "win32":
            return False, xls_path, "此功能仅支持 Windows 系统"

        excel_app = None
        try:
            import pythoncom
            import win32com.client

            # 初始化当前线程的 COM
            pythoncom.CoInitialize()

            try:
                # 生成输出路径
                if output_path is None:
                    output_path = xls_path.with_suffix(".xlsx")
                    # 如果目标文件已存在，先尝试删除旧的临时文件
                    if output_path.exists():
                        try:
                            output_path.unlink()
                        except PermissionError:
                            # 文件被锁定，才使用时间戳创建新文件
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            output_path = xls_path.with_name(f"{xls_path.stem}_{timestamp}.xlsx")

                # 每次创建新的 Excel 应用实例，避免 COM 对象失效问题
                excel_app = win32com.client.Dispatch("Excel.Application")
                excel_app.Visible = False
                excel_app.DisplayAlerts = False

                # 打开 xls 文件
                wb = excel_app.Workbooks.Open(str(xls_path.absolute()))

                # 保存为 xlsx (FileFormat=51 for xlsx)
                wb.SaveAs(str(output_path.absolute()), FileFormat=51)
                wb.Close()

                self.temp_files.append(output_path)
                return True, output_path, ""
            finally:
                # 关闭 Excel 应用
                if excel_app is not None:
                    with contextlib.suppress(Exception):
                        excel_app.Quit()
                pythoncom.CoUninitialize()

        except ImportError:
            return False, xls_path, "未安装 pywin32 库，请运行: pip install pywin32"
        except Exception as e:
            return False, xls_path, f"转换失败: {e!s}"

    def convert_docx_to_doc(
        self, docx_path: Path, output_path: Path | None = None
    ) -> tuple[bool, Path, str]:
        """
        将 .docx 转换为 .doc

        Args:
            docx_path: docx文件路径
            output_path: 输出路径（可选）

        Returns:
            (是否成功, 转换后的文件路径, 错误消息)
        """
        if sys.platform != "win32":
            return False, docx_path, "此功能仅支持 Windows 系统"

        word_app = None
        try:
            import pythoncom
            import win32com.client

            # 初始化当前线程的 COM
            pythoncom.CoInitialize()

            try:
                # 生成输出路径
                if output_path is None:
                    output_path = docx_path.with_suffix(".doc")

                # 每次创建新的 Word 应用实例，避免 COM 对象失效问题
                word_app = win32com.client.Dispatch("Word.Application")
                word_app.Visible = False
                word_app.DisplayAlerts = False

                # 打开 docx 文件
                doc = word_app.Documents.Open(str(docx_path.absolute()))

                # 保存为 doc (FileFormat=0 for doc)
                doc.SaveAs2(str(output_path.absolute()), FileFormat=0)
                doc.Close()

                return True, output_path, ""
            finally:
                # 关闭 Word 应用
                if word_app is not None:
                    with contextlib.suppress(Exception):
                        word_app.Quit()
                pythoncom.CoUninitialize()

        except ImportError:
            return False, docx_path, "未安装 pywin32 库，请运行: pip install pywin32"
        except Exception as e:
            return False, docx_path, f"转换失败: {e!s}"

    def convert_xlsx_to_xls(
        self, xlsx_path: Path, output_path: Path | None = None
    ) -> tuple[bool, Path, str]:
        """
        将 .xlsx 转换为 .xls

        Args:
            xlsx_path: xlsx文件路径
            output_path: 输出路径（可选）

        Returns:
            (是否成功, 转换后的文件路径, 错误消息)
        """
        if sys.platform != "win32":
            return False, xlsx_path, "此功能仅支持 Windows 系统"

        excel_app = None
        try:
            import pythoncom
            import win32com.client

            # 初始化当前线程的 COM
            pythoncom.CoInitialize()

            try:
                # 生成输出路径
                if output_path is None:
                    output_path = xlsx_path.with_suffix(".xls")

                # 每次创建新的 Excel 应用实例，避免 COM 对象失效问题
                excel_app = win32com.client.Dispatch("Excel.Application")
                excel_app.Visible = False
                excel_app.DisplayAlerts = False

                # 打开 xlsx 文件
                wb = excel_app.Workbooks.Open(str(xlsx_path.absolute()))

                # 保存为 xls (FileFormat=56 for xls)
                wb.SaveAs(str(output_path.absolute()), FileFormat=56)
                wb.Close()

                return True, output_path, ""
            finally:
                # 关闭 Excel 应用
                if excel_app is not None:
                    with contextlib.suppress(Exception):
                        excel_app.Quit()
                pythoncom.CoUninitialize()

        except ImportError:
            return False, xlsx_path, "未安装 pywin32 库，请运行: pip install pywin32"
        except Exception as e:
            return False, xlsx_path, f"转换失败: {e!s}"

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

    def convert_back(self, converted_path: Path, original_path: Path) -> tuple[bool, str]:
        """
        将转换后的文件转回原格式，并覆盖原文件

        Args:
            converted_path: 转换后的文件路径
            original_path: 原始文件路径

        Returns:
            (是否成功, 错误消息)
        """
        original_suffix = original_path.suffix.lower()

        if original_suffix == ".doc":
            success, _, error = self.convert_docx_to_doc(converted_path, original_path)
            return success, error
        elif original_suffix == ".xls":
            success, _, error = self.convert_xlsx_to_xls(converted_path, original_path)
            return success, error
        else:
            return False, "不支持的转换格式"

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
