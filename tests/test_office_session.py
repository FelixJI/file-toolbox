"""common.office_session 单元测试。

ComSession / init_office_app / dispose_office_app 是纯 COM 基础设施工具,
无业务逻辑。用 mock 拦截 pythoncom / win32com.client / gc / time 验证契约:

- ComSession: 成功时 __enter__ 调 CoInitialize 并返回 self;__exit__ 调 CoUninitialize;
  CoInitialize 抛异常时进入 no-op(_inited=False),__exit__ 不调 CoUninitialize。
- init_office_app: Dispatch(prog_id) + 设 Visible=False / DisplayAlerts=False。
- dispose_office_app: None 时 no-op;Quit 异常被吞;gc.collect 被调;gc_pause>0 时 sleep。
"""

from unittest.mock import MagicMock

import pytest

from file_toolbox.common.office_session import (
    ComSession,
    dispose_office_app,
    init_isolated_office_app,
    init_office_app,
)

# ===========================================================================
# ComSession
# ===========================================================================


def _stub_pythoncom(monkeypatch, *, co_init_side_effect=None):
    """替换 pythoncom 模块的 CoInitialize/CoUninitialize,返回两个 mock 便于断言。"""
    import pythoncom

    co_init = MagicMock()
    if co_init_side_effect is not None:
        co_init.side_effect = co_init_side_effect
    co_uninit = MagicMock()
    monkeypatch.setattr(pythoncom, "CoInitialize", co_init)
    monkeypatch.setattr(pythoncom, "CoUninitialize", co_uninit)
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


def test_com_session_init_failure_is_noop(monkeypatch):
    """CoInitialize 抛异常 → _inited=False,__exit__ 不调 CoUninitialize(非 Windows 路径)。"""
    co_init, co_uninit = _stub_pythoncom(monkeypatch, co_init_side_effect=RuntimeError("no com"))

    session = ComSession()
    session.__enter__()
    assert session._inited is False
    co_init.assert_called_once()

    session.__exit__(None, None, None)
    co_uninit.assert_not_called()


def test_com_session_exit_suppresses_couninit_exception(monkeypatch):
    """CoUninitialize 抛异常 → 被 suppress,不向 __exit__ 调用方传播。"""
    _, co_uninit = _stub_pythoncom(monkeypatch)
    co_uninit.side_effect = RuntimeError("uninit boom")

    # 不应抛(__exit__ 内 with suppress)
    with ComSession():
        pass


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


# ===========================================================================
# init_office_app
# ===========================================================================


def test_init_office_app_dispatches_and_sets_properties(monkeypatch):
    """init_office_app: Dispatch(prog_id) + Visible=False + DisplayAlerts=False,返回 app。"""
    import win32com.client

    app = MagicMock()
    dispatch = MagicMock(return_value=app)
    monkeypatch.setattr(win32com.client, "Dispatch", dispatch)

    result = init_office_app("Word.Application")

    assert result is app
    dispatch.assert_called_once_with("Word.Application")
    assert app.Visible is False
    assert app.DisplayAlerts is False


def test_init_office_app_does_not_set_screen_updating(monkeypatch):
    """init_office_app 不设 ScreenUpdating(那是调用方业务)——验证 ScreenUpdating 未被赋值。"""
    import win32com.client

    app = MagicMock()
    monkeypatch.setattr(win32com.client, "Dispatch", MagicMock(return_value=app))

    # 在调用前捕获 ScreenUpdating 自动子 mock 的身份。若 init_office_app 执行了
    # ``app.ScreenUpdating = False``,该属性会被重绑定为布尔 False(不再指向原子 mock),
    # 身份比较即失败。注意:对 MagicMock 直接赋值不会经过 mock_calls,故必须用身份比较。
    screen_updating_before = app.ScreenUpdating

    init_office_app("Excel.Application")

    assert app.ScreenUpdating is screen_updating_before, (
        "init_office_app 必须不赋值 ScreenUpdating(那是调用方业务)"
    )


def test_init_isolated_office_app_uses_dispatch_ex(monkeypatch):
    """考勤等一次性任务使用 DispatchEx，不附着用户已有 Office 会话。"""
    import win32com.client

    app = MagicMock()
    dispatch_ex = MagicMock(return_value=app)
    monkeypatch.setattr(win32com.client, "DispatchEx", dispatch_ex)

    result = init_isolated_office_app("Excel.Application")

    assert result is app
    dispatch_ex.assert_called_once_with("Excel.Application")
    assert app.Visible is False
    assert app.DisplayAlerts is False


# ===========================================================================
# dispose_office_app
# ===========================================================================


def test_dispose_office_app_none_is_noop(monkeypatch):
    """app=None → no-op,不触碰 gc.collect。"""
    import gc

    gc_collect = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)

    dispose_office_app(None)

    gc_collect.assert_not_called()


def test_dispose_office_app_quits_and_collects(monkeypatch):
    """非 None app → Quit + gc.collect;gc_pause=0 时不 sleep。"""
    import gc
    import time

    gc_collect = MagicMock()
    sleep = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)
    monkeypatch.setattr(time, "sleep", sleep)

    app = MagicMock()
    dispose_office_app(app)

    app.Quit.assert_called_once_with()
    gc_collect.assert_called_once_with()
    sleep.assert_not_called()


def test_dispose_office_app_quit_exception_swallowed(monkeypatch):
    """Quit 抛异常 → 被 suppress(进程可能已退出),gc.collect 仍执行。"""
    import gc

    gc_collect = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)

    app = MagicMock()
    app.Quit.side_effect = RuntimeError("already gone")

    dispose_office_app(app)  # 不应抛

    app.Quit.assert_called_once_with()
    gc_collect.assert_called_once_with()


def test_dispose_office_app_can_propagate_quit_failure_after_gc(monkeypatch):
    """严格调用方可让 Quit 失败阻止后续文件晋升，且仍先执行 gc。"""
    import gc

    gc_collect = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)
    app = MagicMock()
    app.Quit.side_effect = RuntimeError("Excel busy")

    with pytest.raises(RuntimeError, match="关闭 Office 应用失败"):
        dispose_office_app(app, raise_on_error=True)

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
    dispose_office_app(app, gc_pause=0.3)

    app.Quit.assert_called_once_with()
    gc_collect.assert_called_once_with()
    sleep.assert_called_once_with(0.3)
