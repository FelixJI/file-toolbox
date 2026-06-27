"""Excel 文档内容替换处理器(.xls/.xlsx),使用 pywin32 COM 接口。"""

import contextlib
import gc
import re
import time
from collections.abc import Callable
from pathlib import Path

from file_toolbox.common.loggable import LoggableMixin

# 单个文件操作超时时间（秒）

FILE_OPERATION_TIMEOUT = 30


class ExcelHandler(LoggableMixin):
    """Excel 文档处理器"""

    def __init__(self, get_office_pids: Callable, kill_office_processes: Callable):
        """

        初始化 Excel 处理器



        Args:

            get_office_pids: 获取 Office 进程 PID 的函数

            kill_office_processes: 清理 Office 进程的函数

        """

        self._get_office_pids = get_office_pids

        self._kill_office_processes = kill_office_processes

    def read_content(self, file_path: Path) -> str:
        """

        读取 Excel 文档内容



        Args:

            file_path: 文件路径



        Returns:

            文档文本内容

        """

        import pythoncom
        import win32com.client

        excel_app = None

        wb = None

        com_initialized = False

        try:
            pythoncom.CoInitialize()

            com_initialized = True

            excel_app = win32com.client.Dispatch("Excel.Application")

            excel_app.Visible = False

            excel_app.DisplayAlerts = False

            wb = excel_app.Workbooks.Open(str(file_path.absolute()), ReadOnly=True)

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

            return ""

        finally:
            if wb is not None:
                with contextlib.suppress(Exception):
                    wb.Close(False)

            if excel_app is not None:
                with contextlib.suppress(Exception):
                    excel_app.Quit()

            wb = None
            excel_app = None
            gc.collect()

            if com_initialized:
                with contextlib.suppress(Exception):
                    pythoncom.CoUninitialize()

    def batch_replace(
        self,
        files: list[Path],
        operations: list[dict],
        upgrade_format: bool = False,
        cancel_check: Callable | None = None,
        file_progress_callback: Callable | None = None,
    ) -> dict:
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

        import pythoncom
        import win32com.client

        result = {"success_count": 0, "total_replacements": 0, "errors": []}

        if not files:
            return result

        excel_app = None

        com_initialized = False

        excel_pids_before = self._get_office_pids("EXCEL.EXE")

        try:
            try:
                pythoncom.CoInitialize()

                com_initialized = True

            except Exception as e:
                result["errors"].append(f"COM初始化失败: {e!s}")

                return result

            try:
                excel_app = win32com.client.Dispatch("Excel.Application")

                excel_app.Visible = False

                excel_app.DisplayAlerts = False

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

                file_start_time = time.time()

                try:

                    def check_timeout(start_time=file_start_time):
                        if time.time() - start_time > FILE_OPERATION_TIMEOUT:
                            raise TimeoutError(f"文件操作超时 ({FILE_OPERATION_TIMEOUT}s)")

                    # 先读取内容检查匹配数

                    wb = excel_app.Workbooks.Open(str(file_path.absolute()), ReadOnly=True)

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

                    wb = excel_app.Workbooks.Open(str(file_path.absolute()))

                    check_timeout()

                    for operation in operations:
                        try:
                            check_timeout()

                            count = self._execute_operation(wb, operation, check_timeout)

                            result["total_replacements"] += count

                        except TimeoutError:
                            raise

                        except Exception as op_error:
                            self.logger.error(f"Excel替换操作失败: {op_error}")

                            continue

                    # 保存工作簿

                    is_old_format = file_path.suffix.lower() == ".xls"

                    if upgrade_format and is_old_format:
                        new_path = file_path.with_suffix(".xlsx")

                        wb.SaveAs(str(new_path.absolute()), FileFormat=51)

                        wb.Close()

                        wb = None

                        with contextlib.suppress(Exception):
                            file_path.unlink()

                    else:
                        wb.Save()

                        wb.Close()

                        wb = None

                    result["success_count"] += 1

                except TimeoutError as te:
                    result["errors"].append(f"{file_path.name}: {te!s}")

                    if wb is not None:
                        with contextlib.suppress(Exception):
                            wb.Close(False)
                        wb = None

                    with contextlib.suppress(Exception):
                        excel_app.Quit()

                    excel_app = None
                    gc.collect()
                    time.sleep(0.5)
                    self._kill_office_processes("EXCEL.EXE", excel_pids_before)
                    time.sleep(0.5)

                    try:
                        excel_app = win32com.client.Dispatch("Excel.Application")
                        excel_app.Visible = False
                        excel_app.DisplayAlerts = False
                    except Exception:
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
            if excel_app is not None:
                with contextlib.suppress(Exception):
                    excel_app.Quit()

            excel_app = None
            gc.collect()
            time.sleep(0.3)
            self._kill_office_processes("EXCEL.EXE", excel_pids_before)

            if com_initialized:
                with contextlib.suppress(Exception):
                    pythoncom.CoUninitialize()

        return result

    def _execute_operation(self, wb, operation: dict, check_timeout: Callable | None = None) -> int:
        """执行单个替换操作"""

        from file_toolbox.core.batch_replace.types import ReplaceOperationType

        op_type = operation.get("type")

        params = operation.get("params", {})

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

    def _count_matches_in_text(self, content: str, operations: list[dict]) -> int:
        """统计文本中的匹配数"""

        from file_toolbox.core.batch_replace.types import ReplaceOperationType

        total = 0

        for operation in operations:
            op_type = operation.get("type")

            params = operation.get("params", {})

            if op_type == ReplaceOperationType.SIMPLE_REPLACE.value:
                find_text = params.get("find", "")

                case_sensitive = params.get("case_sensitive", False)

                if find_text:
                    if case_sensitive:
                        total += content.count(find_text)

                    else:
                        total += content.lower().count(find_text.lower())

            elif op_type == ReplaceOperationType.REGEX_REPLACE.value:
                pattern = params.get("pattern", "")

                ignore_case = params.get("ignore_case", False)

                if pattern:
                    try:
                        flags = re.IGNORECASE if ignore_case else 0

                        matches = list(re.finditer(pattern, content, flags))

                        total += len(matches)

                    except re.error:
                        pass

        return total

    def _count_excel_matches(self, sheet, find_text: str, match_case: bool) -> int:
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
        self, sheet, find_text: str, replace_text: str, case_sensitive: bool
    ):
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

    def _replace_headers_footers_regex(self, sheet, pattern, replace_text: str):
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
