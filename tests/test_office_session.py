"""common.office_session 单元测试(Task142 冻结接口)。

ComSession / init_office_app / dispose_office_app / open_office_document /
office_document 是纯 COM 基础设施工具,无业务逻辑。用 mock 拦截
pythoncom / win32com.client / gc / time 验证契约:

- ComSession: 同线程配对 CoInitialize/CoUninitialize;CoInitialize/CoUninitialize
  失败直接传播(不再吞掉);同一会话不能重复进入;无 pywin32 时 no-op。
  (跨线程释放的拒绝由 test_office_ownership.py 回归覆盖。)
- init_office_app: 统一 DispatchEx;仅 Word.Application/Excel.Application 这类
  已验证独占实例设置 Visible/DisplayAlerts,PowerPoint/WPS 保守借用不写全局属性;
  属性设置失败时先释放已创建的专属空应用再抛出。
- init_isolated_office_app: 只允许 Word/Excel,复用 init_office_app。
- dispose_office_app(app, prog_id): prog_id 必传;仅专属应用且对应
  Documents/Workbooks.Count == 0 才 Quit;非零计数是清理错误(严格模式抛);
  Quit 异常默认吞、严格模式抛;共享引用不 Quit。
- open_office_document/office_document: 拒绝接管已打开的目标文档;
  finally 只 Close 本次打开的文档;PPT 先 Saved=True 再 Close。
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from file_toolbox.common.office_session import (
    ComSession,
    dispose_office_app,
    init_isolated_office_app,
    init_office_app,
    office_document,
    open_office_document,
)

# ===========================================================================
# ComSession
# ===========================================================================


def _stub_pythoncom(monkeypatch, *, co_init_side_effect=None):
    """替换 pythoncom 模块的 CoInitialize/CoUninitialize,返回两个 mock 便于断言。"""
    from file_toolbox.common import office_session as pythoncom

    co_init = MagicMock()
    if co_init_side_effect is not None:
        co_init.side_effect = co_init_side_effect
    co_uninit = MagicMock()
    monkeypatch.setattr(pythoncom, "_initialize_com", co_init)
    monkeypatch.setattr(pythoncom, "_uninitialize_com", co_uninit)
    return co_init, co_uninit


def test_com_session_enter_initializes_and_returns_self(monkeypatch):
    """__enter__: CoInitialize 被调,返回 session 自身。"""
    co_init, _ = _stub_pythoncom(monkeypatch)

    session = ComSession()
    assert session is session.__enter__()
    co_init.assert_called_once()
    assert session._inited is True


def test_com_session_exit_uninitializes_when_inited(monkeypatch):
    """__exit__: 已 inited → 调 CoUninitialize。"""
    _, co_uninit = _stub_pythoncom(monkeypatch)

    with ComSession():
        pass
    co_uninit.assert_called_once()


def test_com_session_rejects_repeated_enter(monkeypatch):
    """同一会话实例不能重复进入:第二次 __enter__ 抛 RuntimeError。"""
    co_init, _ = _stub_pythoncom(monkeypatch)

    session = ComSession()
    session.__enter__()
    with pytest.raises(RuntimeError, match="不能重复进入"):
        session.__enter__()
    co_init.assert_called_once()  # 第二次进入未再触发 CoInitialize


def test_com_session_coinit_failure_propagates(monkeypatch):
    """CoInitialize 抛异常 → 直接传播(不再 no-op),_inited 保持 False,退出 no-op。"""
    co_init, co_uninit = _stub_pythoncom(monkeypatch, co_init_side_effect=RuntimeError("no com"))

    session = ComSession()
    with pytest.raises(RuntimeError, match="no com"):
        session.__enter__()
    assert session._inited is False
    co_init.assert_called_once()

    session.__exit__(None, None, None)  # 未初始化 → no-op,不抛
    co_uninit.assert_not_called()


def test_com_session_couninit_failure_propagates(monkeypatch):
    """CoUninitialize 抛异常 → 传播给 __exit__ 调用方,但会话标志仍被复位。"""
    _, co_uninit = _stub_pythoncom(monkeypatch)
    co_uninit.side_effect = RuntimeError("uninit boom")

    session = ComSession()
    session.__enter__()
    with pytest.raises(RuntimeError, match="uninit boom"):
        session.__exit__(None, None, None)
    assert session._inited is False  # 复位,避免重复退出


def test_com_session_context_manager_protocol(monkeypatch):
    """完整 with 语句:enter → body → exit,CoInitialize/CoUninitialize 各调一次。"""
    co_init, co_uninit = _stub_pythoncom(monkeypatch)

    with ComSession() as session:
        assert isinstance(session, ComSession)

    co_init.assert_called_once()
    co_uninit.assert_called_once()


def test_com_session_exit_resets_inited_flag(monkeypatch):
    """__exit__ 后 _inited 复位为 False(避免重复退出)。"""
    _stub_pythoncom(monkeypatch)

    session = ComSession()
    session.__enter__()
    assert session._inited is True
    session.__exit__(None, None, None)
    assert session._inited is False


def test_com_session_without_pythoncom_is_noop(monkeypatch):
    """无 pywin32(ImportError)→ 会话 no-op:enter 返回 self 且不标记已初始化。"""
    monkeypatch.setitem(sys.modules, "pythoncom", None)  # None 条目使 import 抛 ImportError

    session = ComSession()
    assert session.__enter__() is session
    assert session._inited is False
    session.__exit__(None, None, None)  # 不应抛


# ===========================================================================
# init_office_app / init_isolated_office_app
# ===========================================================================


def _stub_dispatch_ex(monkeypatch, *, return_value=None, side_effect=None):
    """替换 win32com.client.DispatchEx,返回 mock 便于断言调用次数与参数。"""
    import win32com.client

    dispatch_ex = MagicMock()
    if side_effect is not None:
        dispatch_ex.side_effect = side_effect
    elif return_value is not None:
        dispatch_ex.return_value = return_value
    monkeypatch.setattr(win32com.client, "DispatchEx", dispatch_ex)
    return dispatch_ex


@pytest.mark.parametrize(
    ("prog_id", "collection"),
    [("Word.Application", "Documents"), ("Excel.Application", "Workbooks")],
)
def test_init_office_app_dispatches_ex_and_sets_owned_properties(monkeypatch, prog_id, collection):
    """专属应用(Word/Excel):DispatchEx(prog_id) + Visible=False + DisplayAlerts=False。"""
    app = MagicMock()
    getattr(app, collection).Count = 0
    dispatch_ex = _stub_dispatch_ex(monkeypatch, return_value=app)

    assert init_office_app(prog_id) is app
    dispatch_ex.assert_called_once_with(prog_id)
    assert app.Visible is False
    assert app.DisplayAlerts is False


@pytest.mark.parametrize("prog_id", ["PowerPoint.Application", "KWPS.Application"])
def test_init_office_app_borrows_shared_apps_without_property_writes(monkeypatch, prog_id):
    """共享应用(PPT/WPS)保守借用:仍 DispatchEx,但不写 Visible/DisplayAlerts。

    用属性身份比较验证未被赋值(对 MagicMock 直接赋值会重绑定属性、丢失原子 mock)。
    """
    app = MagicMock()
    _stub_dispatch_ex(monkeypatch, return_value=app)
    visible_before = app.Visible
    display_before = app.DisplayAlerts

    assert init_office_app(prog_id) is app
    assert app.Visible is visible_before, "共享应用不得改写全局 Visible"
    assert app.DisplayAlerts is display_before, "共享应用不得改写全局 DisplayAlerts"


def test_init_office_app_does_not_set_screen_updating(monkeypatch):
    """init_office_app 不设 ScreenUpdating(那是调用方业务)——验证 ScreenUpdating 未被赋值。"""
    app = MagicMock()
    _stub_dispatch_ex(monkeypatch, return_value=app)

    screen_updating_before = app.ScreenUpdating

    init_office_app("Excel.Application")

    assert app.ScreenUpdating is screen_updating_before, (
        "init_office_app 必须不赋值 ScreenUpdating(那是调用方业务)"
    )


def test_init_office_app_property_failure_releases_created_app(monkeypatch):
    """专属应用属性设置失败 → 必须先 Quit 已创建的空应用再抛出(不留孤儿进程)。"""

    class _PropertyBoomApp:
        def __init__(self) -> None:
            self.Documents = SimpleNamespace(Count=0)
            self.quit_calls: list[int] = []

        def __setattr__(self, name: str, value: object) -> None:
            if name == "Visible":
                raise RuntimeError("visible boom")
            super().__setattr__(name, value)

        def Quit(self) -> None:
            self.quit_calls.append(1)

    app = _PropertyBoomApp()
    _stub_dispatch_ex(monkeypatch, return_value=app)

    with pytest.raises(RuntimeError, match="visible boom"):
        init_office_app("Word.Application")

    assert app.quit_calls == [1]  # 已创建的专属空应用被释放


def test_init_isolated_office_app_reuses_init_office_app(monkeypatch):
    """隔离初始化复用 init_office_app:DispatchEx + 专属属性设置。"""
    app = MagicMock()
    app.Documents.Count = 0
    dispatch_ex = _stub_dispatch_ex(monkeypatch, return_value=app)

    assert init_isolated_office_app("Excel.Application") is app
    dispatch_ex.assert_called_once_with("Excel.Application")
    assert app.Visible is False
    assert app.DisplayAlerts is False


@pytest.mark.parametrize("prog_id", ["PowerPoint.Application", "KWPS.Application"])
def test_init_isolated_office_app_rejects_unverified_engines(prog_id):
    """隔离初始化只允许已验证独占语义的 Microsoft Word/Excel,其余抛 ValueError。"""
    with pytest.raises(ValueError, match="未验证"):
        init_isolated_office_app(prog_id)


# ===========================================================================
# dispose_office_app
# ===========================================================================


def test_dispose_office_app_none_is_noop(monkeypatch):
    """app=None → no-op,不触碰 gc.collect。"""
    import gc

    gc_collect = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)

    dispose_office_app(None, "Word.Application")

    gc_collect.assert_not_called()


def test_dispose_office_app_quits_empty_owned_app_and_collects(monkeypatch):
    """Word 且 Documents.Count==0 → Quit + gc.collect;gc_pause=0 时不 sleep。"""
    import gc
    import time

    gc_collect = MagicMock()
    sleep = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)
    monkeypatch.setattr(time, "sleep", sleep)

    app = MagicMock()
    app.Documents.Count = 0

    dispose_office_app(app, "Word.Application")

    app.Quit.assert_called_once_with()
    gc_collect.assert_called_once_with()
    sleep.assert_not_called()


@pytest.mark.parametrize(
    ("prog_id", "collection"),
    [("Word.Application", "Documents"), ("Excel.Application", "Workbooks")],
)
def test_dispose_office_app_keeps_session_when_documents_open(monkeypatch, prog_id, collection):
    """专属应用仍有未关闭文档(Count != 0)→ 不 Quit;严格模式视为清理错误抛出。"""
    app = MagicMock()
    getattr(app, collection).Count = 2

    dispose_office_app(app, prog_id)  # 默认吞掉,不抛
    app.Quit.assert_not_called()

    with pytest.raises(RuntimeError, match="未关闭文档"):
        dispose_office_app(app, prog_id, raise_on_error=True)
    app.Quit.assert_not_called()


def test_dispose_office_app_quit_exception_swallowed(monkeypatch):
    """Quit 抛异常 → 默认被 suppress(进程可能已退出),gc.collect 仍执行。"""
    import gc

    gc_collect = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)

    app = MagicMock()
    app.Documents.Count = 0
    app.Quit.side_effect = RuntimeError("already gone")

    dispose_office_app(app, "Word.Application")  # 不应抛

    app.Quit.assert_called_once_with()
    gc_collect.assert_called_once_with()


def test_dispose_office_app_can_propagate_quit_failure_after_gc(monkeypatch):
    """严格调用方可让 Quit 失败阻止后续文件晋升，且仍先执行 gc。"""
    import gc

    gc_collect = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)
    app = MagicMock()
    app.Workbooks.Count = 0
    app.Quit.side_effect = RuntimeError("Excel busy")

    with pytest.raises(RuntimeError, match="关闭 Office 应用失败"):
        dispose_office_app(app, "Excel.Application", raise_on_error=True)

    app.Quit.assert_called_once_with()
    gc_collect.assert_called_once_with()


def test_dispose_office_app_with_gc_pause_sleeps_after_collect(monkeypatch):
    """gc_pause > 0 → gc.collect 后 time.sleep(gc_pause)(时序:gc 在前,sleep 在后)。"""
    import gc
    import time

    gc_collect = MagicMock()
    sleep = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)
    monkeypatch.setattr(time, "sleep", sleep)

    app = MagicMock()
    app.Documents.Count = 0

    dispose_office_app(app, "Word.Application", gc_pause=0.3)

    app.Quit.assert_called_once_with()
    gc_collect.assert_called_once_with()
    sleep.assert_called_once_with(0.3)


@pytest.mark.parametrize("prog_id", ["PowerPoint.Application", "KWPS.Application"])
def test_dispose_office_app_never_quits_shared_apps(monkeypatch, prog_id):
    """共享引用(PPT/WPS)只由调用方释放:即便集合为空也不 Quit。"""
    import gc

    gc_collect = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)

    app = MagicMock()
    app.Presentations.Count = 0

    dispose_office_app(app, prog_id)

    app.Quit.assert_not_called()
    gc_collect.assert_called_once_with()  # 引用回收仍执行,只是不碰应用生命周期


# ===========================================================================
# open_office_document / office_document
# ===========================================================================


def test_open_office_document_forwards_args_to_collection_open(tmp_path):
    """Open 参数原样透传(PPT 转换器的 ReadOnly/Untitled/WithWindow 三参)。"""
    path = tmp_path / "a.pptx"
    path.write_bytes(b"x")
    app = MagicMock()
    presentation = MagicMock()
    app.Presentations.Open.return_value = presentation

    assert open_office_document(app, "Presentations", path, True, True, False) is presentation
    app.Presentations.Open.assert_called_once_with(str(path.absolute()), True, True, False)


def test_open_office_document_rejects_already_open_target(tmp_path):
    """目标文档已在集合中打开(FullName 相同)→ 拒绝接管,不再触发第二次 Open。"""
    target = tmp_path / "a.docx"
    target.write_bytes(b"x")
    app = MagicMock()
    opened = MagicMock()
    opened.FullName = str(target)
    app.Documents.__iter__.return_value = iter([opened])

    with pytest.raises(RuntimeError, match="不能接管"):
        open_office_document(app, "Documents", target)

    app.Documents.Open.assert_not_called()


def test_open_office_document_allows_other_documents_open(tmp_path):
    """集合中已打开的是其它文档 → 正常 Open 本次目标。"""
    target = tmp_path / "a.docx"
    target.write_bytes(b"x")
    other = tmp_path / "other.docx"
    other.write_bytes(b"x")
    app = MagicMock()
    opened = MagicMock()
    opened.FullName = str(other)
    app.Documents.__iter__.return_value = iter([opened])
    doc = MagicMock()
    app.Documents.Open.return_value = doc

    assert open_office_document(app, "Documents", target) is doc
    app.Documents.Open.assert_called_once_with(str(target.absolute()))


def test_office_document_closes_word_doc_without_saving(tmp_path):
    """Word/Excel 文档:退出 with 时 Close(False),不保存本次排版。"""
    path = tmp_path / "a.docx"
    path.write_bytes(b"x")
    app = MagicMock()
    doc = MagicMock()
    app.Documents.Open.return_value = doc

    with office_document(app, "Documents", path) as received:
        assert received is doc

    doc.Close.assert_called_once_with(False)


def test_office_document_marks_presentation_saved_before_close(tmp_path):
    """PPT:Close 前必须置 Saved=True(丢弃内存排版,不触发保存对话框/写原文件)。"""
    path = tmp_path / "a.pptx"
    path.write_bytes(b"x")
    app = MagicMock()
    presentation = MagicMock()
    app.Presentations.Open.return_value = presentation

    def close_requires_saved(*args, **kwargs):
        assert presentation.Saved is True, "PPT 必须先置 Saved=True 再 Close"

    presentation.Close.side_effect = close_requires_saved

    with office_document(app, "Presentations", path, True, True, False):
        pass

    presentation.Close.assert_called_once_with()


def test_office_document_closes_doc_and_reraises_body_error(tmp_path):
    """body 抛异常 → 先 Close 本次文档,再原样抛出业务错误。"""
    path = tmp_path / "a.docx"
    path.write_bytes(b"x")
    app = MagicMock()
    doc = MagicMock()
    app.Documents.Open.return_value = doc

    with (
        pytest.raises(ValueError, match="boom"),
        office_document(app, "Documents", path),
    ):
        raise ValueError("boom")

    doc.Close.assert_called_once_with(False)


def test_office_document_reports_close_failure_after_body_error(tmp_path):
    """body 错误 + Close 失败 → 合并为 RuntimeError,原始错误保留为 __cause__。"""
    path = tmp_path / "a.docx"
    path.write_bytes(b"x")
    app = MagicMock()
    doc = MagicMock()
    doc.Close.side_effect = RuntimeError("close boom")
    app.Documents.Open.return_value = doc

    with (
        pytest.raises(RuntimeError, match="关闭 Office 文档失败") as exc_info,
        office_document(app, "Documents", path),
    ):
        raise ValueError("boom")

    assert isinstance(exc_info.value.__cause__, ValueError)
