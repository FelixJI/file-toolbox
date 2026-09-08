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
    win._tabs.setCurrentIndex(8)
    assert win.btn_history.isEnabled() is False


def test_history_button_noop_on_tab_without_history(win, monkeypatch):
    dialog = MagicMock()
    monkeypatch.setattr("file_toolbox.gui.dialogs.history_dialog.HistoryDialog", dialog)
    win._tabs.setCurrentIndex(8)
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
        "excel_merge",
        "pdf_sort",
        None,
    ]


def test_only_first_tab_constructed_initially(win):
    """首屏只构造重命名 Tab:其余 Tab 属性为 None,但占位页保持标签/数量。"""

    assert isinstance(win._rename_tab, FileRenamerDialog)
    assert win._replace_tab is None
    assert win._about_tab is None
    assert win._tabs.count() == 9
    assert [win._tabs.tabText(i) for i in range(9)] == [
        "重命名",
        "建文件夹",
        "生成PDF",
        "内容替换",
        "考勤汇总",
        "发票识别",
        "Excel合并",
        "PDF排序",
        "关于",
    ]


def test_lazy_tab_materialized_on_switch(win):
    """首次切换到懒 Tab:原位替换占位页,位置/标签不变且只构造一次。"""

    win._tabs.setCurrentIndex(3)
    assert isinstance(win._replace_tab, ContentReplaceDialog)
    assert win._tabs.count() == 9
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
    win._tabs.setCurrentIndex(8)
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
    """APPLY_STARTED 收尾契约:存几何、停 worker、退出——裸 quit 会让进程
    拖住 60s 后才被更新器强杀(0.2.9-0.2.11 的实际故障)。"""

    quit_calls: list[int] = []
    settings_calls: list[tuple[str, str]] = []
    worker_calls: list[object] = []

    class RunningWorkerStub:
        def isRunning(self) -> bool:
            return True

        def quit(self) -> None:
            worker_calls.append("quit")

        def wait(self, ms: int) -> None:
            worker_calls.append(("wait", ms))

    monkeypatch.setattr(QApplication, "quit", lambda: quit_calls.append(1))
    monkeypatch.setattr(
        "file_toolbox.common.settings.set",
        lambda key, value: settings_calls.append((key, value)),
    )
    win._update_worker = RunningWorkerStub()  # type: ignore[assignment]
    win._on_update_applied(UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED))
    assert quit_calls == [1]
    assert worker_calls == ["quit", ("wait", 2000)]
    assert [key for key, _value in settings_calls] == ["window/geometry"]


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
        win._excel_merge_tab,
        win._pdf_sort_tab,
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
        win._excel_merge_tab,
        win._pdf_sort_tab,
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


def test_geometry_roundtrip_persists_across_sessions(app, monkeypatch, tmp_path):
    """关闭主窗口保存几何,下次启动恢复同一尺寸。"""
    monkeypatch.chdir(tmp_path)
    from file_toolbox.common import settings

    win = MainWindow(LatestCoordinator())
    win.resize(640, 480)
    win.closeEvent(QCloseEvent())
    blob = settings.get("window/geometry")
    assert isinstance(blob, str) and blob

    win2 = MainWindow(LatestCoordinator())
    assert (win2.width(), win2.height()) == (640, 480)


def test_default_geometry_fits_screen_without_settings(app, monkeypatch, tmp_path):
    """无保存记录时按屏幕可视区自适应,高度不超过默认上限 640。"""
    monkeypatch.chdir(tmp_path)
    win = MainWindow(LatestCoordinator())
    avail = win._available_geometry()
    assert win.width() <= avail.width()
    assert win.height() <= min(640, avail.height())


def test_corrupt_geometry_falls_back_to_default(app, monkeypatch, tmp_path):
    """损坏的几何记录按无记录处理,不抛错并回退默认尺寸。"""
    monkeypatch.chdir(tmp_path)
    from file_toolbox.common import settings

    settings.set("window/geometry", "!!!这不是合法的base64###")
    win = MainWindow(LatestCoordinator())
    assert win.height() <= 640


