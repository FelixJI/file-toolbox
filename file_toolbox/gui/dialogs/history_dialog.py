"""历史记录对话框:查看各工具操作历史(基于 JsonHistoryStore)。

rename 历史额外提供「撤销」按钮:把 rename_map 反转后执行反向重命名。
其余工具(PDF/文件夹/发票)操作不可逆,仅展示记录。
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_rename import FileRenameService


def _summary_label(tool: str, data: dict) -> str:
    """根据工具类型与记录数据,生成一行摘要。"""
    if tool == "rename":
        n = len(data.get("rename_map", {}))
        return f"{n} 个文件"
    if tool == "replace":
        n = len(data.get("files", []))
        return f"{n} 个文件"
    if tool == "pdf":
        files = data.get("files", [])
        ok = data.get("success", 0)
        return f"{ok}/{len(files)} 个成功"
    if tool == "mkdir":
        created = data.get("created", 0)
        skipped = data.get("skipped", 0)
        strategy = data.get("strategy", "?")
        root = data.get("root", "")
        return f"新建 {created}, 跳过 {skipped} [{strategy}] {root}"
    if tool == "invoice":
        inv = data.get("invoice_count", 0)
        files = data.get("file_count", 0)
        fmt = data.get("fmt", "?")
        return f"{inv} 张发票 / {files} 文件 [{fmt}]"
    return str(data)[:40]


class HistoryDialog(QDialog):
    """历史记录查看对话框。传入 JsonHistoryStore 与工具名。

    tool == "rename" 时额外显示「撤销」按钮(反向重命名)。
    """

    def __init__(self, history_store: JsonHistoryStore, tool: str = "rename", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"历史记录 - {tool}")
        self.resize(560, 440)
        self._history = history_store
        self._tool = tool

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.list_widget)

        # rename 支持「撤销」:把 rename_map 反转后执行反向重命名
        self.btn_undo = QPushButton("撤销选中项(反向重命名)")
        self.btn_undo.setVisible(tool == "rename")
        self.btn_undo.clicked.connect(self._undo_selected)
        layout.addWidget(self.btn_undo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()

    def _load(self):
        self.list_widget.clear()
        records = self._history.get_records(self._tool, limit=0)
        if not records:
            self.list_widget.addItem("(无历史记录)")
            self.btn_undo.setEnabled(False)
            return
        self.btn_undo.setEnabled(self._tool == "rename")
        for r in reversed(records):
            undone = "[已撤销] " if r.get("undone") else ""
            summary = _summary_label(self._tool, r.get("data", {}))
            label = f"#{r['id']}  {r['timestamp'][:19]}  {summary}  {undone}"
            item = QListWidgetItem(label)
            # 存记录 id,供撤销使用
            item.setData(0x0100, r["id"])
            self.list_widget.addItem(item)

    def _undo_selected(self):
        """对选中的 rename 历史记录执行反向重命名并标记已撤销。"""
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "提示", "请先选择一条记录。")
            return
        rid = item.data(0x0100)
        if rid is None:
            return
        record = self._history.get_record(self._tool, rid)
        if record is None:
            QMessageBox.warning(self, "错误", "找不到该记录。")
            return
        rename_map = record.get("data", {}).get("rename_map", {})
        if not rename_map:
            QMessageBox.information(self, "提示", "该记录无可撤销的映射。")
            return

        # 反转:{原:新} -> {新:原},用 Path 包装
        reverse_map: dict[Path, Path] = {}
        for old_str, new_str in rename_map.items():
            new_path = Path(new_str)
            old_path = Path(old_str)
            # 反向时跳过已撤销(目标不存在)或不一致的情况,由 service 兜底
            reverse_map[new_path] = old_path

        reply = QMessageBox.question(
            self,
            "确认撤销",
            f"将把 {len(reverse_map)} 个文件改回原名。仅在文件未被进一步移动/重命名时有效。继续?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        svc = FileRenameService()
        count, errors = svc.execute_rename(reverse_map)
        self._history.mark_undone(self._tool, rid)
        msg = f"已反向重命名 {count} 个文件。"
        if errors:
            msg += "\n部分失败:\n" + "\n".join(errors)
        QMessageBox.information(self, "撤销完成", msg)
        self._load()
