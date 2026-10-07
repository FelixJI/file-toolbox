"""Excel 文档内容替换处理器(.xls/.xlsx),使用 pywin32 COM 接口。"""

import contextlib
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.common.office_session import (
    ComSession,
    dispose_office_app,
    init_office_app,
    open_office_document,
)

# 单个文件操作超时时间（秒）

FILE_OPERATION_TIMEOUT = 30


class ExcelHandler(LoggableMixin):
    """Excel 文档处理器"""

    def read_content(self, file_path: Path) -> str:
        """

        读取 Excel 文档内容



        Args:

            file_path: 文件路径



        Returns:

            文档文本内容

        """

        excel_app = None

        wb = None

        with ComSession():
            try:
                excel_app = init_office_app("Excel.Application")

                wb = open_office_document(excel_app, "Workbooks", file_path, ReadOnly=True)

                text_parts = []

                for sheet in wb.Worksheets:
                    used_range = sheet.UsedRange

                    if used_range is not None:
                        values = used_range.Value

                        if values is not None:
                            if isinstance(values, tuple):
                                for row in values:
                                    if isinstance(row, tuple):
                                        for cell_val in row:
                                            if cell_val is not None:
                                                text_parts.append(str(cell_val))

                                    elif row is not None:
                                        text_parts.append(str(row))

                            else:
                                text_parts.append(str(values))

                return "\n".join(text_parts)

            except Exception as e:
                self.logger.error(f"读取Excel文档失败: {file_path} - {e}")

                raise

            finally:
                try:
                    if wb is not None:
                        wb.Close(False)
                finally:
                    wb = None
                    try:
                        dispose_office_app(excel_app, "Excel.Application", raise_on_error=True)
                    finally:
                        excel_app = None

    def batch_replace(
        self,
        files: list[Path],
        operations: list[dict[str, Any]],
        upgrade_format: bool = False,
        cancel_check: Callable[[], bool] | None = None,
        file_progress_callback: Callable[[int], None] | None = None,
    ) -> dict[str, Any]:  # pragma: no cover —— 入口边界(read_content 同款)已被
        # test_com_handlers 覆盖;但方法体含大量 Find/Replace 深链式 COM 遍历,
        # mock 测不可靠,真测需 Office。整体维持排除,避免虚增未覆盖行误导。
        """

        批量替换 Excel 文档



        Args:

            files: Excel 文件列表

            operations: 操作列表

            upgrade_format: 是否将 .xls 升级为 .xlsx

            cancel_check: 取消检查回调

            file_progress_callback: 文件进度回调



        Returns:

            {'success_count': int, 'total_replacements': int, 'errors': list}

        """

        session = ComSession()

        result: dict[str, Any] = {"success_count": 0, "total_replacements": 0, "errors": []}

        if not files or (cancel_check and cancel_check()):
            return result

        excel_app = None

        com_initialized = False

        try:
            try:
                session.__enter__()

                com_initialized = True

            except Exception as e:
                result["errors"].append(f"COM初始化失败: {e!s}")

                return result

            try:
                excel_app = init_office_app("Excel.Application")

                # ScreenUpdating 是 batch_replace 的业务优化(批量替换时关闭屏幕刷新以
                # 提速),init_office_app 不设此项——故在此单独保留。
                excel_app.ScreenUpdating = False

            except Exception as e:
                result["errors"].append(f"无法启动Excel应用程序: {e!s}")

                return result

            for file_idx, file_path in enumerate(files):
                if file_progress_callback:
                    file_progress_callback(file_idx)

                if cancel_check and cancel_check():
                    break

                wb = None

                file_start_time = time.monotonic()
                file_replacements = 0

                try:

                    def check_timeout(start_time: float = file_start_time) -> None:
                        if cancel_check and cancel_check():
                            raise InterruptedError("已请求取消，当前 Office 调用返回后停止")
                        if time.monotonic() - start_time > FILE_OPERATION_TIMEOUT:
                            raise TimeoutError(
                                f"Office 调用返回后超过 {FILE_OPERATION_TIMEOUT}s 协作时限，停止后续操作"
                            )

                    # 先读取内容检查匹配数

                    wb = open_office_document(excel_app, "Workbooks", file_path, ReadOnly=True)

                    check_timeout()

                    text_parts = []

                    for sheet in wb.Worksheets:
                        used_range = sheet.UsedRange

                        if used_range is not None:
                            values = used_range.Value

                            if values is not None:
                                if isinstance(values, tuple):
                                    for row in values:
                                        if isinstance(row, tuple):
                                            for cell_val in row:
                                                if cell_val is not None:
                                                    text_parts.append(str(cell_val))

                                        elif row is not None:
                                            text_parts.append(str(row))

                                else:
                                    text_parts.append(str(values))

                    wb.Close(False)

                    wb = None

                    check_timeout()

                    content = "\n".join(text_parts)

                    match_count = self._count_matches_in_text(content, operations)

                    if match_count == 0:
                        continue

                    # 打开工作簿进行替换

                    wb = open_office_document(excel_app, "Workbooks", file_path)

                    check_timeout()

                    for operation in operations:
                        try:
                            check_timeout()

                            count = self._execute_operation(wb, operation, check_timeout)

                            file_replacements += count

                        except (TimeoutError, InterruptedError):
                            raise

                        except Exception as op_error:
                            self.logger.error(f"Excel替换操作失败: {op_error}")

                            continue

                    check_timeout()

                    # 保存工作簿

                    is_old_format = file_path.suffix.lower() == ".xls"

                    if upgrade_format and is_old_format:
                        new_path = file_path.with_suffix(".xlsx")

                        wb.SaveAs(str(new_path.absolute()), FileFormat=51)
                        result["success_count"] += 1
                        result["total_replacements"] += file_replacements

                        wb.Close()

                        wb = None

                        with contextlib.suppress(Exception):
                            file_path.unlink()

                    else:
                        wb.Save()
                        result["success_count"] += 1
                        result["total_replacements"] += file_replacements

                        wb.Close()

                        wb = None

                    check_timeout()

                except (TimeoutError, InterruptedError) as error:
                    result["errors"].append(f"{file_path.name}: {error}")
                    if wb is not None:
                        try:
                            wb.Close(False)
                        except Exception as cleanup_error:
                            result["errors"].append(f"关闭文档失败: {cleanup_error}")
                        wb = None
                    break

                except Exception as e:
                    result["errors"].append(f"{file_path.name}: {e!s}")

                    if wb is not None:
                        with contextlib.suppress(Exception):
                            wb.Close(False)
                        wb = None

        except Exception as e:
            result["errors"].append(f"Excel批量处理失败: {e!s}")

        finally:
            try:
                dispose_office_app(excel_app, "Excel.Application", raise_on_error=True)
            except Exception as cleanup_error:
                result["errors"].append(f"Excel清理失败: {cleanup_error}")
            excel_app = None
            if com_initialized:
                try:
                    session.__exit__(None, None, None)
                except Exception as cleanup_error:
                    result["errors"].append(f"COM释放失败: {cleanup_error}")

        return result

    def _execute_operation(
        self,
        wb: Any,
        operation: dict[str, Any],
        check_timeout: Callable[[], None] | None = None,
    ) -> int:  # pragma: no cover
        """执行单个替换操作"""

        from file_toolbox.core.batch_replace.types import ReplaceOperationType

        op_type = operation.get("type")

        params: dict[str, Any] = operation.get("params", {})

        total_count = 0

        if op_type == ReplaceOperationType.SIMPLE_REPLACE.value:
            find_text = params.get("find", "")

            replace_text = params.get("replace", "")

            case_sensitive = params.get("case_sensitive", False)

            if not find_text:
                return 0

            for sheet in wb.Worksheets:
                if check_timeout:
                    check_timeout()

                count = self._count_excel_matches(sheet, find_text, case_sensitive)

                total_count += count

                sheet.Cells.Replace(
                    What=find_text,
                    Replacement=replace_text,
                    LookAt=2,
                    SearchOrder=1,
                    MatchCase=case_sensitive,
                    SearchFormat=False,
                    ReplaceFormat=False,
                )

                self._replace_headers_footers(sheet, find_text, replace_text, case_sensitive)

        elif op_type == ReplaceOperationType.REGEX_REPLACE.value:
            pattern_str = params.get("pattern", "")

            replace_text = params.get("replace", "")

            ignore_case = params.get("ignore_case", False)

            if not pattern_str:
                return 0

            flags = re.IGNORECASE if ignore_case else 0

            try:
                pattern = re.compile(pattern_str, flags)

            except re.error:
                return 0

            for sheet in wb.Worksheets:
                if check_timeout:
                    check_timeout()

                used_range = sheet.UsedRange

                if used_range is None:
                    continue

                for row_idx in range(1, used_range.Rows.Count + 1):
                    if check_timeout:
                        check_timeout()

                    for col_idx in range(1, used_range.Columns.Count + 1):
                        cell = used_range.Cells(row_idx, col_idx)

                        if cell.Value is not None and isinstance(cell.Value, str):
                            new_val, count = pattern.subn(replace_text, cell.Value)

                            if count > 0:
                                cell.Value = new_val

                                total_count += count

                self._replace_headers_footers_regex(sheet, pattern, replace_text)

        return total_count

    def _count_matches_in_text(self, content: str, operations: list[dict[str, Any]]) -> int:
        """统计文本中的匹配数"""
        from file_toolbox.core.batch_replace.types import count_text_matches

        return count_text_matches(content, operations)

    def _count_excel_matches(
        self, sheet: Any, find_text: str, match_case: bool
    ) -> int:  # pragma: no cover
        """统计 Excel 工作表中的匹配数"""
        count = 0
        used_range = sheet.UsedRange
        if used_range is None:
            return 0

        max_iterations = 100000  # 防止无限循环的安全限制
        iteration_count = 0

        first_found = None
        found = used_range.Find(
            What=find_text,
            LookIn=-4163,  # xlValues
            LookAt=2,  # xlPart
            SearchOrder=1,  # xlByRows
            MatchCase=match_case,
        )

        while found is not None and iteration_count < max_iterations:
            if first_found is None:
                first_found = found.Address
            else:
                if found.Address == first_found:
                    break
            count += 1
            found = used_range.FindNext(found)
            if found is None:
                break
            iteration_count += 1

        if iteration_count >= max_iterations:
            self.logger.warning(
                f"Excel matching iteration limit reached ({max_iterations}). "
                f"Sheet may have corruption or circular references."
            )
        return count

    def _replace_headers_footers(
        self, sheet: Any, find_text: str, replace_text: str, case_sensitive: bool
    ) -> None:  # pragma: no cover
        """替换 Excel 页眉页脚"""

        try:
            ps = sheet.PageSetup

            header_footer_props = [
                "LeftHeader",
                "CenterHeader",
                "RightHeader",
                "LeftFooter",
                "CenterFooter",
                "RightFooter",
            ]

            for prop in header_footer_props:
                try:
                    value = getattr(ps, prop)

                    if value:
                        if case_sensitive:
                            new_value = value.replace(find_text, replace_text)

                        else:
                            pattern = re.compile(re.escape(find_text), re.IGNORECASE)

                            new_value = pattern.sub(replace_text, value)

                        if new_value != value:
                            setattr(ps, prop, new_value)

                except Exception:
                    pass

        except Exception as e:
            self.logger.error(f"Excel页眉页脚替换失败: {e}")

    def _replace_headers_footers_regex(
        self, sheet: Any, pattern: re.Pattern[str], replace_text: str
    ) -> None:  # pragma: no cover
        """使用正则替换 Excel 页眉页脚"""

        try:
            ps = sheet.PageSetup

            header_footer_props = [
                "LeftHeader",
                "CenterHeader",
                "RightHeader",
                "LeftFooter",
                "CenterFooter",
                "RightFooter",
            ]

            for prop in header_footer_props:
                try:
                    value = getattr(ps, prop)

                    if value:
                        new_value, _ = pattern.subn(replace_text, value)

                        if new_value != value:
                            setattr(ps, prop, new_value)

                except Exception:
                    pass

        except Exception as e:
            self.logger.error(f"Excel页眉页脚正则替换失败: {e}")