def test_window_min_height_not_pinned_by_tabs(app, monkeypatch, tmp_path):
    """布局回归:全部 Tab 构造后主窗口最小高度不再被钉到 ~963px。

    曾由 PDF 页显式 setMinimumSize(800×600) 与关于页 886px 最小高度叠加导致,
    小屏/高分屏缩放下窗口无法缩小到屏幕内。
    """
    win = MainWindow(LatestCoordinator())
    win._materialize_all_tabs()
    assert win._pdf_tab is not None and win._pdf_tab.minimumSize().isEmpty()
    assert win.minimumSizeHint().height() < 700


def test_about_tab_content_scrollable(app):
    """关于页内容包在 QScrollArea 中:页最小尺寸由滚动区而非内容总高度决定。"""
    from PySide6.QtWidgets import QScrollArea

    from file_toolbox.gui.dialogs.about_tab import AboutTab

    tab = AboutTab()
    assert tab.findChild(QScrollArea) is not None
    assert tab.minimumSizeHint().height() < 300


def test_run_gui_creates_and_shows_window(monkeypatch, tmp_path):
    import sys

    from file_toolbox.gui.single_instance import SingleInstanceGuard

    # 恒为主实例:本机若恰有同数据根的 GUI 在跑,真实守卫会把本测试导向
    # secondary 早退分支,窗口断言随之失败 —— 单例行为另由 test_single_instance 覆盖。
    monkeypatch.setattr(SingleInstanceGuard, "acquire", lambda self: True)
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


# ---------------------------------------------------------------------------
# 更新检查回显与下载发起(关于页手动检查 → banner → 进度对话框)
# ---------------------------------------------------------------------------


class _FakeMetaObject:
    invoke_calls: list[tuple] = []

    @staticmethod
    def invokeMethod(*args, **kwargs):
        _FakeMetaObject.invoke_calls.append(args)


def _materialize_about(win):
    win._materialize_all_tabs()
    assert win._about_tab is not None
    return win._about_tab


def test_on_update_checked_ignores_auto_check_noise(win):
    displayed: list[tuple] = []
    about = _materialize_about(win)
    win._manual_check_pending = False

    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(about, "display_check_result", lambda *args: displayed.append(args))
        win._on_update_checked(UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version="9.9.9"))

    assert displayed == []


def test_on_update_checked_requires_constructed_about_tab(win):
    win._manual_check_pending = True
    win._about_tab = None

    win._on_update_checked(UpdateCheckResult(UpdateCheckStatus.LATEST))  # 防御路径不抛异常


@pytest.mark.parametrize(
    ("status", "version", "expected_kind"),
    [
        (UpdateCheckStatus.AVAILABLE, "9.9.9", "available"),
        (UpdateCheckStatus.FAILED, None, "failed"),
        (UpdateCheckStatus.LATEST, None, "latest"),
    ],
)
def test_on_update_checked_displays_manual_results(win, status, version, expected_kind):
    displayed: list[tuple] = []
    available_results: list[UpdateCheckResult] = []
    about = _materialize_about(win)
    win._manual_check_pending = True

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(about, "display_check_result", lambda *args: displayed.append(args))
        mp.setattr(about, "display_update_available", lambda r: available_results.append(r))
        win._on_update_checked(UpdateCheckResult(status, version=version))

    if expected_kind == "available":
        # available 走完整展示(标签 + 更新内容 + 立即更新按钮)
        assert [r.version for r in available_results] == ["9.9.9"]
        assert displayed == []
    else:
        assert displayed and displayed[0][0] == expected_kind
        assert available_results == []


def test_start_download_without_pending_update_is_noop(win, monkeypatch):
    win._pending_update = None
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: (_ for _ in ()).throw(AssertionError("无待更新版本不应弹确认")),
    )

    win._start_download()


def test_start_download_declined_does_not_dispatch(win, monkeypatch):
    _FakeMetaObject.invoke_calls.clear()
    win._pending_update = UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version="9.9.9")
    monkeypatch.setattr(mw_mod.QMetaObject, "invokeMethod", _FakeMetaObject.invokeMethod)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)

    win._start_download()

    assert _FakeMetaObject.invoke_calls == []
    assert win._update_dialog is None


