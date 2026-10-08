"""Word/Excel handler 的 COM 资源清理契约测试(Task142 冻结接口)。

聚焦控制流边界(不模拟 Find/Replace 深链式调用):
- read_content: DispatchEx 失败不再吞掉返回空串伪装零匹配——记录日志后原样传播,
  由 preview_replace 逐文件 except 呈现 ❌;COM 配对(CoUninitialize)仍完成。
- read_content 成功且空内容: 仍返回空串(不变)。
- read_content finally: 文档 Close 失败不阻断后续清理——仍 dispose(Quit)且
  同线程 CoUninitialize。
- batch_replace: 空文件列表直接返回零结果(不初始化 COM/不 Dispatch);
  COM 初始化/Dispatch 失败 → 错误入 errors 并返回(不崩)。

mock pythoncom/win32com.client 模块级函数。本机 Windows(pywin32 已装)与
CI Windows runner 上 import 这些模块成功;真 DispatchEx/CoInitialize 被替换为
mock。handler 构造已无参(Task142 删除 PID 回调注入);Quit 断言依赖显式
Documents/Workbooks.Count = 0 假件——dispose_office_app 只 Quit 空集合的
专属应用,不再无条件 Quit。
"""

from unittest.mock import MagicMock

import pytest

from file_toolbox.core.batch_replace.handlers.excel_handler import ExcelHandler
from file_toolbox.core.batch_replace.handlers.word_handler import WordHandler


@pytest.fixture(autouse=True)
def _reset_office_kind_evidence():
    """隔离 EngineManager 类级 kind 证据(Dispatch 成功路径现在会登记)。"""
    from file_toolbox.core.batch_pdf.engine_manager import EngineManager

    EngineManager._cached_kind_probes = None
    EngineManager._verified_kinds = {}
    yield
    EngineManager._cached_kind_probes = None
    EngineManager._verified_kinds = {}


@pytest.fixture
def word_handler() -> WordHandler:
    return WordHandler()


@pytest.fixture
def excel_handler() -> ExcelHandler:
    return ExcelHandler()


def _fake_owned_app(collection: str) -> MagicMock:
    """构造专属应用假件:集合为空(Count=0),满足 dispose 的 Quit 门控。"""
    app = MagicMock()
    getattr(app, collection).Count = 0
    return app


# ===========================================================================
# Dispatch 成功登记进程内 kind 证据(P5 补齐:预览/替换两链)
# ===========================================================================


def test_word_read_content_success_records_kind_evidence(word_handler, monkeypatch, tmp_path):
    """预览读取链:Word Dispatch 成功 → 登记 word/office 证据。"""
    from file_toolbox.core.batch_pdf.engine_manager import EngineManager
    from file_toolbox.core.batch_replace.handlers import word_handler as module

    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    app = _fake_owned_app("Documents")
    monkeypatch.setattr(module, "init_office_app", lambda _pid: app)
    monkeypatch.setattr(module, "open_office_document", lambda *a, **k: MagicMock())
    monkeypatch.setattr(word_handler, "_extract_all_text", lambda _doc: "content")

    assert word_handler.read_content(f) == "content"
    assert EngineManager._verified_kinds == {"word": "office"}


def test_word_batch_replace_success_records_kind_evidence(word_handler, monkeypatch, tmp_path):
    """替换执行链:Word Dispatch 成功即登记证据(与匹配结果无关)。"""
    from file_toolbox.core.batch_pdf.engine_manager import EngineManager
    from file_toolbox.core.batch_replace.handlers import word_handler as module

    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    app = _fake_owned_app("Documents")
    monkeypatch.setattr(module, "init_office_app", lambda _pid: app)
    monkeypatch.setattr(module, "open_office_document", lambda *a, **k: MagicMock())
    monkeypatch.setattr(word_handler, "_extract_all_text", lambda _doc: "no match here")

    result = word_handler.batch_replace(
        [f], [{"type": "simple_replace", "params": {"find": "zzz", "replace": "x"}}]
    )
    assert result["errors"] == []
    assert EngineManager._verified_kinds == {"word": "office"}


