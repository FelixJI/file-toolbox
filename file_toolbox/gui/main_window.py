"""File Toolbox 主窗口:QMainWindow + 4 Tab。"""

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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


class MainWindow(QMainWindow):
    """工具箱主窗口,4 个功能 Tab。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Toolbox")
        self.resize(950, 720)

        self._history = JsonHistoryStore()

        central = QWidget()
        layout = QVBoxLayout(central)

        # 顶部:历史按钮 + 工具选择
        top = QHBoxLayout()
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

    def closeEvent(self, event):
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
