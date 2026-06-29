"""自更新 GUI 组件:UpdateWorker(后台检查/下载)+ UpdateBanner(状态栏提示)。

线程模型:
  - 检查阶段:do_check() 调 updater.check_update(),有新版 emit ready
  - 下载阶段:do_download(release) 调 downloader.download_and_verify(on_progress=...)
             emit progress(downloaded, total) / verified(zip_path) / failed(msg)
  - 替换阶段:由主窗口在 verified 后触发(调 replacer)

do_check/do_download 为同步方法,由主窗口调度到子线程或事件循环空闲时调用,
避免阻塞 UI(网络请求约 1s,检查失败静默)。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QLabel

from file_toolbox.updater.errors import UpdateError
from file_toolbox.updater.versions import RemoteRelease


class UpdateBanner(QLabel):
    """状态栏更新提示条。默认隐藏,有新版时 show_release() 显示。

    点击触发 clicked 信号(主窗口据此启动下载)。
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "color: #0969da; padding: 2px 8px; cursor: pointer; text-decoration: underline;"
        )
        self.hide()

    def show_release(self, release: RemoteRelease) -> None:
        self.setText(f"🆕 发现新版本 {release.version} · 点击更新")
        self.show()

    def mousePressEvent(self, event):  # noqa: N802 (Qt 命名)
        self.clicked.emit()


class UpdateWorker(QThread):
    """后台检查 + 下载 worker。

    信号:
      ready(RemoteRelease)    — 检查到新版本
      progress(int, int)      — 下载进度(downloaded, total; total=-1 表未知)
      verified(Path)          — 下载校验完成(zip 路径)
      failed(str)             — 任一阶段失败(中文友好提示)
    """

    ready = Signal(RemoteRelease)
    progress = Signal(int, int)
    verified = Signal(Path)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def do_check(self) -> None:
        """检查更新(同步,应由主窗口调度到非阻塞时机)。

        检查失败静默(不打扰用户);有新版 emit ready。
        """
        from file_toolbox import updater as updater_pkg

        try:
            rel = updater_pkg.check_update()
        except Exception:
            # 检查失败静默(不打扰用户)
            return
        if rel is not None:
            self.ready.emit(rel)

    def do_download(self, release: RemoteRelease) -> None:
        """下载并校验(同步,主窗口在用户点击后调度)。

        emit progress(下载进度) / verified(zip 路径) / failed(中文提示)。
        """
        try:
            from file_toolbox.updater.downloader import download_and_verify

            zip_path = download_and_verify(
                release, on_progress=lambda d, t: self.progress.emit(d, t)
            )
            self.verified.emit(zip_path)
        except UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"下载失败: {e}")