def test_excel_read_content_success_records_kind_evidence(excel_handler, monkeypatch, tmp_path):
    """预览读取链:Excel Dispatch 成功 → 登记 excel/office 证据。"""
    from file_toolbox.core.batch_pdf.engine_manager import EngineManager
    from file_toolbox.core.batch_replace.handlers import excel_handler as module

    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    app = _fake_owned_app("Workbooks")
    wb = MagicMock()
    wb.Worksheets = []  # 空表:无匹配,Dispatch 仍成功
    monkeypatch.setattr(module, "init_office_app", lambda _pid: app)
    monkeypatch.setattr(module, "open_office_document", lambda *a, **k: wb)

    assert excel_handler.read_content(f) == ""
    assert EngineManager._verified_kinds == {"excel": "office"}


def test_excel_batch_replace_success_records_kind_evidence(excel_handler, monkeypatch, tmp_path):
    """替换执行链:Excel Dispatch 成功即登记证据(与匹配结果无关)。"""
    from file_toolbox.core.batch_pdf.engine_manager import EngineManager
    from file_toolbox.core.batch_replace.handlers import excel_handler as module

    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    app = _fake_owned_app("Workbooks")
    wb = MagicMock()
    wb.Worksheets = []
    monkeypatch.setattr(module, "init_office_app", lambda _pid: app)
    monkeypatch.setattr(module, "open_office_document", lambda *a, **k: wb)

    result = excel_handler.batch_replace(
        [f], [{"type": "simple_replace", "params": {"find": "zzz", "replace": "x"}}]
    )
    assert result["errors"] == []
    assert EngineManager._verified_kinds == {"excel": "office"}


def _stub_com_modules(
    monkeypatch, *, co_init_raises=False, dispatch_returns=None, dispatch_raises=None
):
    """替换 pythoncom 与 win32com.client 的关键函数。

    - co_init_raises: CoInitialize 抛异常(模拟无 COM 环境;新 ComSession 语义下
      该失败会传播,由 handler 记入 errors)
    - dispatch_returns: DispatchEx 返回的 mock app(成功路径)
    - dispatch_raises: DispatchEx 抛异常
    """
    from file_toolbox.common import office_session as pythoncom

    if co_init_raises:
        monkeypatch.setattr(
            pythoncom, "_initialize_com", lambda: (_ for _ in ()).throw(RuntimeError("no com"))
        )
    co_uninit = MagicMock()
    monkeypatch.setattr(pythoncom, "_uninitialize_com", co_uninit)

    import win32com.client

    if dispatch_raises is not None:
        monkeypatch.setattr(
            win32com.client, "DispatchEx", lambda *a, **k: (_ for _ in ()).throw(dispatch_raises)
        )
    elif dispatch_returns is not None:
        monkeypatch.setattr(win32com.client, "DispatchEx", lambda *a, **k: dispatch_returns)

    return co_uninit


# ===========================================================================
# read_content
# ===========================================================================


def test_word_read_content_propagates_dispatch_failure(word_handler, monkeypatch, tmp_path):
    """DispatchEx 失败 → 异常原样传播(不再吞掉返 ""伪装零匹配),COM 配对仍完成。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    co_uninit = _stub_com_modules(monkeypatch, dispatch_raises=RuntimeError("dispatch boom"))

    with pytest.raises(RuntimeError, match="dispatch boom"):
        word_handler.read_content(f)

    # 清理配对不受影响:CoInitialize 成功过,CoUninitialize 仍被调一次
    co_uninit.assert_called_once()


def test_word_read_content_returns_empty_string_for_empty_document(
    word_handler, monkeypatch, tmp_path
):
    """成功路径但文档无内容 → 仍返回空串(空内容语义不变,与错误传播区分)。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    doc = MagicMock()
    doc.Content.Text = ""  # 空正文(mock 集合默认为空,headers/shapes 无文本)
    app = _fake_owned_app("Documents")
    app.Documents.Open.return_value = doc
    _stub_com_modules(monkeypatch, dispatch_returns=app)

    assert word_handler.read_content(f) == ""
    # 控制流契约:Open 被调用、Close 文档、空集合时 Quit(经 dispose)
    app.Documents.Open.assert_called_once()
    doc.Close.assert_called_once_with(False)
    app.Quit.assert_called_once()


