"""自更新 GUI 组件:UpdateWorker(后台检查/下载)+ UpdateBanner(状态栏提示)。

线程模型(QThread 事件循环):
  - 检查:主窗口 start() → run() → exec() 启动事件循环;
         主窗口用 invokeMethod(do_check, QueuedConnection) 投递检查。
  - 下载:主窗口用 invokeMethod(do_download, QueuedConnection, release) 投递下载。
  两者都在 worker 线程执行,不阻塞 UI。progress/verified/failed 跨线程经信号回主线程。
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel, QWidget

from file_toolbox.updater.errors import UpdateError
from file_toolbox.updater.versions import RemoteRelease

_logger = logging.getLogger(__name__)


class UpdateBanner(QLabel):
    """状态栏更新提示条。默认隐藏,有新版时 show_release() 显示。

    点击触发 clicked 信号(主窗口据此启动下载)。
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "color: #0969da; padding: 2px 8px; cursor: pointer; text-decoration: underline;"
        )
        self.hide()

    def show_release(self, release: RemoteRelease) -> None:
        self.setText(f"🆕 发现新版本 {release.version} · 点击更新")
        self.show()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt 命名)
        self.clicked.emit()


class UpdateWorker(QThread):
    """后台检查 + 下载 worker(运行自身事件循环,接收跨线程方法投递)。

    信号(均跨线程安全投递回主线程):
      ready(RemoteRelease)    — 检查到新版本
      progress(int, int)      — 下载进度(downloaded, total; total=-1 表未知)
      verified(Path)          — 下载校验完成(zip 路径)
      failed(str)             — 任一阶段失败(中文友好提示)

    用法(主线程):
      worker.start()                                  # 启动线程 + 事件循环
      QMetaObject.invokeMethod(worker, "do_check",
                               Qt.ConnectionType.QueuedConnection)
      # 用户点击后:
      QMetaObject.invokeMethod(worker, "do_download",
                               Qt.ConnectionType.QueuedConnection, Q_ARG(...))
    """

    ready = Signal(RemoteRelease)
    progress = Signal(int, int)
    verified = Signal(Path)
    failed = Signal(str)
    checked = Signal(object, str)  # (RemoteRelease | None, "available"|"latest"|"failed")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def run(self) -> None:
        """启动事件循环,等待方法投递(do_check / do_download)。"""
        self.exec()

    @Slot()
    def do_check(self) -> None:
        """检查更新(在 worker 线程执行)。

        始终 emit checked 反馈结果(供手动检查 UI);有新版额外 emit ready。
        自动检查场景只消费 ready(忽略 checked),行为不变。

        必须加 @Slot():主窗口用 QMetaObject.invokeMethod(worker, "do_check",
        QueuedConnection) 按名跨线程投递,PySide6 meta-object 系统只能识别
        被装饰为槽的方法;不加装饰器时投递事件会被静默丢弃,表现为"检查无反应"。
        """
        from file_toolbox import updater as updater_pkg

        try:
            rel = updater_pkg.check_update()
        except Exception as e:
            _logger.warning("检查更新失败: %s", e)
            self.checked.emit(None, "failed")
            return
        if rel is not None:
            self.checked.emit(rel, "available")
            self.ready.emit(rel)
        else:
            self.checked.emit(None, "latest")

    @Slot(RemoteRelease)
    def do_download(self, release: RemoteRelease) -> None:
        """下载并校验(在 worker 线程执行)。

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
