"""MainWindow 非业务分支与 Coordinator UI 集成补充测试。"""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QMetaObject
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from file_toolbox.gui import main_window as mw_mod
from file_toolbox.gui.dialogs.rename_tab import FileRenamerDialog
from file_toolbox.gui.dialogs.replace_tab import ContentReplaceDialog
from file_toolbox.gui.main_window import MainWindow
from file_toolbox.updater import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)


class LatestCoordinator:
    def check(self) -> UpdateCheckResult:
        return UpdateCheckResult(UpdateCheckStatus.LATEST)

    def download_and_apply(
        self, progress: Callable[[int], None] | None = None
    ) -> UpdateApplyResult:
        return UpdateApplyResult(UpdateApplyStatus.FAILED, "no update")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app):
    return MainWindow(LatestCoordinator())


def test_history_button_opens_current_tab_history(win, monkeypatch):
    opened: list[str] = []

    class SpyDialog:
        def __init__(self, _history, tool, _parent=None):
            opened.append(tool)

        def exec(self):
            return 0

    monkeypatch.setattr("file_toolbox.gui.dialogs.history_dialog.HistoryDialog", SpyDialog)
    win._tabs.setCurrentIndex(2)
    win._open_history_for_current_tab()
    assert opened == ["pdf"]


def test_history_button_disabled_on_about_tab(win):
    win._tabs.setCurrentIndex(6)
    assert win.btn_history.isEnabled() is False


def test_history_button_noop_on_tab_without_history(win, monkeypatch):
    dialog = MagicMock()
    monkeypatch.setattr("file_toolbox.gui.dialogs.history_dialog.HistoryDialog", dialog)
    win._tabs.setCurrentIndex(6)
    win._open_history_for_current_tab()
    dialog.assert_not_called()


def test_tab_tools_mapping(win):
    assert win._tab_tools == [
        "rename",
        "mkdir",
        "pdf",
        "replace",
        "attendance",
        "invoice",
        None,
    ]


def test_only_first_tab_constructed_initially(win):
    """首屏只构造重命名 Tab:其余 Tab 属性为 None,但占位页保持标签/数量。"""

    assert isinstance(win._rename_tab, FileRenamerDialog)
    assert win._replace_tab is None
    assert win._about_tab is None
    assert win._tabs.count() == 7
    assert [win._tabs.tabText(i) for i in range(7)] == [
        "重命名",
        "建文件夹",
        "生成PDF",
        "内容替换",
        "考勤汇总",
        "发票识别",
        "关于",
    ]


def test_lazy_tab_materialized_on_switch(win):
    """首次切换到懒 Tab:原位替换占位页,位置/标签不变且只构造一次。"""

    win._tabs.setCurrentIndex(3)
    assert isinstance(win._replace_tab, ContentReplaceDialog)
    assert win._tabs.count() == 7
    assert win._tabs.tabText(3) == "内容替换"
    assert win._tabs.widget(3) is win._replace_tab
    assert win._tabs.currentIndex() == 3
    # 已构造的 Tab 不重复构造
    before = win._replace_tab
    win._tabs.setCurrentIndex(0)
    win._tabs.setCurrentIndex(3)
    assert win._replace_tab is before


def test_close_event_skips_unconstructed_lazy_tabs(win, monkeypatch):
    """存在未构造懒 Tab 时关闭主窗口:跳过未实例化 Tab,不抛错。"""

    assert win._attendance_tab is None
    win.closeEvent(QCloseEvent())  # 不抛错即通过
    assert win._lazy_specs  # 未切换过的 Tab 仍未构造


def test_about_tab_check_signal_wired_after_lazy_construction(win, monkeypatch):
    """关于页懒构造后 check_requested 信号正确连接到手动检查流程。"""

    starts: list[int] = []
    monkeypatch.setattr(win._update_worker, "start", lambda: starts.append(1))
    monkeypatch.setattr(win, "_trigger_check", lambda: None)
    win._tabs.setCurrentIndex(6)
    assert win._about_tab is not None
    win._about_tab.check_requested.emit()
    assert starts == [1]
    assert win._manual_check_pending is True


def test_trigger_check_noop_when_worker_not_running(win, monkeypatch):
    invoked: list[int] = []
    monkeypatch.setattr(QMetaObject, "invokeMethod", lambda *_args: invoked.append(1))
    win._trigger_check()
    assert invoked == []


def test_on_check_requested_starts_worker(win, monkeypatch):
    starts: list[int] = []
    monkeypatch.setattr(win._update_worker, "start", lambda: starts.append(1))
    monkeypatch.setattr(win, "_trigger_check", lambda: None)
    win._on_check_requested()
    assert starts == [1]
    assert win._manual_check_pending is True


