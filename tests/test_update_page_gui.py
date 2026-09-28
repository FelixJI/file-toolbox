"""独立更新页(UpdateTab)行为与跨入口集成测试(#129)。

覆盖:页面状态展示(检查/新版/失败/不支持/下载/应用/取消)、代理设置迁移、
横幅与关于页"仅导航不下载"(AC1)、懒构造回放(AC3)、下载期间业务页锁定而
更新页可操作(AC4)。
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable

from file_toolbox.updater.coordinator import UpdateRequest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLineEdit,
    QListWidget,
    QMessageBox,
)

from file_toolbox.gui.dialogs.update_tab import UpdateTab  # noqa: E402
from file_toolbox.gui.main_window import MainWindow  # noqa: E402
from file_toolbox.updater import (  # noqa: E402
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _available(version: str = "9.9.9", notes: str = "") -> UpdateCheckResult:
    return UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version=version, release_notes=notes)


# ---------------------------------------------------------------------------
# 检查动作与结果展示
# ---------------------------------------------------------------------------


def test_check_button_emits_signal(app):
    tab = UpdateTab()
    received: list = []
    tab.check_requested.connect(lambda: received.append(1))
    tab.btn_check_update.click()
    assert received == [1]


def test_check_button_disables_during_check(app):
    tab = UpdateTab()
    tab.btn_check_update.click()
    assert tab.btn_check_update.isEnabled() is False
    assert "检查更新中" in tab._status_lbl.text()
    assert tab._target_version_lbl.text() == "目标版本 —"


def test_display_available_shows_action_and_notes(app):
    tab = UpdateTab()
    tab.display_check_result(_available("9.9.9", notes="## 9.9.9\n\n- 新功能 A"))
    assert "9.9.9" in tab._status_lbl.text()
    assert "#0969da" in tab._status_lbl.styleSheet()
    assert tab._target_version_lbl.text() == "目标版本 v9.9.9"
    assert tab.btn_download_update.isHidden() is False
    assert tab._notes_lbl.isHidden() is False
    assert "新功能 A" in tab._notes_view.toPlainText()
    assert tab.btn_check_update.isEnabled() is True


def test_display_available_without_notes_hides_notes(app):
    tab = UpdateTab()
    tab.display_check_result(_available("9.9.9"))
    assert tab.btn_download_update.isHidden() is False
    assert tab._notes_view.isHidden() is True


def test_display_latest_hides_action(app):
    tab = UpdateTab()
    tab.display_check_result(_available("9.9.9"))
    tab.display_check_result(UpdateCheckResult(UpdateCheckStatus.LATEST, current_version="0.3.5"))
    assert tab.btn_download_update.isHidden() is True
    assert tab._target_version_lbl.text() == "目标版本 —"
    assert "最新" in tab._status_lbl.text()
    assert tab._status_lbl.styleSheet() == ""


def test_display_failed_colored_and_hides_action(app):
    tab = UpdateTab()
    tab.display_check_result(UpdateCheckResult(UpdateCheckStatus.FAILED, message="无法连接更新源"))
    assert "#d1242f" in tab._status_lbl.styleSheet()
    assert tab.btn_download_update.isHidden() is True
    assert "无法连接更新源" in tab._status_lbl.text()


def test_display_unsupported_shows_reason(app):
    tab = UpdateTab()
    tab.display_check_result(
        UpdateCheckResult(
            UpdateCheckStatus.UNSUPPORTED, message="当前运行形态未检测到有效的 Velopack 安装布局"
        )
    )
    assert "安装布局" in tab._status_lbl.text()
    assert tab.btn_download_update.isHidden() is True


def test_check_again_clears_previous_state(app):
    tab = UpdateTab()
    tab.display_check_result(_available("9.9.9", notes="- 新功能"))
    tab.btn_check_update.click()
    assert tab.btn_download_update.isHidden() is True
    assert tab._notes_view.isHidden() is True
    assert "检查更新中" in tab._status_lbl.text()


def test_download_button_emits_signal(app):
    tab = UpdateTab()
    received: list = []
    tab.download_requested.connect(lambda: received.append(1))
    tab.display_check_result(_available("9.9.9"))
    tab.btn_download_update.click()
    assert received == [1]


def test_cancel_button_emits_signal(app):
    tab = UpdateTab()
    received: list = []
    tab.cancel_requested.connect(lambda: received.append(1))
    tab.btn_cancel_update.click()
    assert received == [1]


def test_startup_outcome_displayed_and_cleared(app):
    tab = UpdateTab()
    assert tab._outcome_lbl.isHidden() is True
    tab.set_startup_outcome("已成功更新到 v0.3.7")
    assert tab._outcome_lbl.isHidden() is False
    assert "v0.3.7" in tab._outcome_lbl.text()
    tab.set_startup_outcome("")
    assert tab._outcome_lbl.isHidden() is True


# ---------------------------------------------------------------------------
# 下载事务的页面状态机
# ---------------------------------------------------------------------------


def test_begin_progress_apply_finish_lifecycle(app):
    tab = UpdateTab()
    tab.display_check_result(_available("9.9.9"))
    tab.begin_download("9.9.9")
    assert tab.btn_check_update.isEnabled() is False
    assert tab.btn_download_update.isEnabled() is False
    assert tab.btn_cancel_update.isHidden() is False
    assert tab._progress.isHidden() is False
    tab.set_download_progress(50)
    assert tab._progress.value() == 50
    tab.set_download_progress(100)
    assert "校验" in tab._status_lbl.text()
    tab.enter_apply_phase()
    assert tab.btn_cancel_update.isHidden() is True
    assert "无法取消" in tab._status_lbl.text()
    tab.finish_download(restored=True)
    assert tab._progress.isHidden() is True
    assert tab.btn_check_update.isEnabled() is True
    assert tab.btn_download_update.isEnabled() is True
    assert tab.btn_download_update.text() == "下载并更新"


def test_finish_without_pending_collapses_action(app):
    """候选已过期(restore=False)时收起主动作,不能继续下载旧目标。"""
    tab = UpdateTab()
    tab.display_check_result(_available("9.9.9"))
    tab.begin_download("9.9.9")
    tab.finish_download(restored=False)
    assert tab.btn_download_update.isHidden() is True
    assert tab._target_version_lbl.text() == "目标版本 —"


# ---------------------------------------------------------------------------
# 代理设置(自关于页迁移,语义不变;默认折叠)
# ---------------------------------------------------------------------------


def test_proxy_group_collapsed_by_default(app):
    """折叠是真隐藏而非仅禁用:checkable QGroupBox 未勾选时内容仍会显示。"""
    from PySide6.QtWidgets import QWidget

    tab = UpdateTab()
    tab.show()
    app.processEvents()
    visible = [c for c in tab._proxy_box.findChildren(QWidget) if c.isVisible()]
    assert visible == []
    tab._proxy_box.setChecked(True)
    app.processEvents()
    assert [c for c in tab._proxy_box.findChildren(QWidget) if c.isVisible()] != []


def _expand_proxy(tab: UpdateTab) -> None:
    """折叠组内的控件在展开前是禁用的;测试先按用户路径展开。"""
    tab._proxy_box.setChecked(True)


def test_proxy_edit_exists(app):
    assert isinstance(UpdateTab()._proxy_edit, QLineEdit)


def test_proxy_list_has_defaults(app):
    from file_toolbox.updater.proxy import DEFAULT_PROXIES

    tab = UpdateTab()
    _expand_proxy(tab)
    lst = tab.findChild(QListWidget)
    assert lst is not None
    texts = [lst.item(i).text() for i in range(lst.count())]
    for proxy in DEFAULT_PROXIES:
        assert any(proxy in t for t in texts), f"默认代理 {proxy} 未出现在列表"


def test_proxy_select_all_and_none(app):
    from PySide6.QtCore import Qt

    tab = UpdateTab()
    _expand_proxy(tab)
    lst = tab.findChild(QListWidget)
    tab.btn_proxy_select_none.click()
    for i in range(lst.count()):
        assert lst.item(i).checkState() == Qt.CheckState.Unchecked
    tab.btn_proxy_select_all.click()
    for i in range(lst.count()):
        assert lst.item(i).checkState() == Qt.CheckState.Checked


def test_proxy_add_custom_and_duplicate(app):
    from PySide6.QtCore import Qt

    tab = UpdateTab()
    _expand_proxy(tab)
    custom = "https://my-proxy.example"
    tab._proxy_edit.setText(custom)
    tab.btn_proxy_add.click()
    lst = tab.findChild(QListWidget)
    urls = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
    assert urls.count(custom) == 1
    assert tab._proxy_edit.text() == ""
    # 重复添加 → 不重复,仅勾选
    tab._proxy_edit.setText(custom)
    tab.btn_proxy_add.click()
    urls = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
    assert urls.count(custom) == 1


def test_proxy_save_writes_checked_and_forward(app, monkeypatch, tmp_path):
    from PySide6.QtCore import Qt

    monkeypatch.chdir(tmp_path)
    from file_toolbox.common import settings

    tab = UpdateTab()
    _expand_proxy(tab)
    tab.btn_proxy_select_none.click()
    lst = tab.findChild(QListWidget)
    first_url = lst.item(0).data(Qt.ItemDataRole.UserRole)
    lst.item(0).setCheckState(Qt.CheckState.Checked)
    tab._forward_proxy_edit.setText("http://127.0.0.1:8899")
    tab.btn_proxy_save.click()
    assert settings.get("gh_proxies") == [first_url]
    assert settings.get("forward_proxy") == "http://127.0.0.1:8899"


def test_proxy_save_none_means_direct(app, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from file_toolbox.common import settings

    tab = UpdateTab()
    _expand_proxy(tab)
    tab.btn_proxy_select_none.click()
    tab.btn_proxy_save.click()
    assert settings.get("gh_proxies") == []


def test_proxy_remove_custom_keeps_defaults(app):
    tab = UpdateTab()
    _expand_proxy(tab)
    custom = "https://removable.example"
    tab._proxy_edit.setText(custom)
    tab.btn_proxy_add.click()
    lst = tab.findChild(QListWidget)
    custom_row = next(
        i for i in range(lst.count()) if lst.item(i).data(Qt.ItemDataRole.UserRole) == custom
    )
    lst.setCurrentRow(custom_row)
    tab.btn_proxy_remove.click()
    urls = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
    assert urls.count(custom) == 0
    # 默认项不可移除:选中第一个默认项移除 → 仅取消勾选,数量不变
    count_before = lst.count()
    lst.setCurrentRow(0)
    first_url = lst.item(0).data(Qt.ItemDataRole.UserRole)
    tab.btn_proxy_remove.click()
    urls = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
    assert first_url in urls
    assert lst.count() == count_before


# ---------------------------------------------------------------------------
# 主窗口集成:入口收敛 / 回放 / 业务保护
# ---------------------------------------------------------------------------


class CountingCoordinator:
    """记录 download_and_apply 调用次数的假 coordinator(AC1:导航 0 次调用)。"""

    def __init__(self, check_result: UpdateCheckResult | None = None) -> None:
        self.check_result = check_result or UpdateCheckResult(UpdateCheckStatus.LATEST)
        self.download_calls = 0

    def check(self) -> UpdateCheckResult:
        return self.check_result

    def download_and_apply(
        self,
        progress: Callable[[int], None] | None = None,
        *,
        request: UpdateRequest | None = None,
        before_apply: Callable[[], None] | None = None,
        expected_version: str | None = None,
    ) -> UpdateApplyResult:
        self.download_calls += 1
        return UpdateApplyResult(UpdateApplyStatus.APPLY_STARTED)


def _window_with_available(app, monkeypatch, tmp_path) -> tuple[MainWindow, CountingCoordinator]:
    monkeypatch.chdir(tmp_path)
    coordinator = CountingCoordinator(_available("8.0.0"))
    win = MainWindow(coordinator)
    return win, coordinator


def test_banner_click_navigates_without_download(app, monkeypatch, tmp_path):
    """右下角横幅点击 → 仅打开更新页;SDK 下载/apply 调用次数为 0(AC1)。"""
    win, coordinator = _window_with_available(app, monkeypatch, tmp_path)
    win._on_update_checked(_available("8.0.0"))
    win._update_banner.click()
    assert win._tabs.currentIndex() == 9
    assert coordinator.download_calls == 0
    assert win._download_request is None


def test_about_button_navigates_without_download(app, monkeypatch, tmp_path):
    """关于页"打开更新页面" → 仅导航;SDK 调用 0 次(AC1)。"""
    win, coordinator = _window_with_available(app, monkeypatch, tmp_path)
    win._tabs.setCurrentIndex(10)  # 关于页
    about = win._about_tab
    assert about is not None
    about.btn_open_update_page.click()
    assert win._tabs.currentIndex() == 9
    assert coordinator.download_calls == 0


def test_update_page_reachable_without_new_version(app, monkeypatch, tmp_path):
    """无新版/未检查时更新页仍可从正常导航进入(AC1)。"""
    monkeypatch.chdir(tmp_path)
    win = MainWindow(CountingCoordinator(UpdateCheckResult(UpdateCheckStatus.LATEST)))
    win._tabs.setCurrentIndex(9)
    assert win._update_tab is not None
    assert win._update_tab.btn_download_update.isHidden() is True


def test_check_result_displays_on_constructed_page(app, monkeypatch, tmp_path):
    win, _ = _window_with_available(app, monkeypatch, tmp_path)
    win._tabs.setCurrentIndex(9)
    win._update_worker.do_check()  # coordinator 注入 → AVAILABLE 8.0.0
    app.processEvents()
    assert "8.0.0" in win._update_tab._status_lbl.text()
    assert win._update_tab.btn_download_update.isHidden() is False


def test_auto_result_replayed_on_lazy_construction(app, monkeypatch, tmp_path):
    """自动检查先于页面创建 → 构造后回放完整状态(AC3)。"""
    win, _ = _window_with_available(app, monkeypatch, tmp_path)
    win._on_update_checked(_available("8.0.0", notes="- 内容"))
    win._tabs.setCurrentIndex(9)
    assert "8.0.0" in win._update_tab._status_lbl.text()
    assert win._update_tab.btn_download_update.isHidden() is False
    assert "内容" in win._update_tab._notes_view.toPlainText()


class GatedCoordinator(CountingCoordinator):
    """download_and_apply 阻塞在门上:让测试在真实 worker 线程下载期间观察 UI。"""

    def __init__(self, check_result: UpdateCheckResult | None = None) -> None:
        super().__init__(check_result or _available("8.0.0"))
        self.gate = threading.Event()

    def download_and_apply(
        self,
        progress: Callable[[int], None] | None = None,
        *,
        request: UpdateRequest | None = None,
        before_apply: Callable[[], None] | None = None,
        expected_version: str | None = None,
    ) -> UpdateApplyResult:
        self.download_calls += 1
        assert self.gate.wait(10), "下载门 10s 内未放行"
        if progress is not None:
            progress(40)
        return UpdateApplyResult(UpdateApplyStatus.CANCELLED)


def _wait_until(predicate, timeout: float = 5.0, pump: QApplication | None = None) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pump is not None:
            pump.processEvents()  # queued 信号送达主线程后谓词才可能翻转
        if predicate():
            return
        time.sleep(0.05)
    raise TimeoutError("condition not met")


def test_download_flow_locks_business_but_not_update_page(app, monkeypatch, tmp_path):
    """下载期间:业务页禁用、更新页可操作、取消可用;容器不禁用(AC4)。"""
    monkeypatch.chdir(tmp_path)
    coordinator = GatedCoordinator(_available("8.0.0"))
    win = MainWindow(coordinator)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Apply)
    win._update_worker.start()
    try:
        win._tabs.setCurrentIndex(9)
        win._on_update_checked(_available("8.0.0"))
        win._start_download()

        _wait_until(lambda: coordinator.download_calls == 1)

        assert win._tabs.isEnabled() is True  # 容器未被整体禁用
        assert win._update_tab.isEnabled() is True
        assert win._update_tab.btn_cancel_update.isHidden() is False
        rename_tab = win._rename_tab
        assert rename_tab is not None
        assert rename_tab.isEnabled() is False  # 业务页锁定

        coordinator.gate.set()  # 放行 → CANCELLED 收尾
        _wait_until(lambda: coordinator.gate.is_set() and win._download_request is None, pump=app)
        assert rename_tab.isEnabled() is True
        assert win._update_tab.btn_check_update.isEnabled() is True
    finally:
        coordinator.gate.set()
        win._update_worker.quit()
        win._update_worker.wait(2000)


def test_page_switch_does_not_restart_transaction(app, monkeypatch, tmp_path):
    """下载中快速切走/返回不重建事务、不触发第二次下载(AC3)。"""
    monkeypatch.chdir(tmp_path)
    coordinator = GatedCoordinator(_available("8.0.0"))
    win = MainWindow(coordinator)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Apply)
    win._update_worker.start()
    try:
        win._tabs.setCurrentIndex(9)
        win._on_update_checked(_available("8.0.0"))
        win._start_download()
        request = win._download_request
        assert request is not None
        _wait_until(lambda: coordinator.download_calls == 1)

        win._tabs.setCurrentIndex(0)
        app.processEvents()
        win._tabs.setCurrentIndex(9)
        app.processEvents()

        assert win._download_request is request
        assert coordinator.download_calls == 1
        assert win._update_tab._progress.isHidden() is False
    finally:
        coordinator.gate.set()
        win._update_worker.quit()
        win._update_worker.wait(2000)


def test_repeated_download_clicks_single_transaction(app, monkeypatch, tmp_path):
    """下载进行中重复点击主动作不会提交第二次(仅一个有效请求,AC3)。"""
    monkeypatch.chdir(tmp_path)
    coordinator = GatedCoordinator(_available("8.0.0"))
    win = MainWindow(coordinator)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Apply)
    win._update_worker.start()
    try:
        win._tabs.setCurrentIndex(9)
        win._on_update_checked(_available("8.0.0"))
        win._start_download()
        _wait_until(lambda: coordinator.download_calls == 1)
        win._start_download()  # 进行中重复点击

        assert coordinator.download_calls == 1
    finally:
        coordinator.gate.set()
        win._update_worker.quit()
        win._update_worker.wait(2000)
