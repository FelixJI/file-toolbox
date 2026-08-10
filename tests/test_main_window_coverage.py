"""main_window 未覆盖分支补充测试。

覆盖:_open_history_tool、更新检查/下载/校验/失败回调、_apply_update、closeEvent、run_gui。
mock worker/对话框,避免真实网络/进程替换。
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from unittest.mock import MagicMock

from PySide6.QtCore import QMetaObject
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from file_toolbox.gui import main_window as mw_mod
from file_toolbox.gui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, monkeypatch, tmp_path):
    """构造 MainWindow,worker 不启动(避免后台线程/网络)。"""
    monkeypatch.setattr(mw_mod.updater_pkg, "is_portable_exe", lambda: False)
    return MainWindow()


# ---------------------------------------------------------------------------
# 历史按钮跟随当前标签页(_open_history_for_current_tab / _on_tab_changed)
# ---------------------------------------------------------------------------


def test_history_button_opens_current_tab_history(win, monkeypatch):
    """点击历史按钮 → 打开当前 tab 对应的历史(默认首个 tab = rename)。"""
    called = {"n": 0, "tool": None}

    def fake_init(self, history, tool, parent=None):
        called["tool"] = tool

    def fake_exec(self):
        called["n"] += 1
        return 0

    monkeypatch.setattr(mw_mod.HistoryDialog, "__init__", fake_init)
    monkeypatch.setattr(mw_mod.HistoryDialog, "exec", fake_exec)
    # 默认当前 tab 是 0 = rename
    win._open_history_for_current_tab()
    assert called["n"] == 1
    assert called["tool"] == "rename"


def test_history_button_disabled_on_about_tab(win):
    """切到'关于'tab → 历史按钮禁用(关于页无历史)。"""
    # 关于 tab 是最后一个(index 5)
    about_index = len(win._tab_tools) - 1
    win._tabs.setCurrentIndex(about_index)
    assert win.btn_history.isEnabled() is False


def test_history_button_enabled_on_function_tab(win):
    """切到功能 tab(如 pdf)→ 历史按钮启用。"""
    pdf_index = win._tab_tools.index("pdf")
    win._tabs.setCurrentIndex(pdf_index)
    assert win.btn_history.isEnabled() is True


def test_history_button_no_menu(win):
    """历史按钮不再有下拉菜单(直接点击打开当前 tab 历史)。"""
    assert win.btn_history.menu() is None


def test_history_button_noop_on_tab_without_history(win, monkeypatch):
    """当前 tab 无历史(关于页)→ 点击历史按钮无操作(不弹窗)。"""
    called = {"n": 0}

    def fake_exec(self):
        called["n"] += 1
        return 0

    monkeypatch.setattr(mw_mod.HistoryDialog, "exec", fake_exec)
    about_index = len(win._tab_tools) - 1
    win._tabs.setCurrentIndex(about_index)
    win._open_history_for_current_tab()
    assert called["n"] == 0  # 未打开对话框


def test_tab_tools_mapping(win):
    """_tab_tools 对应 6 个功能工具，末尾（关于）为 None。"""
    assert win._tab_tools == [
        "rename",
        "mkdir",
        "pdf",
        "replace",
        "attendance",
        "invoice",
        None,
    ]


# ---------------------------------------------------------------------------
# _trigger_check(行 124-130)
# ---------------------------------------------------------------------------


def test_trigger_check_noop_when_worker_not_running(win):
    """worker 未运行 → 直接 return(行 126-127)。"""
    # MainWindow 构造时非便携形态 → worker 未 start
    win._trigger_check()  # 不应抛


def test_trigger_check_invokes_method_when_running(win, monkeypatch):
    """worker 运行 → QMetaObject.invokeMethod(行 128-130)。"""
    win._update_worker = MagicMock()
    win._update_worker.isRunning.return_value = True
    invoked = []
    monkeypatch.setattr(QMetaObject, "invokeMethod", lambda *a, **k: invoked.append(a))
    win._trigger_check()
    assert invoked


# ---------------------------------------------------------------------------
# _on_check_requested(行 132-138)
# ---------------------------------------------------------------------------


def test_on_check_requested_starts_worker_if_not_running(win, monkeypatch):
    """worker 未运行 → start(行 134-136)。"""
    win._update_worker = MagicMock()
    win._update_worker.isRunning.return_value = False
    monkeypatch.setattr(win, "_trigger_check", lambda: None)
    win._on_check_requested()
    win._update_worker.start.assert_called_once()
    assert win._manual_check_pending is True


def test_on_check_requested_worker_running(win, monkeypatch):
    win._update_worker = MagicMock()
    win._update_worker.isRunning.return_value = True
    monkeypatch.setattr(win, "_trigger_check", lambda: None)
    win._on_check_requested()
    win._update_worker.start.assert_not_called()


# ---------------------------------------------------------------------------
# _on_update_checked(行 140-161)
# ---------------------------------------------------------------------------


def test_on_update_checked_ignored_when_not_manual(win):
    """非手动检查 → 忽略(行 145-146)。"""
    win._manual_check_pending = False
    win._on_update_checked(None, "available")  # 不应抛,不调 about


def test_on_update_checked_available_portable(win, monkeypatch):
    win._manual_check_pending = True
    monkeypatch.setattr(mw_mod.updater_pkg, "is_portable_exe", lambda: True)
    win._about_tab = MagicMock()
    release = MagicMock()
    release.version = "1.0"
    win._on_update_checked(release, "available")
    win._about_tab.display_check_result.assert_called_once()
    assert "1.0" in win._about_tab.display_check_result.call_args[0][1]


def test_on_update_checked_available_pip(win, monkeypatch):
    win._manual_check_pending = True
    monkeypatch.setattr(mw_mod.updater_pkg, "is_portable_exe", lambda: False)
    win._about_tab = MagicMock()
    release = MagicMock()
    release.version = "2.0"
    win._on_update_checked(release, "available")
    args = win._about_tab.display_check_result.call_args[0]
    assert "pip install" in args[1]


def test_on_update_checked_failed(win):
    win._manual_check_pending = True
    win._about_tab = MagicMock()
    win._on_update_checked(None, "failed")
    win._about_tab.display_check_result.assert_called_with(
        "failed", "⚠ 检查更新失败,请检查网络或代理设置"
    )


def test_on_update_checked_latest(win):
    win._manual_check_pending = True
    win._about_tab = MagicMock()
    win._on_update_checked(None, "latest")
    args = win._about_tab.display_check_result.call_args[0]
    assert args[0] == "latest"


# ---------------------------------------------------------------------------
# _on_update_ready(行 163-168)
# ---------------------------------------------------------------------------


def test_on_update_ready_portable_shows_banner(win, monkeypatch):
    win._update_banner = MagicMock()
    monkeypatch.setattr(mw_mod.updater_pkg, "is_portable_exe", lambda: True)
    release = MagicMock()
    win._on_update_ready(release)
    win._update_banner.show_release.assert_called_once_with(release)
    assert win._pending_release is release


def test_on_update_ready_pip_no_banner(win, monkeypatch):
    win._update_banner = MagicMock()
    monkeypatch.setattr(mw_mod.updater_pkg, "is_portable_exe", lambda: False)
    release = MagicMock()
    win._on_update_ready(release)
    win._update_banner.show_release.assert_not_called()


# ---------------------------------------------------------------------------
# _start_download(行 170-192)
# ---------------------------------------------------------------------------


def test_start_download_no_pending_noop(win):
    win._pending_release = None
    win._start_download()  # 不应抛


def test_start_download_shows_dialog(win, monkeypatch):
    win._pending_release = MagicMock()
    win._pending_release.version = "1.0"
    win._update_banner = MagicMock()
    win._update_worker = MagicMock()
    # mock Q_ARG 与 QMetaObject.invokeMethod 避免 RemoteRelease 类型问题
    import PySide6.QtCore as qtcore

    monkeypatch.setattr(qtcore, "Q_ARG", lambda *a, **k: None)
    monkeypatch.setattr(QMetaObject, "invokeMethod", lambda *a, **k: None)
    shown = []
    monkeypatch.setattr(QProgressDialog, "show", lambda self: shown.append(1))
    win._start_download()
    assert win._update_dialog is not None
    assert shown


# ---------------------------------------------------------------------------
# _on_download_cancel(行 194-197)
# ---------------------------------------------------------------------------


def test_on_download_cancel_sets_flag(win):
    win._update_dialog = MagicMock()
    win._on_download_cancel()
    assert win._download_cancelled is True
    assert win._update_dialog is None


# ---------------------------------------------------------------------------
# _on_update_progress(行 199-211)
# ---------------------------------------------------------------------------


def test_on_update_progress_no_dialog_noop(win):
    win._update_dialog = None
    win._on_update_progress(100, 200)  # 不应抛


def test_on_update_progress_unknown_total(win):
    """total <= 0 → 不确定模式(行 202-205)。"""
    win._update_dialog = MagicMock()
    win._on_update_progress(2048, 0)
    win._update_dialog.setRange.assert_called_with(0, 0)


def test_on_update_progress_normal(win):
    win._update_dialog = MagicMock()
    win._on_update_progress(50, 200)
    win._update_dialog.setValue.assert_called_with(25)


def test_on_update_progress_complete(win):
    """downloaded >= total → '正在校验完整性'(行 210-211)。"""
    win._update_dialog = MagicMock()
    win._on_update_progress(200, 200)
    win._update_dialog.setLabelText.assert_called_with("正在校验完整性…")


# ---------------------------------------------------------------------------
# _on_update_verified(行 213-227)
# ---------------------------------------------------------------------------


def test_on_update_verified_cancelled_silent(win, monkeypatch):
    win._update_dialog = MagicMock()
    win._download_cancelled = True
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Cancel
    )
    win._on_update_verified("x.zip")
    # 取消 → 不弹信息(但 _update_dialog 被 close)


def test_on_update_verified_apply(win, monkeypatch):
    win._update_dialog = MagicMock()
    win._download_cancelled = False
    applied = {"n": 0}
    monkeypatch.setattr(win, "_apply_update", lambda p: applied.__setitem__("n", 1))
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Apply
    )
    win._on_update_verified("x.zip")
    assert applied["n"] == 1


def test_on_update_verified_cancel(win, monkeypatch):
    win._update_dialog = MagicMock()
    win._download_cancelled = False
    applied = {"n": 0}
    monkeypatch.setattr(win, "_apply_update", lambda p: applied.__setitem__("n", 1))
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Cancel
    )
    win._on_update_verified("x.zip")
    assert applied["n"] == 0


# ---------------------------------------------------------------------------
# _on_update_failed(行 229-236)
# ---------------------------------------------------------------------------


def test_on_update_failed_cancelled_silent(win, monkeypatch):
    win._update_dialog = MagicMock()
    win._download_cancelled = True
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(1) or QMessageBox.StandardButton.Ok
    )
    win._on_update_failed("boom")
    assert warned == []


def test_on_update_failed_shows_warning(win, monkeypatch):
    win._update_dialog = MagicMock()
    win._download_cancelled = False
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(1) or QMessageBox.StandardButton.Ok
    )
    win._on_update_failed("网络错误")
    assert warned


# ---------------------------------------------------------------------------
# _apply_update(行 238-255)
# ---------------------------------------------------------------------------


def test_apply_update_success_quits(win, monkeypatch):
    """replace_dir 成功 → QApplication.quit(行 247, 255)。"""
    import file_toolbox.updater.replacer as replacer_mod

    monkeypatch.setattr(replacer_mod, "replace_dir", lambda *a, **k: None)
    quit_called = []
    monkeypatch.setattr(QApplication, "quit", lambda: quit_called.append(1))
    win._apply_update("update.zip")
    assert quit_called


def test_apply_update_update_error_warns(win, monkeypatch):
    """replace_dir 抛 UpdateError → 友好提示,不退出(行 248-251)。"""
    import file_toolbox.updater.replacer as replacer_mod
    from file_toolbox.updater.errors import UpdateError

    monkeypatch.setattr(
        replacer_mod, "replace_dir", lambda *a, **k: (_ for _ in ()).throw(UpdateError("bad zip"))
    )
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(1) or QMessageBox.StandardButton.Ok
    )
    quit_called = []
    monkeypatch.setattr(QApplication, "quit", lambda: quit_called.append(1))
    win._apply_update("update.zip")
    assert warned
    assert not quit_called  # 未退出


# ---------------------------------------------------------------------------
# closeEvent(行 257-277)
# ---------------------------------------------------------------------------


def test_close_event(win, monkeypatch):
    """closeEvent 退出 worker + 调各 tab closeEvent(行 257-277)。"""
    from PySide6.QtGui import QCloseEvent

    win._update_worker = MagicMock()
    win._update_worker.isRunning.return_value = True
    # mock 各 tab 避免 cleanup 副作用
    for tab in (win._rename_tab, win._mkdir_tab, win._pdf_tab, win._replace_tab):
        monkeypatch.setattr(type(tab), "closeEvent", lambda self, e: None, raising=False)
    win.closeEvent(QCloseEvent())  # 不应抛


def test_close_event_worker_exception_swallowed(win, monkeypatch):
    """worker.isRunning 抛异常 → except 吞(行 263-264)。"""
    from PySide6.QtGui import QCloseEvent

    win._update_worker = MagicMock()
    win._update_worker.isRunning.side_effect = RuntimeError("boom")
    for tab in (win._rename_tab, win._mkdir_tab, win._pdf_tab, win._replace_tab):
        monkeypatch.setattr(type(tab), "closeEvent", lambda self, e: None, raising=False)
    win.closeEvent(QCloseEvent())  # 不应抛


# ---------------------------------------------------------------------------
# run_gui(行 280-)
# ---------------------------------------------------------------------------


def test_run_gui_creates_window(monkeypatch):
    """run_gui 构造 app + MainWindow + show + sys.exit(app.exec())(行 280-289)。

    mock sys.exit 与 app.exec,验证不阻塞。
    """
    import sys

    monkeypatch.setattr(mw_mod.updater_pkg, "is_portable_exe", lambda: False)
    real_app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(real_app, "exec", lambda: 0)
    exited = []
    monkeypatch.setattr(sys, "exit", lambda code=0: exited.append(code))
    mw_mod.run_gui()
    assert exited
