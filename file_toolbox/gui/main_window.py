"""File Toolbox 主窗口:QMainWindow + 4 Tab。"""

from PySide6.QtCore import QMetaObject, Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from file_toolbox import updater as updater_pkg
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.gui.dialogs import (
    AboutTab,
    BatchFolderCreatorDialog,
    ContentReplaceDialog,
    FileRenamerDialog,
    HistoryDialog,
    InvoiceTab,
    PDFGeneratorDialog,
)
from file_toolbox.gui.updater_widget import UpdateBanner, UpdateWorker
from file_toolbox.updater.versions import RemoteRelease


class MainWindow(QMainWindow):
    """工具箱主窗口,4 个功能 Tab。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Toolbox")
        self.resize(950, 720)

        self._history = JsonHistoryStore()

        central = QWidget()
        layout = QVBoxLayout(central)
        # 主区域不留外边距,避免标签栏上方出现一片空白带
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部:历史按钮(右对齐,紧贴标签栏,不撑出一大块空白)
        top = QHBoxLayout()
        top.setContentsMargins(9, 5, 9, 2)
        top.addStretch(1)
        self.btn_history = QPushButton("历史")
        self.btn_history.clicked.connect(self._open_history)
        top.addWidget(self.btn_history)
        layout.addLayout(top)

        # 5 Tab
        tabs = QTabWidget()
        self._rename_tab = FileRenamerDialog()
        self._mkdir_tab = BatchFolderCreatorDialog()
        self._pdf_tab = PDFGeneratorDialog()
        self._replace_tab = ContentReplaceDialog()
        self._invoice_tab = InvoiceTab()
        tabs.addTab(self._rename_tab, "重命名")
        tabs.addTab(self._mkdir_tab, "建文件夹")
        tabs.addTab(self._pdf_tab, "生成PDF")
        tabs.addTab(self._replace_tab, "内容替换")
        tabs.addTab(self._invoice_tab, "发票识别")
        self._about_tab = AboutTab()
        tabs.addTab(self._about_tab, "关于")
        layout.addWidget(tabs, stretch=1)

        central.setLayout(layout)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

        # --- 自更新:状态栏 banner + 后台 worker(仅便携 exe 形态启用检查) ---
        self._update_banner = UpdateBanner()
        self.statusBar().addPermanentWidget(self._update_banner)
        self._update_worker = UpdateWorker(self)
        self._update_worker.ready.connect(self._on_update_ready)
        self._update_worker.progress.connect(self._on_update_progress)
        self._update_worker.verified.connect(self._on_update_verified)
        self._update_worker.failed.connect(self._on_update_failed)
        self._update_banner.clicked.connect(self._start_download)
        self._pending_release: RemoteRelease | None = None
        self._update_dialog: QProgressDialog | None = None
        self._download_cancelled = False  # 用户取消下载后抑制后续 verified/failed 弹窗

        if updater_pkg.is_portable_exe():
            # 启动 worker 线程(事件循环),稍后投递检查(不阻塞 UI)
            self._update_worker.start()
            QTimer.singleShot(0, self._trigger_check)

    def _open_history(self):
        # 简单起见:用一个下拉选择工具,默认显示 rename 历史
        from PySide6.QtWidgets import QInputDialog

        tool, ok = QInputDialog.getItem(
            self,
            "查看历史",
            "选择工具:",
            ["rename", "replace", "pdf", "mkdir", "invoice"],
            0,
            editable=False,
        )
        if not ok:
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

    def _on_update_ready(self, release: RemoteRelease) -> None:
        """检查到新版本 → 状态栏 banner 提示。"""
        self._pending_release = release
        self._update_banner.show_release(release)

    def _start_download(self) -> None:
        """用户点击 banner → 弹进度对话框 + 向 worker 投递下载请求。"""
        if self._pending_release is None:
            return
        self._update_banner.hide()
        release = self._pending_release
        self._download_cancelled = False  # 新一轮下载,清除取消标记
        dlg = QProgressDialog(f"正在下载 v{release.version}…", "取消", 0, 100, self)
        dlg.setWindowTitle("更新")
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        dlg.canceled.connect(self._on_download_cancel)
        self._update_dialog = dlg
        dlg.show()
        # 投递下载到 worker 线程(Q_ARG 包装 RemoteRelease 参数)
        from PySide6.QtCore import Q_ARG

        QMetaObject.invokeMethod(
            self._update_worker,
            "do_download",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(RemoteRelease, release),
        )

    def _on_download_cancel(self) -> None:
        """用户取消下载:抑制后续 verified/failed 弹窗(下载本身无法中断,任其完成)。"""
        self._download_cancelled = True
        self._update_dialog = None

    def _on_update_progress(self, downloaded: int, total: int) -> None:
        if self._update_dialog is None:
            return
        if total <= 0:
            # 拿不到 Content-Length → 不确定模式(滚动条)
            self._update_dialog.setRange(0, 0)
            self._update_dialog.setLabelText(f"正在下载…(已 {downloaded // 1024} KB)")
        else:
            self._update_dialog.setRange(0, 100)
            pct = int(downloaded / total * 100)
            self._update_dialog.setValue(pct)
            if downloaded >= total:
                self._update_dialog.setLabelText("正在校验完整性…")

    def _on_update_verified(self, zip_path) -> None:
        """下载校验完成 → 提示用户应用更新(用户已取消则静默)。"""
        if self._update_dialog is not None:
            self._update_dialog.close()
            self._update_dialog = None
        if self._download_cancelled:
            return
        ret = QMessageBox.information(
            self,
            "更新就绪",
            "更新已下载并通过校验。\n点击「应用更新」将重启生效。",
            QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel,
        )
        if ret == QMessageBox.StandardButton.Apply:
            self._apply_update(zip_path)

    def _on_update_failed(self, msg: str) -> None:
        """下载/校验失败 → 中文友好弹窗,不暴露 traceback(用户已取消则静默)。"""
        if self._update_dialog is not None:
            self._update_dialog.close()
            self._update_dialog = None
        if self._download_cancelled:
            return
        QMessageBox.warning(
            self, "更新失败", f"{msg}\n\n请稍后重试,或前往开源仓库手动下载。"
        )

    def _apply_update(self, zip_path) -> None:
        """生成 helper + 启动 + 退出本程序。"""
        import sys
        from pathlib import Path as _Path

        from file_toolbox.updater.replacer import replace_dir

        replace_dir(_Path(zip_path), exe_path=_Path(sys.executable))
        # helper 已启动,本程序退出
        from PySide6.QtWidgets import QApplication

        QApplication.quit()

    def closeEvent(self, event):
        # 退出自更新 worker 线程(若有)
        try:
            if self._update_worker.isRunning():
                self._update_worker.quit()
                self._update_worker.wait(2000)
        except Exception:
            pass
        for tab in (
            self._rename_tab,
            self._mkdir_tab,
            self._pdf_tab,
            self._replace_tab,
            self._invoice_tab,
            self._about_tab,
        ):
            if hasattr(tab, "closeEvent"):
                # 触发各 tab 的清理
                try:
                    tab.closeEvent(event)  # type: ignore[arg-type]
                except Exception:
                    pass
        super().closeEvent(event)


def run_gui():
    """启动 GUI(供 cli gui 子命令调用)。"""
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
