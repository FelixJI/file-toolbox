"""Word/Excel handler 的 COM 资源清理契约测试。

聚焦控制流边界(不模拟 Find/Replace 深链式调用):
- read_content:Dispatch 异常时 finally 仍 Quit/CoUninitialize,返回 ""
- batch_replace:空文件列表直接返回零结果(不 Dispatch)
- batch_replace:CoInitialize 失败 → 错误入 errors 并返回(不崩)
- batch_replace:Dispatch 失败 → 错误入 errors,finally 清理

mock pythoncom/win32com.client 模块级函数。本机 Windows(pywin32 已装)与
CI Windows runner 上 import 这些模块成功;真 Dispatch/CoInitialize 被替换为 mock。
"""

from unittest.mock import MagicMock

import pytest

from file_toolbox.core.batch_replace.handlers.excel_handler import ExcelHandler
from file_toolbox.core.batch_replace.handlers.word_handler import WordHandler


def _noop_pids(_name: str) -> list[int]:
    return []


def _noop_kill(_name: str, _pids: list[int]) -> None:
    return None


@pytest.fixture
def word_handler() -> WordHandler:
    return WordHandler(_noop_pids, _noop_kill)


@pytest.fixture
def excel_handler() -> ExcelHandler:
    return ExcelHandler(_noop_pids, _noop_kill)


def _stub_com_modules(
    monkeypatch, *, co_init_raises=False, dispatch_returns=None, dispatch_raises=None
):
    """替换 pythoncom 与 win32com.client 的关键函数。

    - co_init_raises: CoInitialize 抛异常(模拟无 COM 环境)
    - dispatch_returns: Dispatch 返回的 mock app(成功路径)
    - dispatch_raises: Dispatch 抛异常
    """
    import pythoncom

    if co_init_raises:
        monkeypatch.setattr(
            pythoncom, "CoInitialize", lambda: (_ for _ in ()).throw(RuntimeError("no com"))
        )
    co_uninit = MagicMock()
    monkeypatch.setattr(pythoncom, "CoUninitialize", co_uninit)

    import win32com.client

    if dispatch_raises is not None:
        monkeypatch.setattr(
            win32com.client, "Dispatch", lambda *a, **k: (_ for _ in ()).throw(dispatch_raises)
        )
    elif dispatch_returns is not None:
        monkeypatch.setattr(win32com.client, "Dispatch", lambda *a, **k: dispatch_returns)

    return co_uninit


# ===========================================================================
# read_content
# ===========================================================================


def test_word_read_content_returns_empty_on_dispatch_failure(word_handler, monkeypatch, tmp_path):
    """Dispatch 抛异常 → finally 清理(CoUninitialize 仍调用),返回 ""。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    _stub_com_modules(monkeypatch, dispatch_raises=RuntimeError("dispatch boom"))
    assert word_handler.read_content(f) == ""


def test_word_read_content_returns_empty_string_when_doc_empty(word_handler, monkeypatch, tmp_path):
    """成功路径但文档无文本 → _extract_all_text 返回空串(Quit/Close 被调用)。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    doc = MagicMock()
    doc.Content.Text = ""  # 空正文
    app = MagicMock()
    app.Documents.Open.return_value = doc
    _stub_com_modules(monkeypatch, dispatch_returns=app)

    result = word_handler.read_content(f)
    # _extract_all_text 拼接 Content.Text + headers/shapes(MagicMock 自动产生非空串)
    assert isinstance(result, str)
    # 控制流契约:Open 被调用、Close/Quit 被调用(资源清理)
    app.Documents.Open.assert_called_once()
    doc.Close.assert_called()
    app.Quit.assert_called()


# ===========================================================================
# batch_replace: 控制流边界(不进 Find/Replace 深链式)
# ===========================================================================


def test_word_batch_replace_empty_files_no_dispatch(word_handler, monkeypatch):
    """空文件列表 → 直接返回零结果 dict,不触发 CoInitialize/Dispatch。"""
    co_init = MagicMock()
    import pythoncom

    monkeypatch.setattr(pythoncom, "CoInitialize", co_init)
    import win32com.client

    dispatch = MagicMock()
    monkeypatch.setattr(win32com.client, "Dispatch", dispatch)

    result = word_handler.batch_replace([], [])
    assert result == {"success_count": 0, "total_replacements": 0, "errors": []}
    co_init.assert_not_called()
    dispatch.assert_not_called()


def test_word_batch_replace_coinit_failure_records_error(word_handler, monkeypatch, tmp_path):
    """CoInitialize 失败 → 错误入 errors 并返回,不崩。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    _stub_com_modules(monkeypatch, co_init_raises=True)

    result = word_handler.batch_replace([f], [{"type": "simple_replace", "params": {"find": "x"}}])
    assert result["success_count"] == 0
    assert any("COM初始化失败" in e for e in result["errors"])


def test_word_batch_replace_dispatch_failure_records_error(word_handler, monkeypatch, tmp_path):
    """Dispatch 失败 → 错误入 errors;CoInitialize 已成功故 finally 仍 CoUninitialize。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    co_uninit = _stub_com_modules(monkeypatch, dispatch_raises=RuntimeError("no office"))

    result = word_handler.batch_replace([f], [{"type": "simple_replace", "params": {"find": "x"}}])
    assert result["success_count"] == 0
    assert any("无法启动Word应用程序" in e for e in result["errors"])
    # CoInit 成功(com_initialized=True),Dispatch 失败后 finally 仍 CoUninitialize
    co_uninit.assert_called_once()


# ===========================================================================
# ExcelHandler:同样的边界契约
# ===========================================================================


def test_excel_read_content_returns_empty_on_dispatch_failure(excel_handler, monkeypatch, tmp_path):
    """Excel read_content:Dispatch 失败 → 返回 ""。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    _stub_com_modules(monkeypatch, dispatch_raises=RuntimeError("dispatch boom"))
    assert excel_handler.read_content(f) == ""


def test_excel_batch_replace_empty_files_no_dispatch(excel_handler, monkeypatch):
    """Excel batch_replace:空文件列表 → 零结果,不 Dispatch。"""
    import pythoncom

    co_init = MagicMock()
    monkeypatch.setattr(pythoncom, "CoInitialize", co_init)

    result = excel_handler.batch_replace([], [])
    assert result == {"success_count": 0, "total_replacements": 0, "errors": []}
    co_init.assert_not_called()


def test_excel_batch_replace_coinit_failure_records_error(excel_handler, monkeypatch, tmp_path):
    """Excel batch_replace:CoInitialize 失败 → 错误入 errors。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    _stub_com_modules(monkeypatch, co_init_raises=True)

    result = excel_handler.batch_replace([f], [{"type": "simple_replace", "params": {"find": "x"}}])
    assert any("COM初始化失败" in e for e in result["errors"])