def test_start_download_confirmed_shows_dialog_and_dispatches(win, monkeypatch):
    _FakeMetaObject.invoke_calls.clear()
    win._pending_update = UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version="9.9.9")
    monkeypatch.setattr(mw_mod.QMetaObject, "invokeMethod", _FakeMetaObject.invokeMethod)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Apply)

    try:
        win._start_download()

        assert _FakeMetaObject.invoke_calls
        assert _FakeMetaObject.invoke_calls[0][1] == "do_download_and_apply"
        assert win._update_dialog is not None
        assert win._download_cancelled is False
        # 到 100% 后还要停留显示"正在校验并准备更新…",必须禁用 Qt 的
        # autoClose/autoReset(默认会在 setValue(100) 时隐藏对话框并重置数值)
        assert win._update_dialog.autoClose() is False
        assert win._update_dialog.autoReset() is False
        assert "9.9.9" in win._update_dialog.windowTitle()
    finally:
        if win._update_dialog is not None:
            win._update_dialog.close()
            win._update_dialog = None


def test_on_download_requested_ensures_worker_and_starts_download(win, monkeypatch):
    """关于页"立即更新":worker 未运行时启动,并复用 _start_download。"""
    starts: list[int] = []
    downloads: list[int] = []
    monkeypatch.setattr(win._update_worker, "start", lambda: starts.append(1))
    monkeypatch.setattr(win._update_worker, "isRunning", lambda: False)
    monkeypatch.setattr(win, "_start_download", lambda: downloads.append(1))

    win._on_download_requested()

    assert starts == [1]
    assert downloads == [1]


def test_about_tab_lazy_construction_receives_pending_update(win):
    """自动检查先发现新版、用户之后才打开关于页 → 构造后补显新版提示。"""
    win._pending_update = UpdateCheckResult(
        UpdateCheckStatus.AVAILABLE, version="9.9.9", release_notes="- 新功能"
    )
    win._tabs.setCurrentIndex(8)
    about = win._about_tab
    assert about is not None
    assert about.btn_download_update.isHidden() is False
    assert "9.9.9" in about._check_result_lbl.text()
    assert "新功能" in about._notes_view.toPlainText()


def test_download_cancel_restores_retry_affordances(win):
    """取消下载后:状态栏横幅恢复显示(可重试),关于页按钮恢复可用。"""
    win._pending_update = UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version="9.9.9")
    about = _materialize_about(win)
    win._update_banner.hide()
    win._update_dialog = MagicMock()
    win._update_worker = MagicMock()

    win._on_download_cancel()

    assert win._download_cancelled is True
    assert win._update_dialog is None
    assert win._update_banner.isHidden() is False
    assert about.btn_download_update.isEnabled() is True
    assert about.btn_check_update.isEnabled() is True


def test_apply_cancelled_result_neither_warns_nor_quits(win, monkeypatch):
    warned: list[str] = []
    quits: list[int] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, message="": warned.append(message))
    monkeypatch.setattr(QApplication, "quit", lambda: quits.append(1))

    win._on_update_applied(UpdateApplyResult(UpdateApplyStatus.CANCELLED))

    assert warned == [] and quits == []


def test_shutdown_survives_update_worker_close_failure(win, monkeypatch):
    quits: list[int] = []

    class BrokenWorkerStub:
        def isRunning(self) -> bool:
            raise RuntimeError("worker already gone")

        def quit(self) -> None:
            raise AssertionError("isRunning 失败后不应继续操作 worker")

    monkeypatch.setattr(QApplication, "quit", lambda: quits.append(1))
    monkeypatch.setattr("file_toolbox.common.settings.set", lambda key, value: None)
    win._update_worker = BrokenWorkerStub()  # type: ignore[assignment]

    win._on_update_applied(UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED))

    assert quits == [1]


def test_update_progress_without_dialog_is_noop(win):
    win._update_dialog = None

    win._on_update_progress(80)  # 不应抛异常


def test_update_progress_partial_value_keeps_download_label(win):
    dialog = MagicMock()
    win._update_dialog = dialog

    win._on_update_progress(45)

    dialog.setValue.assert_called_once_with(45)
    dialog.setLabelText.assert_not_called()
    win._update_dialog = None


def test_close_event_survives_update_worker_quit_failure(win):
    worker = MagicMock()
    worker.isRunning.return_value = True
    worker.quit.side_effect = RuntimeError("quit failed")
    win._update_worker = worker
    event = QCloseEvent()

    win.closeEvent(event)

    worker.quit.assert_called_once()
    assert event.isAccepted() is True
