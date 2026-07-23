"""Word 文档内容替换处理器(.doc/.docx),使用 pywin32 COM 接口。"""

import contextlib
import gc
import time
from collections.abc import Callable
from pathlib import Path

from file_toolbox.common.loggable import LoggableMixin

# 单个文件操作超时时间（秒）

FILE_OPERATION_TIMEOUT = 30


class WordHandler(LoggableMixin):
    """Word 文档处理器"""

    def __init__(self, get_office_pids: Callable, kill_office_processes: Callable):
        """

        初始化 Word 处理器



        Args:

            get_office_pids: 获取 Office 进程 PID 的函数

            kill_office_processes: 清理 Office 进程的函数

        """

        self._get_office_pids = get_office_pids

        self._kill_office_processes = kill_office_processes

    def read_content(self, file_path: Path) -> str:  # pragma: no cover
        """

        读取 Word 文档内容（包含正文、页眉页脚、文本框）



        Args:

            file_path: 文件路径



        Returns:

            文档文本内容

        """

        import pythoncom
        import win32com.client

        word_app = None

        doc = None

        com_initialized = False

        try:
            pythoncom.CoInitialize()

            com_initialized = True

            word_app = win32com.client.Dispatch("Word.Application")

            word_app.Visible = False

            word_app.DisplayAlerts = False

            doc = word_app.Documents.Open(str(file_path.absolute()), ReadOnly=True)

            return self._extract_all_text(doc)

        except Exception as e:
            self.logger.error(f"读取Word文档失败: {file_path} - {e}")

            return ""

        finally:
            if doc is not None:
                with contextlib.suppress(Exception):
                    doc.Close(False)

            if word_app is not None:
                with contextlib.suppress(Exception):
                    word_app.Quit()

            doc = None
            word_app = None
            gc.collect()

            if com_initialized:
                with contextlib.suppress(Exception):
                    pythoncom.CoUninitialize()

    def _extract_all_text(self, doc) -> str:  # pragma: no cover
        """提取文档全文:正文 + 页眉页脚 + 文本框/形状。

        read_content 与 batch_replace 共用此逻辑,避免两处复制粘贴。
        """
        text_parts = []
        if doc.Content.Text:
            text_parts.append(doc.Content.Text)
        text_parts.extend(self._get_headers_footers_text(doc))
        text_parts.extend(self._get_shapes_text(doc))
        return "\n".join(text_parts)

    def batch_replace(
        self,
        files: list[Path],
        operations: list[dict],
        upgrade_format: bool = False,
        cancel_check: Callable | None = None,
        file_progress_callback: Callable | None = None,
    ) -> dict:  # pragma: no cover
        """

        批量替换 Word 文档



        Args:

            files: Word 文件列表

            operations: 操作列表

            upgrade_format: 是否将 .doc 升级为 .docx

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

        word_app = None

        com_initialized = False

        word_pids_before = self._get_office_pids("WINWORD.EXE")

        try:
            try:
                pythoncom.CoInitialize()

                com_initialized = True

            except Exception as e:
                result["errors"].append(f"COM初始化失败: {e!s}")

                return result

            try:
                word_app = win32com.client.Dispatch("Word.Application")

                word_app.Visible = False

                word_app.DisplayAlerts = False

                word_app.ScreenUpdating = False

            except Exception as e:
                result["errors"].append(f"无法启动Word应用程序: {e!s}")

                return result

            for file_idx, file_path in enumerate(files):
                if file_progress_callback:
                    file_progress_callback(file_idx)

                if cancel_check and cancel_check():
                    break

                doc = None

                file_start_time = time.time()

                try:

                    def check_timeout(start_time=file_start_time):
                        if time.time() - start_time > FILE_OPERATION_TIMEOUT:
                            raise TimeoutError(f"文件操作超时 ({FILE_OPERATION_TIMEOUT}s)")

                    # 先读取内容检查匹配数

                    doc = word_app.Documents.Open(str(file_path.absolute()), ReadOnly=True)

                    check_timeout()

                    full_text = self._extract_all_text(doc)

                    doc.Close(False)

                    doc = None

                    check_timeout()

                    match_count = self._count_matches_in_text(full_text, operations)

                    if match_count == 0:
                        continue

                    # 打开文档进行替换

                    doc = word_app.Documents.Open(str(file_path.absolute()))

                    check_timeout()

                    for operation in operations:
                        try:
                            check_timeout()

                            count = self._execute_operation(doc, operation)

                            result["total_replacements"] += count

                        except TimeoutError:
                            raise

                        except Exception as op_error:
                            self.logger.error(f"Word替换操作失败: {op_error}")

                            continue

                    # 保存文档

                    is_old_format = file_path.suffix.lower() == ".doc"

                    if upgrade_format and is_old_format:
                        new_path = file_path.with_suffix(".docx")

                        doc.SaveAs2(str(new_path.absolute()), FileFormat=16)

                        doc.Close()

                        doc = None

                        with contextlib.suppress(Exception):
                            file_path.unlink()

                    else:
                        doc.Save()

                        doc.Close()

                        doc = None

                    result["success_count"] += 1

                except TimeoutError as te:
                    result["errors"].append(f"{file_path.name}: {te!s}")

                    if doc is not None:
                        with contextlib.suppress(Exception):
                            doc.Close(False)
                        doc = None

                    # 超时后尝试重启 Word
                    try:
                        word_app.Quit()

                    except Exception as e:
                        self.logger.warning(f"Word应用退出失败: {e}")

                    word_app = None

                    gc.collect()

                    time.sleep(0.5)

                    self._kill_office_processes("WINWORD.EXE", word_pids_before)

                    time.sleep(0.5)

                    try:
                        word_app = win32com.client.Dispatch("Word.Application")

                        word_app.Visible = False

                        word_app.DisplayAlerts = False

                    except Exception:
                        break

                except Exception as e:
                    result["errors"].append(f"{file_path.name}: {e!s}")

                    if doc is not None:
                        with contextlib.suppress(Exception):
                            doc.Close(False)
                        doc = None

        except Exception as e:
            result["errors"].append(f"Word批量处理失败: {e!s}")

        finally:
            if word_app is not None:
                with contextlib.suppress(Exception):
                    word_app.Quit()

            word_app = None
            gc.collect()
            time.sleep(0.3)

            self._kill_office_processes("WINWORD.EXE", word_pids_before)

            if com_initialized:
                with contextlib.suppress(Exception):
                    pythoncom.CoUninitialize()

        return result

    def _execute_operation(self, doc, operation: dict) -> int:  # pragma: no cover
        """执行单个替换操作"""

        from file_toolbox.core.batch_replace.types import ReplaceOperationType

        op_type = operation.get("type")

        params = operation.get("params", {})

        if op_type == ReplaceOperationType.SIMPLE_REPLACE.value:
            find_text = params.get("find", "")

            replace_text = params.get("replace", "")

            case_sensitive = params.get("case_sensitive", False)

            if not find_text:
                return 0

            count = self._count_word_matches(doc, find_text, case_sensitive, False)

            self._word_global_replace(doc, find_text, replace_text, case_sensitive, False)

            return count

        elif op_type == ReplaceOperationType.REGEX_REPLACE.value:
            pattern_str = params.get("pattern", "")

            replace_text = params.get("replace", "")

            ignore_case = params.get("ignore_case", False)

            if not pattern_str:
                return 0

            count = self._count_word_matches(doc, pattern_str, not ignore_case, True)

            self._word_global_replace(doc, pattern_str, replace_text, not ignore_case, True)

            return count

        return 0

    def _count_matches_in_text(self, content: str, operations: list[dict]) -> int:
        """统计文本中的匹配数"""

        import re

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

    def _count_word_matches(
        self, doc, find_text: str, match_case: bool, use_wildcards: bool
    ) -> int:  # pragma: no cover
        """统计 Word 文档中的匹配数"""
        count = 0
        max_iterations = 10000
        iteration_count = 0
        try:
            rng = doc.Content
            doc_end = rng.End
            rng.Start = 0
            last_start = -1
            while iteration_count < max_iterations:
                found = rng.Find.Execute(
                    FindText=find_text,
                    MatchCase=match_case,
                    MatchWholeWord=False,
                    MatchWildcards=use_wildcards,
                    Forward=True,
                    Wrap=0,
                )

                if not found:
                    break

                current_start = rng.Start
                if current_start == last_start:
                    break

                last_start = current_start
                count += 1
                iteration_count += 1

                new_start = rng.End
                if new_start >= doc_end:
                    break

                rng.Start = new_start
                rng.End = doc_end

                if rng.Start >= rng.End:
                    break
            if iteration_count >= max_iterations:
                self.logger.warning(
                    f"Word matching iteration limit reached ({max_iterations}). "
                    f"Document may have corruption or infinite loop."
                )
        except Exception as e:
            self.logger.error(f"统计Word匹配数时出错: {e}")
        return count

    def _word_global_replace(
        self,
        doc,
        find_text: str,
        replace_text: str,
        match_case: bool,
        use_wildcards: bool,
    ):  # pragma: no cover
        """Word 全局替换：遍历所有 StoryRanges"""
        story_types = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        max_story_iterations = 1000  # 防止无限循环的安全限制
        for story_type in story_types:
            try:
                story_range = doc.StoryRanges(story_type)
                iteration_count = 0
                while story_range is not None and iteration_count < max_story_iterations:
                    try:
                        story_range.Find.ClearFormatting()
                        story_range.Find.Replacement.ClearFormatting()
                        story_range.Find.Execute(
                            FindText=find_text,
                            MatchCase=match_case,
                            MatchWholeWord=False,
                            MatchWildcards=use_wildcards,
                            MatchSoundsLike=False,
                            MatchAllWordForms=False,
                            Forward=True,
                            Wrap=1,
                            Format=False,
                            ReplaceWith=replace_text,
                            Replace=2,
                        )

                        story_range = story_range.NextStoryRange
                        iteration_count += 1
                    except Exception:
                        break
                if iteration_count >= max_story_iterations:
                    self.logger.warning(
                        f"StoryRange iteration limit reached for story type {story_type}. "
                        f"Possible circular reference or document corruption."
                    )
            except Exception:
                pass

        # 额外处理形状中的文本

        self._replace_shapes(doc, find_text, replace_text, match_case, use_wildcards)

    def _get_headers_footers_text(self, doc) -> list[str]:  # pragma: no cover
        """获取页眉页脚文本"""

        text_parts = []

        try:
            for section in doc.Sections:
                for header_type in [1, 2, 3]:
                    try:
                        header = section.Headers(header_type)

                        if header.Exists and header.Range.Text:
                            text_parts.append(header.Range.Text)

                    except Exception:
                        pass

                for footer_type in [1, 2, 3]:
                    try:
                        footer = section.Footers(footer_type)

                        if footer.Exists and footer.Range.Text:
                            text_parts.append(footer.Range.Text)

                    except Exception:
                        pass

        except Exception as e:
            self.logger.error(f"获取页眉页脚文本失败: {e}")

        return text_parts

    def _get_shapes_text(self, doc) -> list[str]:  # pragma: no cover
        """获取形状（文本框）中的文本"""

        text_parts = []

        try:
            text_parts.extend(self._get_shapes_text_from_collection(doc.Shapes))

            for section in doc.Sections:
                for header_type in [1, 2, 3]:
                    try:
                        header = section.Headers(header_type)

                        if header.Exists:
                            text_parts.extend(self._get_shapes_text_from_collection(header.Shapes))

                    except Exception:
                        pass

                for footer_type in [1, 2, 3]:
                    try:
                        footer = section.Footers(footer_type)

                        if footer.Exists:
                            text_parts.extend(self._get_shapes_text_from_collection(footer.Shapes))

                    except Exception:
                        pass

        except Exception as e:
            self.logger.error(f"获取形状文本失败: {e}")

        return text_parts

    def _get_shapes_text_from_collection(self, shapes) -> list[str]:  # pragma: no cover
        """从 Shapes 集合提取文本"""

        text_parts = []

        try:
            for shape in shapes:
                try:
                    if shape.TextFrame.HasText:
                        text = shape.TextFrame.TextRange.Text

                        if text:
                            text_parts.append(text)

                except Exception:
                    pass

                try:
                    if shape.Type == 6:  # msoGroup
                        text_parts.extend(self._get_shapes_text_from_collection(shape.GroupItems))

                except Exception:
                    pass

        except Exception:
            pass

        return text_parts

    def _replace_shapes(
        self,
        doc,
        find_text: str,
        replace_text: str,
        match_case: bool,
        use_wildcards: bool,
    ):  # pragma: no cover
        """替换形状中的文本"""

        try:
            self._replace_shapes_in_collection(
                doc.Shapes, find_text, replace_text, match_case, use_wildcards
            )

            for section in doc.Sections:
                for header_type in [1, 2, 3]:
                    try:
                        header = section.Headers(header_type)

                        if header.Exists:
                            self._replace_shapes_in_collection(
                                header.Shapes,
                                find_text,
                                replace_text,
                                match_case,
                                use_wildcards,
                            )

                    except Exception:
                        pass

                for footer_type in [1, 2, 3]:
                    try:
                        footer = section.Footers(footer_type)

                        if footer.Exists:
                            self._replace_shapes_in_collection(
                                footer.Shapes,
                                find_text,
                                replace_text,
                                match_case,
                                use_wildcards,
                            )

                    except Exception:
                        pass

        except Exception as e:
            self.logger.error(f"替换形状失败: {e}")

    def _replace_shapes_in_collection(
        self,
        shapes,
        find_text: str,
        replace_text: str,
        match_case: bool,
        use_wildcards: bool,
    ):  # pragma: no cover
        """在 Shapes 集合中执行替换"""

        try:
            for shape in shapes:
                try:
                    if shape.TextFrame.HasText:
                        rng = shape.TextFrame.TextRange

                        find = rng.Find

                        find.ClearFormatting()

                        find.Replacement.ClearFormatting()

                        find.Text = find_text

                        find.Replacement.Text = replace_text

                        find.Forward = True

                        find.Wrap = 1

                        find.Format = False

                        find.MatchCase = match_case

                        find.MatchWholeWord = False

                        find.MatchWildcards = use_wildcards

                        find.MatchSoundsLike = False

                        find.MatchAllWordForms = False

                        find.Execute(Replace=2)

                except Exception:
                    pass

                try:
                    if shape.Type == 6:  # msoGroup
                        self._replace_shapes_in_collection(
                            shape.GroupItems,
                            find_text,
                            replace_text,
                            match_case,
                            use_wildcards,
                        )

                except Exception:
                    pass

        except Exception as e:
            self.logger.error(f"替换形状集合失败: {e}")
