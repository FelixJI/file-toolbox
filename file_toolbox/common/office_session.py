"""Office COM 会话基础设施。

提供线程级的 CoInitialize/CoUninitialize 配对上下文管理器,以及通用的
Office app 初始化/释放辅助(Dispatch + Visible/DisplayAlerts 设置、Quit + gc)。
供 batch_pdf(EngineManager)与 batch_replace(handlers)共用,消除重复的 COM 典礼。

设计要点:
- ``ComSession`` 只管「使用 win32com 的线程先 CoInitialize、用完 CoUninitialize'',
  **不缓存 COM app 实例**——STA 绑定下 COM 应用绑定创建它的线程,跨线程复用会失效,
  故本类只跟踪本线程的 CoInit 状态(线程局部),由调用方各自管理 app 生命周期。
- ``init_office_app`` 抽自 ``EngineManager._init_office_app`` 的最内层 Dispatch+属性设置,
  但不持有/缓存 app:EngineManager 缓存实例,replace handlers 每批建/释放。
- ``dispose_office_app`` 是「Quit + gc.collect(+可选 sleep)」的最通用形态,供批末清理。
- **进程退出安全**:`dispose_office_app` 始终走 gc.collect;真正需要在 GC 链中跳过 gc 的
  场景(如 ``EngineManager.close(_from_del=True)``)保留各自的 ``_from_del`` 守卫逻辑,
  不下沉到此处——本模块是无状态工具,不理解「是否处于 __del__ 链」这种业务上下文。

这些辅助是**无状态工具**:超时重启(Quit→gc→sleep0.5→kill→sleep0.5→重 Dispatch)、
PID 清理、ScreenUpdating 等 replace 侧业务逻辑**不在本模块**,保留在各 handler。
"""

from __future__ import annotations

import contextlib
import gc
import time
from typing import Any


class ComSession:
    """线程级 COM 初始化上下文。

    用法::

        with ComSession():
            # 本线程内可安全 win32com.client.Dispatch
            ...

    非 Windows / 无 pywin32 时进入为 no-op(不抛),退出无操作。这样调用方
    (handlers / worker)无需在调用前判断平台——CoInit 失败即视为「无 COM 环境」。
    """

    def __init__(self) -> None:
        self._inited = False

    def __enter__(self) -> ComSession:
        try:
            import pythoncom

            pythoncom.CoInitialize()
            self._inited = True
        except Exception:
            self._inited = False  # 非 Windows / 无 pywin32
        return self

    def __exit__(self, *exc: object) -> None:
        if self._inited:
            with contextlib.suppress(Exception):
                import pythoncom

                pythoncom.CoUninitialize()
        self._inited = False


def init_office_app(prog_id: str) -> Any:
    """Dispatch 一个 Office app 并设置常用属性(Visible/DisplayAlerts=False)。

    调用方负责 CoInitialize(用 ``ComSession``)与 Quit(批末)。
    prog_id 例:``'Word.Application'`` / ``'Excel.Application'`` / ``'PowerPoint.Application'``。

    与原 ``EngineManager._init_office_app`` 的最内层逻辑等价:
    ``Dispatch(prog_id)`` → ``Visible=False`` → ``DisplayAlerts=False``。
    不设 ``ScreenUpdating``——那是 replace batch_replace 的业务优化(减少屏幕刷新),
    由调用方在需要时单独设置。
    """
    import win32com.client

    app = win32com.client.Dispatch(prog_id)
    app.Visible = False
    app.DisplayAlerts = False
    return app


def init_isolated_office_app(prog_id: str) -> Any:
    """用 DispatchEx 创建不附着用户现有会话的 Office app。"""
    import win32com.client

    dispatch_ex: Any = win32com.client.DispatchEx
    app = dispatch_ex(prog_id)
    app.Visible = False
    app.DisplayAlerts = False
    return app


def dispose_office_app(
    app: Any | None, *, gc_pause: float = 0.0, raise_on_error: bool = False
) -> None:
    """安全 Quit 一个 Office app 并触发 gc(批末清理用)。

    - app 为 None 时 no-op。
    - 默认吞掉 Quit 失败；``raise_on_error=True`` 时完成 gc 后抛出。
    - 始终 ``gc.collect()`` 释放 COM 对象;``gc_pause > 0`` 时 gc 后再 sleep,用于
      批间彻底释放(与原 ``Quit→gc.collect→time.sleep`` 时序一致:gc 在前,sleep 在后)。

    注意:**不在此处 kill 残留进程**——PID 清理是 replace 侧业务(依赖批前快照 PID),
    保留在 handlers。本函数只管单个 app 对象的「软」清理。
    """
    if app is None:
        return
    quit_error: Exception | None = None
    try:
        app.Quit()
    except Exception as exc:  # COM 已断开/进程已退出
        quit_error = exc
    gc.collect()
    if gc_pause > 0:
        time.sleep(gc_pause)
    if quit_error is not None and raise_on_error:
        raise RuntimeError(f"关闭 Office 应用失败: {quit_error}") from quit_error
