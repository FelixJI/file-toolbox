"""历史记录对话框:查看各工具操作历史(基于 JsonHistoryStore)。

rename 历史额外提供「撤销」按钮:由核心验证记录并持久化逐项恢复进度。
其余工具(PDF/文件夹/发票/考勤)操作不可逆，仅展示记录。
"""

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_rename import FileRenameService


def _summary_label(tool: str, data: dict[str, Any]) -> str:
    """根据工具类型与记录数据,生成一行摘要。"""
    if not isinstance(data, dict):
        return "记录数据无效"
    if tool == "rename":
        mapping = data.get("rename_map", {})
        n = len(mapping) if isinstance(mapping, dict) else 0
        remaining = data.get("undo_remaining")
        suffix = f", 剩余 {len(remaining)} 个待撤销" if isinstance(remaining, list) else ""
        return f"{n} 个文件" + suffix
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
    if tool == "excel_merge":
        sheets = data.get("sheet_count", 0)
        files = data.get("file_count", 0)
        naming = data.get("naming", "?")
        output = Path(str(data.get("output", ""))).name
        return f"{sheets} 工作表 / {files} 文件 [{naming}] → {output}"
    if tool == "attendance":
        employees = data.get("employee_count", 0)
        year = data.get("year", "?")
        month = data.get("month", "?")
        output = Path(str(data.get("output", ""))).name
        return f"{year}-{month} / {employees} 人 → {output}"
    if tool == "pdf_sort":
        pages = data.get("page_count", 0)
        files = data.get("file_count", 0)
        outputs = data.get("outputs", [])
        order = data.get("order", "?")
        return f"{pages} 页 / {files} 文件 [{order}] → {len(outputs)} 个输出"
    return str(data)[:40]


class HistoryDialog(QDialog):
    """历史记录查看对话框。传入 JsonHistoryStore 与工具名。

    tool == "rename" 时额外显示「撤销」按钮(反向重命名)。
    """

    def __init__(
        self, history_store: JsonHistoryStore, tool: str = "rename", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"历史记录 - {tool}")
        self.resize(560, 440)
        self._history = history_store
        self._tool = tool

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.list_widget)

        # rename 支持由核心校验并恢复尚未撤销的文件。
        self.btn_undo = QPushButton("撤销选中项(反向重命名)")
        self.btn_undo.setVisible(tool == "rename")
        self.btn_undo.clicked.connect(self._undo_selected)
        layout.addWidget(self.btn_undo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()

    def _load(self) -> None:
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

    def _undo_selected(self) -> None:
        """恢复选中记录的剩余文件;全部完成后才标记已撤销。"""
        if self._tool != "rename":
            return
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
        data = record.get("data", {})
        rename_map = data.get("rename_map", {}) if isinstance(data, dict) else {}
        if not isinstance(rename_map, dict) or not rename_map:
            QMessageBox.information(self, "提示", "该记录无可撤销的映射。")
            return

        if record.get("undone"):
            QMessageBox.information(self, "提示", "该记录已经撤销。")
            return

        remaining = data.get("undo_remaining", list(rename_map))
        count = len(remaining) if isinstance(remaining, list) else len(rename_map)
        reply = QMessageBox.question(
            self,
            "确认撤销",
            f"将尝试把剩余 {count} 个文件改回原名。仅恢复可确认归属且原路径未被占用的文件。继续?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        svc = FileRenameService(self._history)
        outcome = svc.undo_record(rid)
        count, errors = outcome.count, outcome.messages
        msg = f"已反向重命名 {count} 个文件。"
        if errors:
            msg += "\n部分失败:\n" + "\n".join(errors)
        QMessageBox.information(self, "撤销结果", msg)
        self._load()