def test_word_read_content_close_failure_still_disposes_and_uninitializes(
    word_handler, monkeypatch, tmp_path
):
    """文档 Close 失败 → 仍先 dispose(Quit)、同线程 CoUninitialize,失败本身不吞掉。

    finally 链保证清理顺序:Close 抛错不阻断 dispose/COM 配对,但错误照常传播,
    由上层预览呈现(不得伪装成空内容/零匹配)。
    """
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    doc = MagicMock()
    doc.Content.Text = "hello"
    doc.Close.side_effect = RuntimeError("close boom")
    app = _fake_owned_app("Documents")
    app.Documents.Open.return_value = doc
    co_uninit = _stub_com_modules(monkeypatch, dispatch_returns=app)

    with pytest.raises(RuntimeError, match="close boom"):
        word_handler.read_content(f)

    # Close 失败不阻断清理链:Quit 与 CoUninitialize 均已完成
    app.Quit.assert_called_once()
    co_uninit.assert_called_once()


# ===========================================================================
# batch_replace: 控制流边界(不进 Find/Replace 深链式)
# ===========================================================================


def test_word_batch_replace_empty_files_no_com(word_handler, monkeypatch):
    """空文件列表 → 直接返回零结果 dict,不触发 CoInitialize/DispatchEx。"""
    co_init = MagicMock()
    from file_toolbox.common import office_session as pythoncom

    monkeypatch.setattr(pythoncom, "_initialize_com", co_init)
    import win32com.client

    dispatch_ex = MagicMock()
    monkeypatch.setattr(win32com.client, "DispatchEx", dispatch_ex)

    result = word_handler.batch_replace([], [])
    assert result == {"success_count": 0, "total_replacements": 0, "errors": []}
    co_init.assert_not_called()
    dispatch_ex.assert_not_called()


def test_word_batch_replace_coinit_failure_records_error(word_handler, monkeypatch, tmp_path):
    """CoInitialize 失败 → 错误入 errors 并返回(不崩,不带出异常)。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    _stub_com_modules(monkeypatch, co_init_raises=True)

    result = word_handler.batch_replace([f], [{"type": "simple_replace", "params": {"find": "x"}}])
    assert result["success_count"] == 0
    assert result["errors"], "COM 初始化失败必须记入 errors 而不是静默"
    assert any("no com" in e for e in result["errors"])


def test_word_batch_replace_dispatch_failure_records_error(word_handler, monkeypatch, tmp_path):
    """DispatchEx 失败 → 错误入 errors;CoInitialize 已成功故 CoUninitialize 仍配对。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"fake")
    co_uninit = _stub_com_modules(monkeypatch, dispatch_raises=RuntimeError("no office"))

    result = word_handler.batch_replace([f], [{"type": "simple_replace", "params": {"find": "x"}}])
    assert result["success_count"] == 0
    assert result["errors"], "应用启动失败必须记入 errors"
    assert any("no office" in e for e in result["errors"])
    # CoInit 成功,Dispatch 失败后 COM 会话仍配对退出
    co_uninit.assert_called_once()


# ===========================================================================
# ExcelHandler:同样的边界契约
# ===========================================================================


