"""updater GUI 组件冒烟测试:验证信号连接 + Banner 控件,不真做网络请求。"""

import os

# GUI 测试用离屏平台,避免弹窗干扰
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

# 用 QtWidgets 子模块做 importorskip(而非顶层 PySide6):后者只校验包可 import,
# 不触发 libEGL/libGL 原生库加载;真实 import QtWidgets 才会,缺库时应跳过而非收集失败。
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from file_toolbox.gui.updater_widget import UpdateBanner, UpdateWorker  # noqa: E402
from file_toolbox.updater.versions import RemoteRelease  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class TestUpdateBanner:
    def test_is_widget(self, app):
        banner = UpdateBanner()
        assert banner.isHidden() is True  # 默认隐藏

    def test_show_release(self, app):
        banner = UpdateBanner()
        rel = RemoteRelease("1.2.0", "http://x/a.zip", "http://x/c.txt", "github")
        banner.show_release(rel)
        assert banner.isVisible() is True
        # 文案含版本号
        text = banner.text()
        assert "1.2.0" in text

    def test_click_emits_signal(self, app):
        banner = UpdateBanner()
        rel = RemoteRelease("1.2.0", "http://x/a.zip", "http://x/c.txt", "github")
        banner.show_release(rel)
        clicked: list = []
        banner.clicked.connect(lambda: clicked.append(1))
        # QLabel 无 click(),用 QTest 模拟鼠标点击
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        QTest.mouseClick(banner, Qt.MouseButton.LeftButton)
        assert len(clicked) == 1


class TestUpdateWorker:
    def test_signals_exist(self, app):
        """worker 暴露 ready/progress/verified/failed 信号。"""
        w = UpdateWorker()
        assert hasattr(w, "ready")
        assert hasattr(w, "progress")
        assert hasattr(w, "verified")
        assert hasattr(w, "failed")
        w.deleteLater()

    def test_check_emits_ready_when_update_available(self, app, monkeypatch):
        """检查到新版本 → emit ready(RemoteRelease)。"""
        import file_toolbox.updater as upkg

        rel = RemoteRelease("9.9.9", "http://x/a.zip", "http://x/c.txt", "github")
        monkeypatch.setattr(upkg, "check_update", lambda: rel)

        w = UpdateWorker()
        got: list = []
        w.ready.connect(lambda r: got.append(r))
        w.do_check()
        assert len(got) == 1
        assert got[0].version == "9.9.9"
        w.deleteLater()

    def test_check_silent_when_no_update(self, app, monkeypatch):
        import file_toolbox.updater as upkg

        monkeypatch.setattr(upkg, "check_update", lambda: None)
        w = UpdateWorker()
        got: list = []
        w.ready.connect(lambda r: got.append(r))
        w.do_check()
        assert got == []
        w.deleteLater()


from file_toolbox.gui.main_window import MainWindow  # noqa: E402


class TestMainWindowIntegration:
    def test_banner_added(self, app):
        """主窗口实例化后含 UpdateBanner(默认隐藏)。"""
        win = MainWindow()
        assert hasattr(win, "_update_banner")
        assert win._update_banner.isHidden() is True
        win.deleteLater()

    def test_worker_added(self, app):
        win = MainWindow()
        assert hasattr(win, "_update_worker")
        win.deleteLater()

    def test_banner_shows_on_ready(self, app, monkeypatch):
        """worker ready 信号 → banner 显示。"""
        import file_toolbox.updater as upkg

        rel = RemoteRelease("9.9.9", "http://x/a.zip", "http://x/c.txt", "github")
        monkeypatch.setattr(upkg, "check_update", lambda: rel)

        win = MainWindow()
        win._update_worker.do_check()
        app.processEvents()
        # isVisible() 在父窗口未 show 时恒为 False;改用 isHidden()(show() 后为 False)
        assert win._update_banner.isHidden() is False
        win.deleteLater()

    def test_no_check_when_not_portable(self, app, monkeypatch):
        """非便携形态(pip 安装)→ 不启动检查,banner 保持隐藏。"""
        import file_toolbox.updater as upkg

        monkeypatch.setattr(upkg, "is_portable_exe", lambda: False)
        win = MainWindow()
        assert win._update_banner.isHidden() is True
        win.deleteLater()
