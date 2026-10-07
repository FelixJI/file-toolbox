"""COM 线程配对与 Office 任务资源边界。

Word/Excel 的独立实例已经过真实 Windows 验证。PowerPoint 是 MultiUse，
WPS 的隔离能力不作假设：借用其应用时不修改全局属性，也不调用 Quit。
文档仅接管本次 Open 返回且此前未打开的目标；所有调用仍是协作式、可能阻塞。
"""

from __future__ import annotations

import contextlib
import gc
import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal, cast

# Microsoft SingleUse 应用；不要把 DispatchEx 等同于所有引擎都独占进程。
_OWNED_APPLICATIONS = {"Word.Application": "Documents", "Excel.Application": "Workbooks"}
DocumentCollection = Literal["Documents", "Workbooks", "Presentations"]


def _initialize_com() -> None:
    # pywin32 的主初始化线程不累计嵌套计数；直接调用系统 API 才能成对释放。
    import ctypes

    import pythoncom

    ole32 = ctypes.OleDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoInitializeEx(None, pythoncom.COINIT_APARTMENTTHREADED)


def _uninitialize_com() -> None:
    import ctypes

    ole32 = ctypes.WinDLL("ole32")
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoUninitialize()


class ComSession:
    """在同一线程配对 CoInitialize/CoUninitialize；无 pywin32 时不初始化。"""

    def __init__(self) -> None:
        self._inited = False
        self._thread_id: int | None = None

    def __enter__(self) -> ComSession:
        if self._inited:
            raise RuntimeError("COM 会话不能重复进入")
        try:
            _initialize_com()
        except ImportError:
            return self
        self._inited = True
        self._thread_id = threading.get_ident()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._inited:
            if self._thread_id != threading.get_ident():
                raise RuntimeError("COM 会话必须在初始化线程释放")
            try:
                _uninitialize_com()
            finally:
                self._inited = False
                self._thread_id = None


def init_office_app(prog_id: str) -> Any:
    """按需创建 COM 引用；共享应用不设置 Visible/DisplayAlerts。"""
    import win32com.client

    dispatch_ex = cast(Callable[[str], Any], win32com.client.DispatchEx)
    app = dispatch_ex(prog_id)
    if prog_id in _OWNED_APPLICATIONS:
        try:
            app.Visible = False
            app.DisplayAlerts = False
        except Exception:
            # 初始化属性失败也必须释放已创建的专属空应用。
            with contextlib.suppress(Exception):
                dispose_office_app(app, prog_id, raise_on_error=True)
            raise
    return app


def init_isolated_office_app(prog_id: str) -> Any:
    """只允许已验证独立实例语义的 Microsoft Word/Excel。"""
    if prog_id not in _OWNED_APPLICATIONS:
        raise ValueError(f"未验证该应用可创建独占会话: {prog_id}")
    return init_office_app(prog_id)


def open_office_document(
    app: Any,
    collection_name: DocumentCollection,
    path: Path,
    *args: object,
    **kwargs: object,
) -> Any:
    """拒绝接管应用中已经打开的目标文档，避免稍后 Close 非任务文档。"""
    documents = getattr(app, collection_name)
    target = os.path.normcase(os.path.realpath(path))
    for document in documents:
        if os.path.normcase(os.path.realpath(document.FullName)) == target:
            raise RuntimeError(f"目标文档已在 Office 中打开，不能接管: {path.name}")
    return documents.Open(str(path.absolute()), *args, **kwargs)


@contextlib.contextmanager
def office_document(
    app: Any,
    collection_name: DocumentCollection,
    path: Path,
    *args: object,
    **kwargs: object,
) -> Iterator[Any]:
    """无论转换成功或失败都关闭本次文档；保留处理及关闭错误。"""
    document = open_office_document(app, collection_name, path, *args, **kwargs)

    def close() -> None:
        if collection_name == "Presentations":
            document.Saved = True  # 只丢弃本次转换的内存排版，不改原文件。
            document.Close()
        else:
            document.Close(False)

    try:
        yield document
    except Exception as error:
        try:
            close()
        except Exception as cleanup_error:
            raise RuntimeError(f"{error}；关闭 Office 文档失败: {cleanup_error}") from error
        raise
    else:
        close()


def dispose_office_app(
    app: Any | None,
    prog_id: str,
    *,
    gc_pause: float = 0.0,
    raise_on_error: bool = False,
) -> None:
    """仅 Quit 已知专属且没有未关闭文档的应用；共享引用只由调用方释放。

    不按进程名/PID 差集清理，也不能硬中断正在进行的 COM 调用。
    调用方必须在创建线程关闭文档、清空引用，再退出 ComSession。
    """
    if app is None:
        return
    quit_error: Exception | None = None
    try:
        collection_name = _OWNED_APPLICATIONS.get(prog_id)
        if collection_name is not None:
            count = getattr(app, collection_name).Count
            if count != 0:
                identity = prog_id
                # PID 仅用于人工定位保留的会话，绝不作为 kill/归属授权。
                with contextlib.suppress(Exception):
                    import win32gui
                    import win32process

                    window = app.ActiveWindow if prog_id == "Word.Application" else app
                    hwnd = window.Hwnd
                    if win32gui.IsWindow(hwnd):
                        thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
                        if thread_id and pid:
                            identity += f" (PID {pid})"
                raise RuntimeError(
                    f"{identity} 仍有 {count} 个未关闭文档，保留会话，不执行 Quit；"
                    "请在该应用中保存并关闭文档"
                )
            app.Quit()
    except Exception as error:
        quit_error = error
    gc.collect()
    if gc_pause > 0:
        time.sleep(gc_pause)
    if quit_error is not None and raise_on_error:
        raise RuntimeError(f"关闭 Office 应用失败: {quit_error}") from quit_error