def test_excel_read_content_propagates_dispatch_failure(excel_handler, monkeypatch, tmp_path):
    """Excel read_content:DispatchEx 失败 → 异常原样传播(不吞掉返 ""),配对仍完成。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    co_uninit = _stub_com_modules(monkeypatch, dispatch_raises=RuntimeError("dispatch boom"))

    with pytest.raises(RuntimeError, match="dispatch boom"):
        excel_handler.read_content(f)

    co_uninit.assert_called_once()


def test_excel_read_content_returns_text_on_success(excel_handler, monkeypatch, tmp_path):
    """Excel read_content 成功路径:遍历 Worksheets → UsedRange.Value 拼接文本。

    覆盖三种 values 形态:tuple-of-tuples / 单层 tuple(行非 tuple) / 非 tuple 标量。
    """
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")

    # 构造三张表,分别触发三个分支
    sheet_grid = MagicMock()
    sheet_grid.UsedRange.Value = (("a", "b"), ("c", None))  # tuple-of-tuples

    single_row = MagicMock()
    single_row.UsedRange.Value = ("scalar_row",)  # 行非 tuple → elif 分支

    scalar_sheet = MagicMock()
    scalar_sheet.UsedRange.Value = "one_string"  # 非 tuple → else 分支

    app = _fake_owned_app("Workbooks")
    wb = app.Workbooks.Open.return_value
    wb.Worksheets = [sheet_grid, single_row, scalar_sheet]
    _stub_com_modules(monkeypatch, dispatch_returns=app)

    result = excel_handler.read_content(f)
    # tuple-of-tuples: a,b,c(None 跳过); 单层: scalar_row; 标量: one_string
    assert "a" in result and "b" in result and "c" in result
    assert "scalar_row" in result
    assert "one_string" in result
    # 资源清理契约:Close 工作簿(不保存),空集合时 Quit
    app.Workbooks.Open.assert_called_once()
    wb.Close.assert_called_once_with(False)
    app.Quit.assert_called_once()


def test_excel_read_content_empty_used_range(excel_handler, monkeypatch, tmp_path):
    """UsedRange 为 None → 跳过该表,返回空串(不崩)。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")

    sheet = MagicMock()
    sheet.UsedRange = None  # 空 → if used_range is not None 跳过
    app = _fake_owned_app("Workbooks")
    app.Workbooks.Open.return_value.Worksheets = [sheet]
    _stub_com_modules(monkeypatch, dispatch_returns=app)

    assert excel_handler.read_content(f) == ""


def test_excel_read_content_none_values(excel_handler, monkeypatch, tmp_path):
    """UsedRange.Value 为 None → 跳过,返回空串。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")

    sheet = MagicMock()
    sheet.UsedRange.Value = None  # values None → if values is not None 跳过
    app = _fake_owned_app("Workbooks")
    app.Workbooks.Open.return_value.Worksheets = [sheet]
    _stub_com_modules(monkeypatch, dispatch_returns=app)

    assert excel_handler.read_content(f) == ""


def test_excel_batch_replace_empty_files_no_com(excel_handler, monkeypatch):
    """Excel batch_replace:空文件列表 → 零结果,不初始化 COM。"""
    from file_toolbox.common import office_session as pythoncom

    co_init = MagicMock()
    monkeypatch.setattr(pythoncom, "_initialize_com", co_init)

    result = excel_handler.batch_replace([], [])
    assert result == {"success_count": 0, "total_replacements": 0, "errors": []}
    co_init.assert_not_called()


def test_excel_batch_replace_coinit_failure_records_error(excel_handler, monkeypatch, tmp_path):
    """Excel batch_replace:CoInitialize 失败 → 错误入 errors。"""
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"fake")
    _stub_com_modules(monkeypatch, co_init_raises=True)

    result = excel_handler.batch_replace([f], [{"type": "simple_replace", "params": {"find": "x"}}])
    assert result["success_count"] == 0
    assert result["errors"], "COM 初始化失败必须记入 errors 而不是静默"
    assert any("no com" in e for e in result["errors"])
