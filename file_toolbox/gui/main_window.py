"""File Toolbox 主窗口：QMainWindow + 6 个功能 Tab。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QByteArray, QMetaObject, QRect, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.common.logging_config import configure_logging
from file_toolbox.common.metadata import VERSION
from file_toolbox.common.runtime import is_packaged_runtime
from file_toolbox.gui.freeze_watchdog import FreezeWatchdog
from file_toolbox.gui.updater_widget import UpdateBanner, UpdateWorker
from file_toolbox.updater import create_update_coordinator
from file_toolbox.updater.coordinator import UpdateCoordinator
from file_toolbox.updater.models import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)

if TYPE_CHECKING:
    # Tab 类仅在类型标注中使用;运行时导入延迟到各 _make_*_tab 工厂,
    # 避免 dialogs 包(及其重依赖 pypdfium2/pypdf/chardet/cattrs)进入启动链。
    from file_toolbox.gui.dialogs.about_tab import AboutTab
    from file_toolbox.gui.dialogs.attendance_tab import AttendanceTab
    from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab
    from file_toolbox.gui.dialogs.mkdir_tab import BatchFolderCreatorDialog
    from file_toolbox.gui.dialogs.pdf_tab import PDFGeneratorDialog
    from file_toolbox.gui.dialogs.rename_tab import FileRenamerDialog
    from file_toolbox.gui.dialogs.replace_tab import ContentReplaceDialog

_logger = logging.getLogger(__name__)

# 窗口几何持久化 key(settings.json):base64(saveGeometry)。
_GEOMETRY_KEY = "window/geometry"


def _make_rename_tab() -> FileRenamerDialog:
    from file_toolbox.gui.dialogs.rename_tab import FileRenamerDialog

    return FileRenamerDialog()


def _make_mkdir_tab() -> BatchFolderCreatorDialog:
    from file_toolbox.gui.dialogs.mkdir_tab import BatchFolderCreatorDialog

    return BatchFolderCreatorDialog()


def _make_pdf_tab() -> PDFGeneratorDialog:
    from file_toolbox.gui.dialogs.pdf_tab import PDFGeneratorDialog

    return PDFGeneratorDialog()


def _make_replace_tab() -> ContentReplaceDialog:
    from file_toolbox.gui.dialogs.replace_tab import ContentReplaceDialog

    return ContentReplaceDialog()


def _make_attendance_tab() -> AttendanceTab:
    from file_toolbox.gui.dialogs.attendance_tab import AttendanceTab

    return AttendanceTab()


def _make_invoice_tab() -> InvoiceTab:
    from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab

    return InvoiceTab()


def _make_about_tab() -> AboutTab:
    from file_toolbox.gui.dialogs.about_tab import AboutTab

    return AboutTab()


def _construct_tab(factory: Callable[[], QWidget], name: str) -> QWidget:
    """构造一个功能 Tab 并记录耗时(偶发启动卡顿时定位到具体 Tab)。"""
    t0 = time.perf_counter()
    tab = factory()
    _logger.debug("Tab 构造完成 tab=%s 耗时=%.0fms", name, (time.perf_counter() - t0) * 1000)
    return tab


class MainWindow(QMainWindow):
    """工具箱主窗口，6 个功能 Tab。"""

    def __init__(self, coordinator: UpdateCoordinator | None = None) -> None:
        super().__init__()
        self.setWindowTitle("File Toolbox")
        self._restore_window_geometry()

        self._history = JsonHistoryStore()

        central = QWidget()
        layout = QVBoxLayout(central)
        # 主区域不留外边距,避免标签栏上方出现一片空白带
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部:历史按钮(直接对应当前标签页,无需二次选择;右对齐)
        top = QHBoxLayout()
        top.setContentsMargins(9, 5, 9, 2)
        top.addStretch(1)
        self.btn_history = QToolButton()
        self.btn_history.setText("历史")
        self.btn_history.clicked.connect(self._open_history_for_current_tab)
        top.addWidget(self.btn_history)
        layout.addLayout(top)

        # 6 个功能 Tab + 关于:Tab 类与重依赖(pypdfium2/pypdf/chardet/cattrs)
        # 均懒导入,首次构造某 Tab 时才 import;首屏只构造重命名 Tab。
        # 打包形态下真实平台主窗口构造可达 ~1.7s,大头是首个控件初始化链
        # 之后的各 Tab 陆续构造;懒掉非首屏 Tab 让首帧只付首 Tab 的成本。
        tabs = QTabWidget()
        self._tabs = tabs
        self._rename_tab: FileRenamerDialog | None = None
        self._mkdir_tab: BatchFolderCreatorDialog | None = None
        self._pdf_tab: PDFGeneratorDialog | None = None
        self._replace_tab: ContentReplaceDialog | None = None
        self._attendance_tab: AttendanceTab | None = None
        self._invoice_tab: InvoiceTab | None = None
        self._about_tab: AboutTab | None = None
        # 懒构造登记:index -> (标签文本, Tab 工厂, 属性名);占位页被真实 Tab 原位替换。
        # 含首屏(重命名):由 __init__ 末尾的 _on_tab_changed 统一触发构造。
        self._lazy_specs: dict[int, tuple[str, Callable[[], QWidget], str]] = {
            index: (label, factory, attr)
            for index, (label, factory, attr) in enumerate(
                [
                    ("重命名", _make_rename_tab, "_rename_tab"),
                    ("建文件夹", _make_mkdir_tab, "_mkdir_tab"),
                    ("生成PDF", _make_pdf_tab, "_pdf_tab"),
                    ("内容替换", _make_replace_tab, "_replace_tab"),
                    ("考勤汇总", _make_attendance_tab, "_attendance_tab"),
                    ("发票识别", _make_invoice_tab, "_invoice_tab"),
                    ("关于", _make_about_tab, "_about_tab"),
                ]
            )
        }
        for label, _factory, _attr in self._lazy_specs.values():
            tabs.addTab(QWidget(), label)
        # 各 Tab 对应的历史工具名;"关于"页无历史 → None(按钮禁用)
        self._tab_tools: list[str | None] = [
            "rename",
            "mkdir",
            "pdf",
            "replace",
            "attendance",
            "invoice",
            None,
        ]
        tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(tabs, stretch=1)

        central.setLayout(layout)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

        # --- 自更新:状态栏 banner + 后台 worker(仅便携 exe 形态启用检查) ---
        self._update_banner = UpdateBanner()
        self.statusBar().addPermanentWidget(self._update_banner)
        self._update_worker = UpdateWorker(coordinator or create_update_coordinator())
        self._update_worker.ready.connect(self._on_update_ready)
        self._update_worker.progress.connect(self._on_update_progress)
        self._update_worker.applied.connect(self._on_update_applied)
        self._update_banner.clicked.connect(self._start_download)
        self._pending_update: UpdateCheckResult | None = None
        self._update_dialog: QProgressDialog | None = None
        self._download_cancelled = False  # 用户取消下载后抑制后续 verified/failed 弹窗

        self._update_worker.checked.connect(self._on_update_checked)
        self._manual_check_pending = False  # 区分手动 vs 自动检查(关于页懒构造后连接)

        if is_packaged_runtime():
            # 仅打包产物(Nuitka/Velopack)形态自动检查;开发态仍可从关于页手动检查。
            # 不能只看 sys.frozen:Nuitka standalone 不设置它,便携包曾因此
            # 被当成开发态,自动检查从未运行。
            self._update_worker.start()
            QTimer.singleShot(0, self._trigger_check)

        # 历史按钮初始状态跟随当前(首个)标签页
        self._on_tab_changed(self._tabs.currentIndex())

    def _ensure_tab(self, index: int) -> None:
        """懒构造:用真实 Tab 原位替换占位页(标签与位置不变)。

        blockSignals 防止 removeTab/insertTab 期间 currentChanged 跳到别的
        占位页触发连锁构造;结束后恢复原 currentIndex(即被构造的 Tab)。
        """

        spec = self._lazy_specs.get(index)
        if spec is None:
            return
        label, factory, attr = spec
        del self._lazy_specs[index]
        tab = _construct_tab(factory, label)
        setattr(self, attr, tab)
        current = self._tabs.currentIndex()
        self._tabs.blockSignals(True)
        self._tabs.removeTab(index)
        self._tabs.insertTab(index, tab, label)
        self._tabs.setCurrentIndex(current)
        self._tabs.blockSignals(False)
        if attr == "_about_tab":
            # 关于页手动检查更新:AboutTab 请求 → 投递 worker → 结果回显
            cast("AboutTab", tab).check_requested.connect(self._on_check_requested)

    def _materialize_all_tabs(self) -> None:
        """立即构造全部懒 Tab(测试与预热场景使用)。"""

        for index in sorted(self._lazy_specs):
            self._ensure_tab(index)

    def _on_tab_changed(self, index: int) -> None:
        """标签页切换:先补建懒 Tab,再更新历史按钮可用状态(关于页无历史 → 禁用)。"""

        self._ensure_tab(index)
        tool = self._tab_tools[index] if 0 <= index < len(self._tab_tools) else None
        self.btn_history.setEnabled(tool is not None)

    def _open_history_for_current_tab(self) -> None:
        """点击历史按钮:直接打开当前标签页对应的历史(无需二次选择)。"""
        index = self._tabs.currentIndex()
        tool = self._tab_tools[index] if 0 <= index < len(self._tab_tools) else None
        if tool is None:
            return
        from file_toolbox.gui.dialogs.history_dialog import HistoryDialog

        dlg = HistoryDialog(self._history, tool, self)
        dlg.exec()

    # --- 自更新槽方法 ---

    def _trigger_check(self) -> None:
        """向 worker 线程投递检查请求(跨线程 QueuedConnection)。"""
        if not self._update_worker.isRunning():
            return
        QMetaObject.invokeMethod(
            self._update_worker, "do_check", Qt.ConnectionType.QueuedConnection
        )

    def _on_check_requested(self) -> None:
        """关于页请求检查更新:确保 worker 运行并投递 do_check。"""
        if not self._update_worker.isRunning():
            # 非便携形态(pip/dev):按需启动 worker(自动检查不会启)
            self._update_worker.start()
        self._manual_check_pending = True
        self._trigger_check()

    def _on_update_checked(self, result: UpdateCheckResult) -> None:
        """worker checked 信号:仅手动检查时回显结果到关于页。

        自动检查场景(启动后台)忽略此回调(由 _on_update_ready 处理 banner)。
        """
        if not self._manual_check_pending:
            return
        self._manual_check_pending = False
        about = self._about_tab
        if about is None:
            return  # 手动检查必经关于页,理论上已构造;防御懒构造态异常路径
        if result.status is UpdateCheckStatus.AVAILABLE:
            about.display_check_result(
                "available", f"🆕 发现新版本 {result.version}(点击底部提示更新)"
            )
        elif result.status is UpdateCheckStatus.FAILED:
            about.display_check_result(
                "failed", f"⚠ {result.message or '检查更新失败,请检查网络或代理设置'}"
            )
        else:  # latest
            about.display_check_result("latest", f"✓ 当前为最新版本 v{VERSION}")

    def _on_update_ready(self, result: UpdateCheckResult) -> None:
        """检查到新版 → 状态栏 banner 提示。"""
        self._pending_update = result
        self._update_banner.show_result(result)

    def _start_download(self) -> None:
        """用户点击 banner → 弹进度对话框 + 向 worker 投递下载请求。"""
        if self._pending_update is None:
            return
        update = self._pending_update
        prompt = f"将下载并应用 v{update.version}，应用会在准备完成后退出并重启。是否继续？"
        if (
            QMessageBox.question(
                self,
                "确认更新",
                prompt,
                QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel,
            )
            != QMessageBox.StandardButton.Apply
        ):
            return
        self._update_banner.hide()
        self._download_cancelled = False  # 新一轮下载,清除取消标记
        label = f"正在下载 v{update.version}…"
        dlg = QProgressDialog(label, "取消", 0, 100, self)
        dlg.setWindowTitle("更新")
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        dlg.canceled.connect(self._on_download_cancel)
        self._update_dialog = dlg
        dlg.show()
        QMetaObject.invokeMethod(
            self._update_worker,
            "do_download_and_apply",
            Qt.ConnectionType.QueuedConnection,
        )

    def _on_download_cancel(self) -> None:
        """用户取消下载:抑制后续 verified/failed 弹窗(下载本身无法中断,任其完成)。"""
        self._download_cancelled = True
        self._update_worker.cancel_download()
        self._update_dialog = None

    def _on_update_progress(self, value: int) -> None:
        if self._update_dialog is None:
            return
        self._update_dialog.setValue(max(0, min(100, value)))
        if value >= 100:
            self._update_dialog.setLabelText("正在校验并准备更新…")

    def _on_update_applied(self, result: UpdateApplyResult) -> None:
        """处理 Coordinator 的 apply 结果。"""
        if self._update_dialog is not None:
            self._update_dialog.close()
            self._update_dialog = None
        if self._download_cancelled or result.status is UpdateApplyStatus.CANCELLED:
            return
        if result.status is UpdateApplyStatus.FAILED:
            QMessageBox.warning(
                self,
                "更新失败",
                f"{result.message}\n\n原程序未受影响,可稍后重试。",
            )
            return
        self._shutdown_for_restart()

    def _shutdown_for_restart(self) -> None:
        """更新已由 Velopack 接管:收尾并真正退出进程,让更新器立即替换重启。

        裸 ``QApplication.quit()`` 不经过 ``closeEvent``,UpdateWorker 的事件
        循环会让进程再活 60s,更新器只能等超时后强杀(0.2.9-0.2.11 的实际
        故障:确认更新到新版本启动约 95s,其中 60s 在等旧进程退出)。
        """
        from PySide6.QtWidgets import QApplication

        self._persist_window_geometry()
        try:
            if self._update_worker.isRunning():
                self._update_worker.quit()
                self._update_worker.wait(2000)
        except Exception:
            _logger.exception("关闭更新 worker 失败")
        QApplication.quit()

    # --- 窗口几何 ---

    def _restore_window_geometry(self) -> None:
        """恢复上次窗口几何;无记录/记录越界(如换了显示器)时回退屏幕自适应默认值。"""
        from file_toolbox.common import settings

        blob = settings.get(_GEOMETRY_KEY)
        restored = False
        if isinstance(blob, str) and blob:
            try:
                restored = self.restoreGeometry(QByteArray.fromBase64(blob.encode("ascii")))
            except ValueError:  # 损坏/非 base64 记录 → 当作无记录
                restored = False
        if restored and self._frame_on_some_screen():
            if not self.isMaximized():
                avail = self._available_geometry()
                self.resize(min(self.width(), avail.width()), min(self.height(), avail.height()))
            return
        self._apply_default_geometry()

    def _frame_on_some_screen(self) -> bool:
        """窗口是否与任一屏幕可视区有交集(防恢复到已拔掉的显示器上)。"""
        frame = self.frameGeometry()
        return any(frame.intersects(s.availableGeometry()) for s in QGuiApplication.screens())

    def _available_geometry(self) -> QRect:
        return (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()

    def _apply_default_geometry(self) -> None:
        """默认尺寸 950×640,且不超过当前屏幕可视区(高分屏缩放/小屏自动收窄)。"""
        avail = self._available_geometry()
        self.resize(min(950, avail.width() - 40), min(640, avail.height() - 60))

    def _persist_window_geometry(self) -> None:
        """保存窗口几何(含最大化状态)到 settings。"""
        from file_toolbox.common import settings

        settings.set(_GEOMETRY_KEY, bytes(self.saveGeometry().toBase64().data()).decode("ascii"))

    def closeEvent(self, event: QCloseEvent) -> None:
        # 记住窗口几何(含最大化状态),下次启动恢复
        self._persist_window_geometry()
        # 退出自更新 worker 线程(若有)
        try:
            if self._update_worker.isRunning():
                self._update_worker.quit()
                self._update_worker.wait(2000)
        except Exception:
            _logger.exception("关闭更新 worker 失败")
        for tab in (
            self._rename_tab,
            self._mkdir_tab,
            self._pdf_tab,
            self._replace_tab,
            self._attendance_tab,
            self._invoice_tab,
            self._about_tab,
        ):
            # 懒构造 Tab 可能尚未实例化(用户未切换过),无实例即无清理
            if tab is None or not hasattr(tab, "closeEvent"):
                continue
            # 触发各 tab 的清理(吞掉异常避免一个 tab 清理失败影响其余)
            try:
                tab.closeEvent(event)
            except Exception:
                _logger.exception("关闭 Tab 失败 tab=%s", type(tab).__name__)
        attendance = self._attendance_tab
        if attendance is not None and attendance.close_pending:
            event.ignore()
            return
        super().closeEvent(event)


def _activate_window(window: QWidget) -> None:
    """把既有主窗口取消最小化并提前(单实例守卫收到重复启动请求时调用)。"""

    window.setWindowState(
        (window.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive
    )
    window.show()
    window.raise_()
    window.activateWindow()


def run_gui() -> None:
    """启动 GUI(供 cli gui 子命令调用)。"""
    import sys

    from PySide6.QtWidgets import QApplication

    from file_toolbox.common.paths import current_data_root
    from file_toolbox.gui.single_instance import SingleInstanceGuard, server_name_for

    log_file = configure_logging(mode="gui")
    _logger.info("GUI 初始化")
    watchdog = FreezeWatchdog(log_file)
    t0 = time.perf_counter()
    app = QApplication.instance() or QApplication(sys.argv)
    _logger.info("QApplication 就绪 耗时=%.0fms", (time.perf_counter() - t0) * 1000)
    watchdog.start(app)
    guard = SingleInstanceGuard(server_name_for(current_data_root()))
    if not guard.acquire():
        # 重复启动:激活既有实例窗口后本进程退出,避免两个 GUI 抢写同一份
        # settings/历史,也避免用户看到"程序打开了两次"。
        _logger.info("检测到已运行的 GUI 实例,本次启动退出")
        return
    t0 = time.perf_counter()
    win = MainWindow()
    guard.activateRequested.connect(lambda: _activate_window(win))
    _logger.info("主窗口构造完成 耗时=%.0fms", (time.perf_counter() - t0) * 1000)
    win.show()
    _logger.info("进入事件循环")
    sys.exit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    run_gui()
