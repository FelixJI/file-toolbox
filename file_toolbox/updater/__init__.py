"""自更新子系统对外门面。

对外暴露:
  - check_update(): 检查是否有新版本(返回 RemoteRelease 或 None)
  - is_portable_exe(): 当前是否以便携 exe(PyInstaller onedir)形态运行

三层职责(versions/downloader/replacer)在各自模块内,门面只做组装与转发。
"""

from __future__ import annotations

import sys
from pathlib import Path

from file_toolbox import __version__
from file_toolbox.updater.proxy import apply_proxy
from file_toolbox.updater.versions import RemoteRelease, fetch_latest, is_newer

__all__ = ["check_update", "is_portable_exe", "apply_proxy", "RemoteRelease"]


def is_portable_exe() -> bool:
    """检测当前是否以便携 exe(PyInstaller onedir)形态运行。

    PyInstaller 会设置 ``sys.frozen`` 与 ``sys._MEIPASS``。onedir 模式下 bundle
    目录位于 exe 同目录或其子目录(当前 PyInstaller 6 默认是 ``_internal``)；
    onefile 模式的临时 bundle 位于安装目录之外,不能使用整目录替换更新。
    """
    exe = Path(sys.executable).resolve()
    if exe.name.casefold() != "filetoolbox.exe" or not getattr(sys, "frozen", False):
        return False

    bundle_path = getattr(sys, "_MEIPASS", None)
    if not bundle_path:
        return False
    bundle_dir = Path(bundle_path).resolve()
    return bundle_dir == exe.parent or exe.parent in bundle_dir.parents


def check_update() -> RemoteRelease | None:
    """检查是否有比本地更新的正式版本。

    返回最新 RemoteRelease(若有更新),否则 None。
    便携形态之外(pip 安装)也照常检查,由调用方决定是否提示。
    """
    rel = fetch_latest()
    if rel is None:
        return None
    if not is_newer(rel.version, __version__):
        return None
    return rel
