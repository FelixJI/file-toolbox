"""GUI 单实例守卫:同一份数据根(便携目录/仓库)只允许一个 GUI 进程。

重复启动的常见来源:更新器 15s hook 超时强杀后重拉(0.2.9-0.2.11 故障)、
旧进程退出迟滞期间用户等不及再次双击、用户连击图标。secondary 进程不弹窗,
请求主实例把既有窗口提前后直接退出,用户看到的是"窗口被激活"而非两个 GUI。

判定顺序(先连接后监听,Windows 下不能反过来):
  Windows 命名管道允许同名的多个 server 实例,重复 ``listen`` 也返回 True,
  "listen 失败 = 已有实例"不成立。必须先以客户端身份连接:连得上即存在
  主实例;连不上再 listen 成为主实例。主实例存活期间 secondary 不会 listen,
  因此不会出现双主实例瓜分连接的分脑。
"""

from __future__ import annotations

import contextlib
import logging
import sys
import zlib
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_logger = logging.getLogger(__name__)
_ACTIVATE_MESSAGE = b"activate\n"
_ACK_MESSAGE = b"ok"
_CONNECT_TIMEOUT_MS = 1500


def server_name_for(data_root: Path) -> str:
    """由数据根派生本地服务名:同一份安装共享一个名字,不同安装互不影响。

    大小写归一应对 Windows 不区分大小写的路径;CRC32 只做隔离用,无安全语义。
    """

    normalized = str(data_root).replace("\\", "/").casefold()
    return f"file-toolbox-gui-{zlib.crc32(normalized.encode('utf-8')):08x}"


def _allow_foreground_activation() -> None:
    """把前台激活权让给任意进程,主实例 activateWindow() 才能真正抢到前台。

    Windows 前台锁:只有前台进程(刚被用户启动的 secondary)有授权资格;
    非 win32 或授权失败都静默,最坏情形主实例只闪任务栏图标。
    """

    if sys.platform != "win32":
        return
    with contextlib.suppress(OSError):
        import ctypes

        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY


class SingleInstanceGuard(QObject):
    """基于 QLocalServer 的单实例锁,存活期由 run_gui 的局部引用保持。

    activateRequested 在主实例收到 secondary 的激活消息时发出(经事件循环派发),
    run_gui 连接该信号把既有窗口取消最小化并提前。
    """

    activateRequested = Signal()

    def __init__(self, server_name: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server_name = server_name
        self._server = QLocalServer()
        self._clients: list[QLocalSocket] = []

    def acquire(self) -> bool:
        """尝试成为主实例;False 表示已有实例存活且已被请求激活,调用方应退出。"""

        if self._notify_primary():
            return False
        # unix 下前一次异常退出可能残留 socket 文件;Windows 命名管道随进程消失,清理为空操作
        QLocalServer.removeServer(self._server_name)
        if self._listen():
            return True
        # 极小概率的双启动竞态:两边连接失败后同时 listen,慢的一方在此失败。
        # 此时按 secondary 处理;若连激活都送达失败,单实例只是体验优化,fail open。
        _logger.warning("单实例服务监听失败(%s),尝试按重复实例处理", self._server.errorString())
        return not self._notify_primary()

    def release(self) -> None:
        """停止监听(主实例退出前调用;也供测试模拟实例退出)。"""

        self._server.close()

    def _listen(self) -> bool:
        if not self._server.listen(self._server_name):
            return False
        self._server.newConnection.connect(self._on_new_connection)
        return True

    def _notify_primary(self) -> bool:
        """连接既有主实例并发送激活消息;连接失败(无实例)返回 False。

        写完后必须等主实例回执再放手:secondary 的 socket 是局部对象,返回即
        被 GC 断管;不等回执的话,消息可能随管道拆除而丢失(主实例读到空)。
        回执超时按已送达处理 —— 主实例事件循环重度繁忙时回执迟到,不应据此
        放弃单实例语义。
        """

        socket = QLocalSocket()
        socket.connectToServer(self._server_name)
        if not socket.waitForConnected(_CONNECT_TIMEOUT_MS):
            return False
        socket.write(_ACTIVATE_MESSAGE)
        socket.flush()
        socket.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
        _allow_foreground_activation()
        if socket.waitForReadyRead(_CONNECT_TIMEOUT_MS) and _ACK_MESSAGE in socket.readAll().data():
            _logger.info("已有 GUI 实例运行,已请求激活其窗口(已确认)")
        else:
            _logger.warning("已有 GUI 实例运行,激活请求已发送但未收到回执")
        return True

    def _on_new_connection(self) -> None:
        while (client := self._server.nextPendingConnection()) is not None:
            client.readyRead.connect(lambda c=client: self._read_client(c))
            # 持有引用:消息到达前 socket 不能被 GC 断开管道
            self._clients.append(client)
            if client.bytesAvailable() > 0:
                # 激活消息可能在 readyRead 连接之前就已写入管道,信号已错过
                self._read_client(client)

    def _read_client(self, client: QLocalSocket) -> None:
        if _ACTIVATE_MESSAGE.strip() not in client.readAll().data():
            return
        _logger.info("收到重复启动的激活请求")
        self.activateRequested.emit()
        client.write(_ACK_MESSAGE)
        client.flush()
        with contextlib.suppress(ValueError):
            self._clients.remove(client)
        client.disconnectFromServer()
