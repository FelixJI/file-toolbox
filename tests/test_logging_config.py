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


def test_gui_entry_startup_trace_logged_when_run_as_main(monkeypatch, tmp_path):
    """gui_entry 以 __main__ 执行时启动留痕必须落在 file_toolbox 日志树。

    python -m file_toolbox.gui_entry 与 PyInstaller 入口脚本都以 __main__ 执行
    gui_entry,若用 __name__ 取 logger 则挂在 root 下、文件 handler 收不到,
    启动卡死诊断留痕(GUI 入口/模块导入)会静默丢失。
    """

    import runpy

    import file_toolbox.common.logging_config as logging_config
    import file_toolbox.gui.main_window as main_window

    # 隔离:main() 内延迟导入引用同一模块对象,patch 生效;真实 GUI 不启动。
    monkeypatch.setattr(logging_config, "configure_logging", lambda *, mode: tmp_path / "log")
    monkeypatch.setattr(main_window, "run_gui", lambda: None)

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    app_logger = logging.getLogger("file_toolbox")
    capture = _Capture()
    monkeypatch.setattr(app_logger, "level", logging.DEBUG)
    app_logger.addHandler(capture)
    try:
        runpy.run_module("file_toolbox.gui_entry", run_name="__main__")
    finally:
        app_logger.removeHandler(capture)

    messages = [r.getMessage() for r in records if r.name == "file_toolbox.gui_entry"]
    assert any("GUI 入口" in m for m in messages)
    assert any("GUI 模块导入完成" in m for m in messages)
