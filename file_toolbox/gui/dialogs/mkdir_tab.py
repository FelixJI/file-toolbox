"""建文件夹 Tab:从层级或粘贴的 Excel 表格批量创建文件夹结构。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QWidget,
)

from file_toolbox.core.batch_mkdir import ConflictStrategy, FolderCreatorService
from file_toolbox.gui.generated.ui_mkdir_dialog import Ui_BatchFolderCreatorDialog


class BatchFolderCreatorDialog(QDialog):
    """批量创建文件夹对话框(作为 Tab 嵌入)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_BatchFolderCreatorDialog()
        self.ui.setupUi(self)
        self._svc = FolderCreatorService()

        self.ui.btn_cancel.setVisible(False)
        self._connect_signals()

    def _connect_signals(self):
        self.ui.btn_browse_root.clicked.connect(self._browse_root)
        self.ui.btn_clear.clicked.connect(self._clear)
        self.ui.btn_fix_special_chars.clicked.connect(self._fix_special_chars)
        self.ui.btn_create_folders.clicked.connect(self._create_folders)
        self.ui.btn_open_root.clicked.connect(self._open_root)

    def _browse_root(self):
        d = QFileDialog.getExistingDirectory(self, "选择根目录")
        if d:
            self.ui.line_edit_root_path.setText(d)

    def _root_path(self):
        from pathlib import Path

        return Path(self.ui.line_edit_root_path.text().strip() or ".")

    def _clear(self):
        self._paste_table().clearContents()
        self._paste_table().setRowCount(0)

    def _paste_table(self) -> QTableWidget:
        return self.ui.table_paste

    def _fix_special_chars(self):
        """把当前粘贴表中的特殊字符替换为下划线。"""
        tbl = self._paste_table()
        changed = 0
        for r in range(tbl.rowCount()):
            for c in range(tbl.columnCount()):
                item = tbl.item(r, c)
                if item and item.text():
                    fixed = self._svc.replace_special_chars(item.text())
                    if fixed != item.text():
                        item.setText(fixed)
                        changed += 1
        QMessageBox.information(self, "处理完成", f"已替换 {changed} 处特殊字符。")

    def _collect_structures(self) -> list[tuple[str, ...]]:
        """从粘贴表格读取层级结构(按行,Tab 感知用列)。"""
        tbl = self._paste_table()
        structures: list[tuple[str, ...]] = []
        for r in range(tbl.rowCount()):
            parts: list[str] = []
            for c in range(tbl.columnCount()):
                item = tbl.item(r, c)
                if item and item.text().strip():
                    parts.append(item.text().strip())
            if parts:
                structures.append(tuple(parts))
        return structures

    def _create_folders(self):
        structures = self._collect_structures()
        if not structures:
            QMessageBox.information(self, "提示", "请先在表格中粘贴或输入文件夹结构。")
            return
        root = self._root_path()
        items = self._svc.build_folder_paths(root, structures)
        existing = sum(1 for it in items if it.exists)
        reply = QMessageBox.question(
            self,
            "确认创建",
            f"将在 {root} 下创建 {len(items)} 个文件夹({existing} 个已存在,将合并)。",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = self._svc.create_folders(items, ConflictStrategy.MERGE)
        QMessageBox.information(
            self,
            "完成" if result.success else "出错",
            f"新建 {result.created_count}, 共 {result.total_count}"
            + (f"\n{result.error_message}" if result.error_message else ""),
        )

    def _open_root(self):
        import os
        import sys

        root = str(self._root_path())
        if sys.platform == "win32":
            os.startfile(root)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", root])
        else:
            import subprocess

            subprocess.Popen(["xdg-open", root])

    def closeEvent(self, event):
        super().closeEvent(event)
