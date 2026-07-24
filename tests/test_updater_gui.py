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

    def test_checked_signal_exists(self, app):
        """worker 暴露 checked 信号。"""
        w = UpdateWorker()
        assert hasattr(w, "checked")
        w.deleteLater()

    def test_check_emits_checked_available_when_update(self, app, monkeypatch):
        """有新版 → emit checked(rel, 'available')。"""
        import file_toolbox.updater as upkg

        rel = RemoteRelease("9.9.9", "http://x/a.zip", "http://x/c.txt", "github")
        monkeypatch.setattr(upkg, "check_update", lambda: rel)

        w = UpdateWorker()
        checked: list = []
        w.checked.connect(lambda r, s: checked.append((r, s)))
        w.do_check()
        assert len(checked) == 1
        assert checked[0][1] == "available"
        assert checked[0][0] is rel
        w.deleteLater()

    def test_check_emits_checked_latest_when_no_update(self, app, monkeypatch):
        """无新版 → emit checked(None, 'latest')。"""
        import file_toolbox.updater as upkg

        monkeypatch.setattr(upkg, "check_update", lambda: None)
        w = UpdateWorker()
        checked: list = []
        w.checked.connect(lambda r, s: checked.append((r, s)))
        w.do_check()
        assert checked == [(None, "latest")]
        w.deleteLater()

    def test_check_emits_checked_failed_on_exception(self, app, monkeypatch):
        """check_update 抛异常 → emit checked(None, 'failed')。"""
        import file_toolbox.updater as upkg

        def boom():
            raise RuntimeError("network down")

        monkeypatch.setattr(upkg, "check_update", boom)
        w = UpdateWorker()
        checked: list = []
        w.checked.connect(lambda r, s: checked.append((r, s)))
        w.do_check()
        assert checked == [(None, "failed")]
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
        """worker ready 信号 → banner 显示(便携版)。"""
        import file_toolbox.updater as upkg

        rel = RemoteRelease("9.9.9", "http://x/a.zip", "http://x/c.txt", "github")
        monkeypatch.setattr(upkg, "check_update", lambda: rel)
        # _on_update_ready 仅便携版弹 banner;测试环境非便携,需模拟便携形态
        monkeypatch.setattr(upkg, "is_portable_exe", lambda: True)

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

    def test_history_button_is_toolbutton_with_menu(self, app):
        """历史按钮是 QToolButton 且带 5 项菜单。"""
        from PySide6.QtWidgets import QToolButton

        win = MainWindow()
        assert isinstance(win.btn_history, QToolButton)
        menu = win.btn_history.menu()
        assert menu is not None
        actions = menu.actions()
        assert len(actions) == 5
        labels = [a.text() for a in actions]
        assert "重命名历史" in labels
        assert "建文件夹历史" in labels
        assert "生成PDF历史" in labels
        assert "内容替换历史" in labels
        assert "发票识别历史" in labels
        win.deleteLater()

    def test_history_menu_item_opens_dialog(self, app, monkeypatch):
        """点菜单项 → 打开对应 HistoryDialog(无二次选择)。"""
        opened: list[str] = []

        from file_toolbox.gui import main_window as mw_mod

        class _SpyDialog:
            def __init__(self, history, tool, parent=None):
                opened.append(tool)

            def exec(self):
                return 0

        monkeypatch.setattr(mw_mod, "HistoryDialog", _SpyDialog)
        win = MainWindow()
        menu = win.btn_history.menu()
        # 点「重命名历史」
        act = next(a for a in menu.actions() if a.text() == "重命名历史")
        act.trigger()
        assert opened == ["rename"]
        win.deleteLater()

    def test_check_requested_triggers_worker(self, app, monkeypatch):
        """关于页 check_requested → 主窗口投递 worker do_check。"""
        import file_toolbox.updater as upkg

        rel = RemoteRelease("9.9.9", "http://x/a.zip", "http://x/c.txt", "github")
        monkeypatch.setattr(upkg, "check_update", lambda: rel)

        win = MainWindow()
        # 关于页触发检查请求
        win._about_tab.check_requested.emit()
        # 同步调 do_check(模拟 worker 投递后执行)
        win._update_worker.do_check()
        app.processEvents()
        # 结果应回显到关于页
        assert win._about_tab.btn_check_update.isEnabled() is True
        assert "9.9.9" in win._about_tab._check_result_lbl.text()
        win.deleteLater()

    def test_manual_check_latest_shown_in_about(self, app, monkeypatch):
        """手动检查无新版 → 关于页显示最新(不弹 banner)。"""
        import file_toolbox.updater as upkg

        monkeypatch.setattr(upkg, "check_update", lambda: None)
        win = MainWindow()
        win._about_tab.check_requested.emit()
        win._update_worker.do_check()
        app.processEvents()
        text = win._about_tab._check_result_lbl.text()
        assert "最新" in text
        # 非便携版不弹 banner
        win.deleteLater()

    def test_manual_check_failed_shown_in_about(self, app, monkeypatch):
        """手动检查失败 → 关于页显示失败。"""
        import file_toolbox.updater as upkg

        def boom():
            raise RuntimeError("net")

        monkeypatch.setattr(upkg, "check_update", boom)
        win = MainWindow()
        win._about_tab.check_requested.emit()
        win._update_worker.do_check()
        app.processEvents()
        text = win._about_tab._check_result_lbl.text()
        assert "失败" in text
        win.deleteLater()
