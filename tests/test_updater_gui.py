"""updater GUI 组件冒烟测试:验证信号连接 + Banner 控件,不真做网络请求。"""

import pytest

pytest.importorskip("PySide6")

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
