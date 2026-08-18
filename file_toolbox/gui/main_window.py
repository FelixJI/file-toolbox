"""File Toolbox 主窗口：QMainWindow + 6 个功能 Tab。"""

import logging
import sys
import time

from PySide6.QtCore import QMetaObject, Qt, QTimer
from PySide6.QtGui import QCloseEvent
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
from file_toolbox.gui.dialogs import (
    AboutTab,
    AttendanceTab,
    BatchFolderCreatorDialog,
    ContentReplaceDialog,
    FileRenamerDialog,
    HistoryDialog,
    InvoiceTab,
    PDFGeneratorDialog,
)
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

_logger = logging.getLogger(__name__)


def _construct_tab[T](cls: type[T]) -> T:
    """构造一个功能 Tab 并记录耗时(偶发启动卡顿时定位到具体 Tab)。"""
    t0 = time.perf_counter()
    tab = cls()
    _logger.debug(
        "Tab 构造完成 tab=%s 耗时=%.0fms", cls.__name__, (time.perf_counter() - t0) * 1000
    )
    return tab


class MainWindow(QMainWindow):
    """工具箱主窗口，6 个功能 Tab。"""

    def __init__(self, coordinator: UpdateCoordinator | None = None) -> None:
        super().__init__()
        self.setWindowTitle("File Toolbox")
        self.resize(950, 720)

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

        # 6 个功能 Tab + 关于
        tabs = QTabWidget()
        self._tabs = tabs
        self._rename_tab = _construct_tab(FileRenamerDialog)
        self._mkdir_tab = _construct_tab(BatchFolderCreatorDialog)
        self._pdf_tab = _construct_tab(PDFGeneratorDialog)
        self._replace_tab = _construct_tab(ContentReplaceDialog)
        self._attendance_tab = _construct_tab(AttendanceTab)
        self._invoice_tab = _construct_tab(InvoiceTab)
        tabs.addTab(self._rename_tab, "重命名")
        tabs.addTab(self._mkdir_tab, "建文件夹")
        tabs.addTab(self._pdf_tab, "生成PDF")
        tabs.addTab(self._replace_tab, "内容替换")
        tabs.addTab(self._attendance_tab, "考勤汇总")
        tabs.addTab(self._invoice_tab, "发票识别")
        self._about_tab = AboutTab()
        tabs.addTab(self._about_tab, "关于")
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

        if getattr(sys, "frozen", False):  # pragma: no cover
            # 仅 PyInstaller/Velopack 形态自动检查；开发态仍可从关于页手动检查。
            self._update_worker.start()
            QTimer.singleShot(0, self._trigger_check)

        # 关于页手动检查更新:AboutTab 请求 → 投递 worker → 结果回显
        self._about_tab.check_requested.connect(self._on_check_requested)
        self._update_worker.checked.connect(self._on_update_checked)
        self._manual_check_pending = False  # 区分手动 vs 自动检查

        # 历史按钮初始状态跟随当前(首个)标签页
        self._on_tab_changed(self._tabs.currentIndex())

    def _on_tab_changed(self, index: int) -> None:
        """标签页切换:更新历史按钮可用状态(关于页无历史 → 禁用)。"""
        tool = self._tab_tools[index] if 0 <= index < len(self._tab_tools) else None
        self.btn_history.setEnabled(tool is not None)

    def _open_history_for_current_tab(self) -> None:
        """点击历史按钮:直接打开当前标签页对应的历史(无需二次选择)。"""
        index = self._tabs.currentIndex()
        tool = self._tab_tools[index] if 0 <= index < len(self._tab_tools) else None
        if tool is None:
            return
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
        if result.status is UpdateCheckStatus.AVAILABLE:
            self._about_tab.display_check_result(
                "available", f"🆕 发现新版本 {result.version}(点击底部提示更新)"
            )
        elif result.status is UpdateCheckStatus.FAILED:
            self._about_tab.display_check_result(
                "failed", f"⚠ {result.message or '检查更新失败,请检查网络或代理设置'}"
            )
        else:  # latest
            self._about_tab.display_check_result("latest", f"✓ 当前为最新版本 v{VERSION}")

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
                f"{result.message}\n\n原程序未受影响，可稍后重试。",
            )
            return
        from PySide6.QtWidgets import QApplication

        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
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
            if hasattr(tab, "closeEvent"):
                # 触发各 tab 的清理(吞掉异常避免一个 tab 清理失败影响其余)
                try:
                    tab.closeEvent(event)
                except Exception:
                    _logger.exception("关闭 Tab 失败 tab=%s", type(tab).__name__)
        if self._attendance_tab.close_pending:
            event.ignore()
            return
        super().closeEvent(event)


def run_gui() -> None:
    """启动 GUI(供 cli gui 子命令调用)。"""
    import sys

    from PySide6.QtWidgets import QApplication

    log_file = configure_logging(mode="gui")
    _logger.info("GUI 初始化")
    watchdog = FreezeWatchdog(log_file)
    t0 = time.perf_counter()
    app = QApplication.instance() or QApplication(sys.argv)
    _logger.info("QApplication 就绪 耗时=%.0fms", (time.perf_counter() - t0) * 1000)
    watchdog.start(app)
    t0 = time.perf_counter()
    win = MainWindow()
    _logger.info("主窗口构造完成 耗时=%.0fms", (time.perf_counter() - t0) * 1000)
    win.show()
    _logger.info("进入事件循环")
    sys.exit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    run_gui()
