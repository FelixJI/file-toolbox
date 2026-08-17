"""应用统一文件日志、轮转和未捕获异常记录。"""

from __future__ import annotations

import logging
import platform
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from uuid import uuid4

from file_toolbox import __version__
from file_toolbox.common.paths import get_log_dir

_LOGGER_NAME = "file_toolbox"
_LOG_FILE_NAME = "file-toolbox.log"
_MAX_LOG_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5
_HANDLER_MARKER = "_file_toolbox_file_handler"
# 已记录"应用启动"行的 (日志文件, mode)(按二者去重:gui_entry 与 run_gui 各配置
# 一次只留一行;CLI 先 mode=cli 再进 gui 子命令时保留各自的模式行;测试切换
# tmp 目录换文件时各自保留)。
_startup_line_key: tuple[Path, str] | None = None
_hooks_installed = False
_original_sys_excepthook = sys.excepthook
_original_threading_excepthook = threading.excepthook


def get_log_file() -> Path:
    """返回当前运行目录对应的主日志文件。"""
    return get_log_dir() / _LOG_FILE_NAME


def configure_logging(*, mode: str) -> Path:
    """幂等配置应用 logger，并返回主日志文件路径。"""
    log_file = get_log_file().resolve()
    app_logger = logging.getLogger(_LOGGER_NAME)
    app_logger.setLevel(logging.DEBUG)
    app_logger.propagate = False

    matching_handler: RotatingFileHandler | None = None
    for handler in tuple(app_logger.handlers):
        if not isinstance(handler, RotatingFileHandler) or not getattr(
            handler, _HANDLER_MARKER, False
        ):
            continue
        if Path(handler.baseFilename) == log_file:
            matching_handler = handler
            continue
        app_logger.removeHandler(handler)
        handler.close()

    if matching_handler is None:
        matching_handler = RotatingFileHandler(
            log_file,
            maxBytes=_MAX_LOG_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        setattr(matching_handler, _HANDLER_MARKER, True)
        matching_handler.setLevel(logging.DEBUG)
        matching_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(process)d:%(threadName)s | %(name)s | %(message)s"
            )
        )
        app_logger.addHandler(matching_handler)

    _install_exception_hooks()
    global _startup_line_key
    if _startup_line_key != (log_file, mode):
        _startup_line_key = (log_file, mode)
        app_logger.info(
            "应用启动 version=%s mode=%s platform=%s python=%s",
            __version__,
            mode,
            platform.platform(),
            platform.python_version(),
        )
    return log_file


def new_error_reference() -> str:
    """生成供界面与日志关联的短错误编号。"""
    return uuid4().hex[:8]


def format_user_error(message: str, reference: str) -> str:
    """给用户提示附加错误编号和可查证日志位置。"""
    return f"{message}\n\n错误编号：{reference}\n日志：{get_log_file()}"


def _install_exception_hooks() -> None:
    global _hooks_installed
    if _hooks_installed:
        return
    sys.excepthook = _log_uncaught_exception
    threading.excepthook = _log_uncaught_thread_exception
    _hooks_installed = True


def _log_uncaught_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    traceback: TracebackType | None,
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        _original_sys_excepthook(exc_type, exc_value, traceback)
        return
    logging.getLogger(f"{_LOGGER_NAME}.crash").critical(
        "主线程未捕获异常",
        exc_info=(exc_type, exc_value, traceback),
    )
    _original_sys_excepthook(exc_type, exc_value, traceback)


def _log_uncaught_thread_exception(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:
        _original_threading_excepthook(args)
        return
    logger = logging.getLogger(f"{_LOGGER_NAME}.crash")
    if args.exc_value is None:
        logger.critical(
            "后台线程未捕获异常但无异常实例 thread=%s",
            args.thread.name if args.thread is not None else "unknown",
        )
    else:
        logger.critical(
            "后台线程未捕获异常 thread=%s",
            args.thread.name if args.thread is not None else "unknown",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
    _original_threading_excepthook(args)