def test_progress_clamps_to_percentage(win):
    win._update_dialog = MagicMock()
    win._on_update_progress(140)
    win._update_dialog.setValue.assert_called_with(100)
    win._update_dialog.setLabelText.assert_called_with("正在校验并准备更新…")


def test_cancel_requests_worker_stop(win):
    win._update_worker = MagicMock()
    win._update_dialog = MagicMock()
    win._on_download_cancel()
    assert win._download_cancelled is True
    assert win._update_dialog is None
    win._update_worker.cancel_download.assert_called_once()


def test_apply_started_quits_after_sdk_schedules_update(win, monkeypatch):
    quit_calls: list[int] = []
    monkeypatch.setattr(QApplication, "quit", lambda: quit_calls.append(1))
    win._on_update_applied(UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED))
    assert quit_calls == [1]


def test_apply_failure_warns_without_quitting(win, monkeypatch):
    warned: list[str] = []
    quit_calls: list[int] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warned.append(message),
    )
    monkeypatch.setattr(QApplication, "quit", lambda: quit_calls.append(1))
    win._on_update_applied(UpdateApplyResult(UpdateApplyStatus.FAILED, "network"))
    assert warned and quit_calls == []


def test_close_event_stops_update_worker(win, monkeypatch):
    worker = MagicMock()
    worker.isRunning.return_value = True
    win._update_worker = worker
    win._materialize_all_tabs()
    for tab in (
        win._rename_tab,
        win._mkdir_tab,
        win._pdf_tab,
        win._replace_tab,
        win._attendance_tab,
        win._invoice_tab,
        win._about_tab,
    ):
        monkeypatch.setattr(type(tab), "closeEvent", lambda self, event: None, raising=False)
    win.closeEvent(QCloseEvent())
    worker.quit.assert_called_once()
    worker.wait.assert_called_once_with(2000)


def test_close_event_respects_attendance_pending_state(win, monkeypatch):
    win._materialize_all_tabs()
    for tab in (
        win._rename_tab,
        win._mkdir_tab,
        win._pdf_tab,
        win._replace_tab,
        win._invoice_tab,
        win._about_tab,
    ):
        monkeypatch.setattr(type(tab), "closeEvent", lambda self, event: None, raising=False)
    monkeypatch.setattr(type(win._attendance_tab), "closeEvent", lambda self, event: None)
    win._attendance_tab._close_pending = True
    event = QCloseEvent()
    win.closeEvent(event)
    assert event.isAccepted() is False
    win._attendance_tab._close_pending = False


def test_main_window_import_stays_light():
    """启动导入契约:构造首屏后启动链不得拉入非首屏 Tab 及其重依赖。

    回归:dialogs 包 __init__ 曾顶层导入全部 8 个 Tab,首屏 Tab 构造会连带把
    pypdfium2+pypdf+chardet+cattrs(~440ms dev)全部带入启动链。子进程隔离
    验证,避免本会话已导入模块干扰。
    """
    import subprocess
    import sys
    from pathlib import Path

    import file_toolbox

    repo_root = Path(file_toolbox.__file__).resolve().parents[1]
    code = (
        "import os, sys\n"
        "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
        "os.environ.setdefault('FILE_TOOLBOX_NO_COM_DETECT', '1')\n"
        "from PySide6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "from file_toolbox.gui.main_window import MainWindow\n"
        "MainWindow()\n"
        "mods = sys.modules\n"
        "leaked = {m for m in mods\n"
        "          if m.split('.')[0] in {'pypdfium2', 'pypdf', 'chardet', 'cattrs', 'attr', 'PIL'}}\n"
        "leaked |= {m for m in mods\n"
        "           if m.startswith('file_toolbox.gui.dialogs.')\n"
        "           and m != 'file_toolbox.gui.dialogs.rename_tab'}\n"
        "print(','.join(sorted(leaked)))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        check=True,
    )
    assert proc.stdout.strip() == "", f"启动链被污染: {proc.stdout.strip()}"


def test_run_gui_creates_and_shows_window(monkeypatch, tmp_path):
    import sys

    modes: list[str] = []
    shown: list[int] = []
    fake_window = MagicMock()
    fake_window.show.side_effect = lambda: shown.append(1)
    monkeypatch.setattr(mw_mod, "MainWindow", lambda: fake_window)
    monkeypatch.setattr(
        mw_mod, "configure_logging", lambda *, mode: modes.append(mode) or tmp_path / "log"
    )
    real_app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(real_app, "exec", lambda: 0)
    exited: list[int] = []
    monkeypatch.setattr(sys, "exit", lambda code=0: exited.append(code))
    mw_mod.run_gui()
    assert modes == ["gui"]
    assert shown == [1]
    assert exited == [0]
