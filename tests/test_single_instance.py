"""GUI 单实例守卫回归契约。

历史缺陷:GUI 从无双实例保护,更新器 15s hook 超时强杀重拉(0.2.9-0.2.11)、
旧进程退出迟滞期间用户再次双击、连击图标,都会表现为"程序打开了两次"。
守卫的判定顺序(先连接后监听)由 Windows 命名管道允许同名多 server 实例决定,
重复 ``listen`` 也返回 True,"listen 失败 = 已有实例"在 Windows 不成立。
"""

import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from file_toolbox.gui.main_window import _activate_window
from file_toolbox.gui.single_instance import SingleInstanceGuard, server_name_for


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _unique_name() -> str:
    return f"file-toolbox-test-{uuid.uuid4().hex[:12]}"


def _wait_until(app: QApplication, predicate: Callable[[], bool], timeout_s: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    return predicate()


class TestServerNameFor:
    def test_same_root_case_insensitive_share_name(self):
        """同一安装的路径大小写差异(Windows 语义)不得分裂出两个服务名。"""

        assert server_name_for(Path("C:/Apps/FileToolbox/.file_toolbox")) == server_name_for(
            Path("c:\\apps\\filetoolbox\\.file_toolbox")
        )

    def test_different_roots_get_different_names(self):
        assert server_name_for(Path("C:/A/.file_toolbox")) != server_name_for(
            Path("C:/B/.file_toolbox")
        )


class TestGuardAcquire:
    def test_primary_acquires_and_secondary_requests_activation(self, app):
        name = _unique_name()
        primary = SingleInstanceGuard(name)
        assert primary.acquire() is True

        activated: list[int] = []
        primary.activateRequested.connect(lambda: activated.append(1))

        # 真实场景中 secondary 是另一个进程;同进程内必须并行跑:
        # secondary 的 _notify_primary 会阻塞等待回执,而主实例要靠本线程
        # 泵事件才能读到消息并回执,串行执行会互锁。
        secondary = SingleInstanceGuard(name)
        result: list[bool] = []
        thread = threading.Thread(target=lambda: result.append(secondary.acquire()))
        thread.start()
        try:
            assert _wait_until(app, lambda: activated == [1])
        finally:
            thread.join(10)
            primary.release()
        assert result == [False]

    def test_takeover_after_primary_released(self, app):
        """主实例退出(释放服务)后,新启动的进程应能接管为主实例。"""

        name = _unique_name()
        primary = SingleInstanceGuard(name)
        assert primary.acquire() is True
        primary.release()

        successor = SingleInstanceGuard(name)
        try:
            assert successor.acquire() is True
        finally:
            successor.release()

    def test_race_loser_falls_back_to_secondary(self, app, monkeypatch):
        """双启动竞态:listen 失败(另一实例抢先)后应按 secondary 处理。"""

        guard = SingleInstanceGuard(_unique_name())
        notify_results = iter([False, True])
        monkeypatch.setattr(guard, "_notify_primary", lambda: next(notify_results))
        monkeypatch.setattr(guard, "_listen", lambda: False)
        assert guard.acquire() is False

    def test_fail_open_when_no_primary_reachable(self, app, monkeypatch):
        """谁都联系不上时必须放行启动:单实例是体验优化,不能拦截用户。"""

        guard = SingleInstanceGuard(_unique_name())
        monkeypatch.setattr(guard, "_notify_primary", lambda: False)
        monkeypatch.setattr(guard, "_listen", lambda: False)
        assert guard.acquire() is True


def test_activate_window_unminimizes_and_shows(app):
    w = QWidget()
    w.show()
    w.setWindowState(Qt.WindowState.WindowMinimized)
    _activate_window(w)
    assert not w.windowState() & Qt.WindowState.WindowMinimized
    assert w.isVisible()


def test_run_gui_secondary_exits_without_window(monkeypatch, tmp_path):
    """secondary 路径:激活请求发出后直接返回,不构造窗口、不进事件循环。"""

    import sys

    from file_toolbox.gui import main_window as mw_mod

    created: list[int] = []
    exited: list[int] = []
    monkeypatch.setattr(mw_mod, "MainWindow", lambda: created.append(1))
    monkeypatch.setattr(mw_mod, "configure_logging", lambda *, mode: tmp_path / "log")
    monkeypatch.setattr(SingleInstanceGuard, "acquire", lambda self: False)
    real_app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(real_app, "exec", lambda: pytest.fail("secondary 不得进入事件循环"))
    monkeypatch.setattr(sys, "exit", lambda code=0: exited.append(code))

    mw_mod.run_gui()

    assert created == []
    assert exited == []
