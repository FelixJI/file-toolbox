"""cli/main.py 未覆盖分支补充测试。

覆盖行:
- 26-33: gui 命令(ImportError 分支 + run_gui 调用)
- 58-72: main() 入口(OpParseError → SystemExit(1);typer.Exit → SystemExit(exit_code))
- 75-76: __main__ 块(pragma,不测)
"""

import pytest
from typer.testing import CliRunner

from file_toolbox import __version__
from file_toolbox.cli import main as main_mod
from file_toolbox.cli.main import app, main

runner = CliRunner()


# ---------------------------------------------------------------------------
# gui 命令(行 26-33)
# ---------------------------------------------------------------------------


def test_gui_command_import_error(monkeypatch):
    """GUI 依赖缺失 → ImportError → 红字提示 + Exit(1)(行 28-32)。"""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "file_toolbox.gui.main_window":
            raise ImportError("no PySide6")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    r = runner.invoke(app, ["gui"])
    assert r.exit_code == 1
    assert "GUI 不可用" in r.output


def test_gui_command_runs(monkeypatch):
    """GUI 可用 → 调用 run_gui(行 26-27, 33)。mock run_gui 避免真起窗口。"""
    called = {"n": 0}

    def fake_run_gui():
        called["n"] += 1

    # 注入一个可被 import 的假模块
    import sys
    import types

    fake_mod = types.ModuleType("file_toolbox.gui.main_window")
    fake_mod.run_gui = fake_run_gui
    monkeypatch.setitem(sys.modules, "file_toolbox.gui.main_window", fake_mod)

    r = runner.invoke(app, ["gui"])
    assert r.exit_code == 0
    assert called["n"] == 1


# ---------------------------------------------------------------------------
# main() 入口(行 58-72)
# ---------------------------------------------------------------------------


def test_main_op_parse_error_exits_1(monkeypatch):
    """main():OpParseError → '错误:...' + SystemExit(1)(行 67-69)。"""
    from file_toolbox.cli.op_parser import OpParseError

    def boom(*a, **k):
        raise OpParseError("解析失败")

    monkeypatch.setattr(main_mod, "app", boom)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_main_typer_exit_propagates_exit_code(monkeypatch):
    """main():typer.Exit → SystemExit(exit_code)(行 70-72)。"""
    import typer

    def boom(*a, **k):
        raise typer.Exit(42)

    monkeypatch.setattr(main_mod, "app", boom)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 42


def test_main_normal_completion_exit_zero(monkeypatch):
    """main():正常完成(无异常)→ 不抛 SystemExit。"""
    monkeypatch.setattr(main_mod, "app", lambda *a, **k: None)
    # 不应抛异常
    main()


# ---------------------------------------------------------------------------
# version flag(行 50-52,已有 test_version,补确认 main_callback 路径)
# ---------------------------------------------------------------------------


def test_main_callback_version_prints_and_exits():
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0
    assert __version__ in r.output
