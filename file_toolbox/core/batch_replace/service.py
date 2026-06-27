"""批量文档内容替换核心逻辑:协调 Word/Excel/文本处理,预览-执行两段式,自动备份。"""

import contextlib
import gc
import shutil
import subprocess
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from file_toolbox.common.base_operation import BaseOperationService
from file_toolbox.common.file_utils import format_file_size
from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.common.paths import get_backup_dir
from file_toolbox.core.batch_replace.file_converter import FileConverterService
from file_toolbox.core.batch_replace.handlers.excel_handler import ExcelHandler
from file_toolbox.core.batch_replace.handlers.text_handler import TextHandler
from file_toolbox.core.batch_replace.handlers.word_handler import WordHandler
from file_toolbox.core.batch_replace.types import REPLACE_PARAM_RULES, ReplaceOperationType

# 子进程超时(秒)
SUBPROCESS_TIMEOUT_SECONDS = 5

# 单个文件操作超时时间（秒）
FILE_OPERATION_TIMEOUT = 30
# 应用程序退出超时时间（秒）
APP_QUIT_TIMEOUT = 10
# 文本文件并行处理的最大线程数
MAX_TEXT_WORKERS = 4


class ContentReplaceService(BaseOperationService, LoggableMixin):
    """内容替换服务"""

    SUPPORTED_FORMATS: ClassVar[set[str]] = {".docx", ".doc", ".xlsx", ".xls", ".txt", ".md"}

    DIRECT_FORMATS: ClassVar[set[str]] = {".docx", ".xlsx", ".txt", ".md"}

    CONVERT_FORMATS: ClassVar[set[str]] = {".doc", ".xls"}

    def __init__(self):
        self.converter = FileConverterService()
        self._lock = threading.Lock()
        self._initial_word_pids = self._get_office_pids("WINWORD.EXE")
        self._initial_excel_pids = self._get_office_pids("EXCEL.EXE")
        # 初始化各类型处理器
        self._word_handler = WordHandler(self._get_office_pids, self._kill_new_office_processes)
        self._excel_handler = ExcelHandler(self._get_office_pids, self._kill_new_office_processes)
        self._text_handler = TextHandler()
        # 初始化备份目录
        self._backup_dir = get_backup_dir()

    def get_operation_types(self) -> list[str]:
        """获取支持的操作类型列表"""
        return [t.value for t in ReplaceOperationType]

    def _validate_params(self, operation: dict, index: int) -> tuple[bool, str]:
        """验证操作参数(委托给共享的声明式规则表)。"""
        from file_toolbox.common.op_schema import validate_params

        return validate_params(operation, index, REPLACE_PARAM_RULES)

    def _get_office_pids(self, process_name: str) -> list[int]:
        """获取指定 Office 进程的 PID 列表"""
        pids = []

        try:
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"IMAGENAME eq {process_name}",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )

            for line in result.stdout.strip().split("\n"):
                parts = line.replace('"', "").split(",")

                if len(parts) >= 2 and parts[1].isdigit():
                    pids.append(int(parts[1]))

        except Exception:
            pass

        return pids

    def _kill_new_office_processes(self, process_name: str, pids_before: list[int]):
        """强制结束新启动的 Office 进程"""
        current_pids = self._get_office_pids(process_name)
        new_pids = set(current_pids) - set(pids_before)

        for pid in new_pids:
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    timeout=SUBPROCESS_TIMEOUT_SECONDS,
                )

    def is_supported_file(self, file_path: Path) -> bool:
        """检查文件是否为支持的格式"""
        return file_path.suffix.lower() in self.SUPPORTED_FORMATS

    def is_file_locked(self, file_path: Path) -> tuple[bool, str]:
        """检查文件是否被占用/锁定"""
        if not file_path.exists():
            return True, "文件不存在"

        if file_path.name.startswith("~$") or file_path.suffix.lower() == ".tmp":
            return True, "临时文件，跳过处理"

        try:
            with open(file_path, "r+b"):
                pass
            return False, ""
        except PermissionError:
            return True, "文件被占用或无写入权限"
        except Exception as e:
            return True, f"无法访问: {e!s}"

    def preview_replace(
        self,
        files: list[Path],
        operations: list[dict],
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[Path, dict]:
        """

        预览替换结果（不修改文件）



        Args:

            files: 文件路径列表

            operations: 操作列表



        Returns:

            字典: {文件路径: {"match_count": 数量, "status": 状态, ...}}

        """

        result = {}

        for file_path in files:
            # 检查是否取消
            if cancel_check and cancel_check():
                self.logger.info("预览操作被取消")
                break

            try:
                if not self.is_supported_file(file_path):
                    result[file_path] = {
                        "match_count": 0,
                        "status": "❌ 不支持的格式",
                        "needs_conversion": False,
                        "file_size": (
                            format_file_size(file_path.stat().st_size)
                            if file_path.exists()
                            else "未知"
                        ),
                    }

                    continue

                # 占用检查:文件被其它程序打开/只读/不存在时跳过,避免 COM Open 抛错或卡住
                locked, lock_reason = self.is_file_locked(file_path)
                if locked:
                    result[file_path] = {
                        "match_count": 0,
                        "status": f"❌ {lock_reason}",
                        "needs_conversion": False,
                        "file_size": (
                            format_file_size(file_path.stat().st_size)
                            if file_path.exists()
                            else "未知"
                        ),
                    }
                    continue

                needs_conversion = self.converter.is_conversion_needed(file_path)

                if needs_conversion:
                    success, converted_path, error = self.converter.auto_convert_if_needed(
                        file_path
                    )

                    if not success:
                        result[file_path] = {
                            "match_count": 0,
                            "status": f"❌ {error}",
                            "needs_conversion": True,
                            "file_size": (
                                format_file_size(file_path.stat().st_size)
                                if file_path.exists()
                                else "未知"
                            ),
                        }

                        continue

                    match_count = self._count_matches(converted_path, operations)

                    result[file_path] = {
                        "match_count": match_count,
                        "status": "✓ 准备就绪" if match_count > 0 else "ℹ️ 无匹配",
                        "needs_conversion": True,
                        "converted_path": converted_path,
                        "file_size": format_file_size(file_path.stat().st_size),
                    }

                else:
                    match_count = self._count_matches(file_path, operations)

                    result[file_path] = {
                        "match_count": match_count,
                        "status": "✓ 准备就绪" if match_count > 0 else "ℹ️ 无匹配",
                        "needs_conversion": False,
                        "file_size": format_file_size(file_path.stat().st_size),
                    }

            except Exception as e:
                result[file_path] = {
                    "match_count": 0,
                    "status": f"❌ 错误: {e!s}",
                    "needs_conversion": False,
                    "file_size": "未知",
                }

        gc.collect()

        self.converter.cleanup_temp_files()

        return result

    def execute_replace(
        self,
        files: list[Path],
        operations: list[dict],
        keep_new_format: bool = False,
        progress_callback=None,
        cancel_check=None,
    ) -> tuple[int, int, list[str]]:
        """

        执行替换操作



        Args:

            files: 文件列表

            operations: 操作列表

            keep_new_format: 转换后是否保留新格式

            progress_callback: 进度回调函数

            cancel_check: 取消检查回调



        Returns:

            (成功数量, 总替换次数, 错误消息列表)

        """

        if not files:
            return 0, 0, ["文件列表为空"]

        if not operations:
            return 0, 0, ["操作列表为空"]

        valid, error_msg = self.validate_operations(operations)

        if not valid:
            return 0, 0, [error_msg]

        success_count = 0
        total_replacements = 0
        errors = []

        def is_cancelled():
            return cancel_check and cancel_check()

        # 按文件类型分组
        docx_files = []
        xlsx_files = []
        text_files = []

        for file_path in files:
            if not self.is_supported_file(file_path):
                errors.append(f"{file_path.name}: 不支持的格式")
                continue

            # 占用检查:被锁定/不存在的文件跳过,避免 COM Open 卡住或抛异常
            locked, lock_reason = self.is_file_locked(file_path)
            if locked:
                errors.append(f"{file_path.name}: {lock_reason}")
                continue

            suffix = file_path.suffix.lower()

            if suffix in [".docx", ".doc"]:
                docx_files.append(file_path)
            elif suffix in [".xlsx", ".xls"]:
                xlsx_files.append(file_path)
            elif suffix in [".txt", ".md"]:
                text_files.append(file_path)

        total_files = len(files)
        processed = 0

        # 1. 处理文本文件
        for file_path in text_files:
            if is_cancelled():
                break

            try:
                # 创建备份
                backup_path = self._create_backup(file_path)
                self.logger.debug(f"备份已创建: {backup_path}")

                content = self._text_handler.read_content(file_path)
                match_count = self._text_handler.count_matches(content, operations)

                if match_count > 0:
                    replace_count = self._text_handler.replace_file(file_path, operations)
                    total_replacements += replace_count
                    success_count += 1

            except Exception as e:
                errors.append(f"{file_path.name}: {e!s}")

            finally:
                processed += 1
                if progress_callback:
                    progress_callback(processed, total_files)

        # 2. 处理 Word 文档(先创建备份)
        if docx_files and not is_cancelled():
            # 为所有Word文档创建备份
            backup_paths = []
            for file_path in docx_files:
                try:
                    backup_path = self._create_backup(file_path)
                    backup_paths.append((file_path, backup_path))
                except Exception as e:
                    errors.append(f"{file_path.name}: 备份失败 - {e!s}")

            def word_file_callback(file_idx):
                nonlocal processed
                processed = len(text_files) + file_idx
                if progress_callback:
                    progress_callback(processed, total_files)

            result = self._word_handler.batch_replace(
                docx_files,
                operations,
                keep_new_format,
                cancel_check,
                word_file_callback,
            )

            success_count += result["success_count"]
            total_replacements += result["total_replacements"]
            errors.extend(result["errors"])

            processed = len(text_files) + len(docx_files)

            if progress_callback:
                progress_callback(processed, total_files)

        # 3. 处理 Excel 文档(先创建备份)
        if xlsx_files and not is_cancelled():
            # 为所有Excel文档创建备份
            for file_path in xlsx_files:
                try:
                    backup_path = self._create_backup(file_path)
                except Exception as e:
                    errors.append(f"{file_path.name}: 备份失败 - {e!s}")

            def excel_file_callback(file_idx):
                nonlocal processed
                processed = len(text_files) + len(docx_files) + file_idx
                if progress_callback:
                    progress_callback(processed, total_files)

            result = self._excel_handler.batch_replace(
                xlsx_files,
                operations,
                keep_new_format,
                cancel_check,
                excel_file_callback,
            )

            success_count += result["success_count"]
            total_replacements += result["total_replacements"]
            errors.extend(result["errors"])

            processed = len(text_files) + len(docx_files) + len(xlsx_files)

            if progress_callback:
                progress_callback(processed, total_files)

        self.converter.cleanup_temp_files()

        return success_count, total_replacements, errors

    def _count_matches(self, file_path: Path, operations: list[dict]) -> int:
        """统计文件中的匹配数量"""
        content = self._read_file_content(file_path)

        if content is None:
            return 0

        return self._text_handler.count_matches(content, operations)

    def _read_file_content(self, file_path: Path) -> str | None:
        """读取文件内容"""

        suffix = file_path.suffix.lower()

        try:
            if suffix in [".txt", ".md"]:
                content = self._text_handler.read_content(file_path)

            elif suffix in [".docx", ".doc"]:
                content = self._word_handler.read_content(file_path)

            elif suffix in [".xlsx", ".xls"]:
                content = self._excel_handler.read_content(file_path)

            else:
                return None

            return TextHandler.normalize_text(content) if content else content

        except Exception as e:
            self.logger.error(f"读取文件失败: {file_path} - {e}")

            return None

    def close(self):
        """关闭服务，释放资源"""
        with contextlib.suppress(Exception):
            self.converter.close()

        # 检查Python是否正在关闭，避免在关闭时执行不安全操作
        import sys

        # 检查解释器是否正在关闭
        if hasattr(sys, "exitfunc") or not sys.modules.get("sys"):
            return

        try:
            if self._lock.acquire(blocking=False):
                try:
                    self._kill_new_office_processes("WINWORD.EXE", self._initial_word_pids)
                    self._kill_new_office_processes("EXCEL.EXE", self._initial_excel_pids)
                finally:
                    self._lock.release()
        except Exception:
            pass

    def _create_backup(self, file_path: Path) -> Path:
        """创建文件备份

        Args:
            file_path: 原文件路径

        Returns:
            备份文件路径
        """

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        backup_path = self._backup_dir / backup_name
        shutil.copy2(file_path, backup_path)
        self.logger.info(f"创建备份: {file_path} -> {backup_path}")
        return backup_path

    def __del__(self):
        """析构函数"""
        with contextlib.suppress(Exception):
            self.close()
