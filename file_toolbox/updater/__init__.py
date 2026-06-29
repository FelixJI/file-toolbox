"""自更新子系统对外门面。

对外暴露:
  - check_update(): 检查是否有新版本(返回 RemoteRelease 或 None)
  - is_portable_exe(): 当前是否以便携 exe(Nuitka standalone)形态运行

三层职责(versions/downloader/replacer)在各自模块内,门面只做组装与转发。
"""

from __future__ import annotations

import sys
from pathlib import Path

from file_toolbox import __version__
from file_toolbox.updater.versions import RemoteRelease, fetch_latest, is_newer

__all__ = ["check_update", "is_portable_exe", "RemoteRelease"]


def is_portable_exe() -> bool:
    """检测当前是否以便携 exe(Nuitka standalone)形态运行。

    判据:可执行名 == FileToolbox.exe 且同目录存在 python3.dll
    (Nuitka standalone 产物的运行时标记)。
    """
    exe = Path(sys.executable)
    return exe.name == "FileToolbox.exe" and (exe.parent / "python3.dll").exists()


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
