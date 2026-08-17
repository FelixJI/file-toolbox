import logging
import sys
from logging.handlers import RotatingFileHandler

from file_toolbox.common.logging_config import configure_logging, get_log_file


def _flush_file_handlers() -> None:
    for handler in logging.getLogger("file_toolbox").handlers:
        handler.flush()


def test_configure_logging_creates_single_rotating_utf8_log(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    log_file = configure_logging(mode="test")
    configure_logging(mode="test")
    logging.getLogger("file_toolbox.test").info("可追查的测试消息")
    _flush_file_handlers()

    assert log_file == tmp_path / ".file_toolbox" / "logs" / "file-toolbox.log"
    assert get_log_file() == log_file
    assert log_file.is_file()
    content = log_file.read_text(encoding="utf-8")
    assert "可追查的测试消息" in content
    assert "mode=test" in content
    handlers = [
        handler
        for handler in logging.getLogger("file_toolbox").handlers
        if isinstance(handler, RotatingFileHandler)
    ]
    assert len(handlers) == 1
    assert handlers[0].backupCount > 0
    assert handlers[0].maxBytes > 0


def test_configure_logging_dedups_startup_line_for_same_file(monkeypatch, tmp_path):
    """gui_entry 与 run_gui 各配置一次,同一日志文件只留一行"应用启动"。"""
    monkeypatch.chdir(tmp_path)

    log_file = configure_logging(mode="test")
    configure_logging(mode="test")
    _flush_file_handlers()

    content = log_file.read_text(encoding="utf-8")
    assert content.count("应用启动") == 1


def test_configure_logging_logs_startup_line_for_each_new_file(monkeypatch, tmp_path):
    """切换日志文件(如测试切换 cwd)时,新文件保留各自的启动行。"""
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()

    monkeypatch.chdir(first)
    first_log = configure_logging(mode="test")
    monkeypatch.chdir(second)
    second_log = configure_logging(mode="test")
    _flush_file_handlers()

    assert first_log.read_text(encoding="utf-8").count("应用启动") == 1
    assert second_log.read_text(encoding="utf-8").count("应用启动") == 1


def test_uncaught_exception_hook_writes_traceback(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    log_file = configure_logging(mode="test")

    try:
        raise RuntimeError("顶层崩溃样本")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    _flush_file_handlers()

    content = log_file.read_text(encoding="utf-8")
    assert "未捕获异常" in content
    assert "RuntimeError: 顶层崩溃样本" in content
