"""历史记录对话框:查看各工具操作历史(基于 JsonHistoryStore)。"""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from file_toolbox.common.history import JsonHistoryStore


class HistoryDialog(QDialog):
    """历史记录查看对话框。传入 JsonHistoryStore 与工具名。"""

    def __init__(self, history_store: JsonHistoryStore, tool: str = "rename", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"历史记录 - {tool}")
        self.resize(500, 400)
        self._history = history_store
        self._tool = tool

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()

    def _load(self):
        self.list_widget.clear()
        records = self._history.get_records(self._tool, limit=0)
        if not records:
            self.list_widget.addItem("(无历史记录)")
            return
        for r in reversed(records):
            undone = "[已撤销] " if r.get("undone") else ""
            data = r.get("data", {})
            n = len(data.get("rename_map", data.get("files", [])))
            label = f"#{r['id']}  {r['timestamp'][:19]}  {n} 项 {undone}"
            self.list_widget.addItem(QListWidgetItem(label))
