from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableView

_ROOT_INDEX = QModelIndex()


class FileListModel(QAbstractListModel):
    """文件数据为权威，GUI 线程一次通知一批插入。"""

    def __init__(self, files: list[Path], full_path: bool, parent: QObject) -> None:
        super().__init__(parent)
        self.files = files
        self.full_path = full_path

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.files)

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self.files):
            return None
        path = self.files[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return str(path) if self.full_path else path.name
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(path)
        return None

    def append_paths(self, paths: list[Path]) -> None:
        if paths:
            start = len(self.files)
            self.beginInsertRows(QModelIndex(), start, start + len(paths) - 1)
            self.files.extend(paths)
            self.endInsertRows()

    def replace_paths(self, paths: list[Path]) -> None:
        self.beginResetModel()
        self.files[:] = paths
        self.endResetModel()


class FileTableModel(QAbstractTableModel):
    """预览/结果只保存数据，避免为每个单元格分配 Qt item。"""

    def __init__(self, headers: list[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.headers = headers
        self.rows: list[tuple[list[str], QColor | None]] = []

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        values, color = self.rows[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return values[index.column()]
        if role == Qt.ItemDataRole.BackgroundRole:
            return color
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                self.headers[section] if orientation == Qt.Orientation.Horizontal else section + 1
            )
        return None

    def replace_rows(self, rows: Sequence[tuple[list[str], QColor | None]]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def append_rows(self, rows: Sequence[tuple[list[str], QColor | None]]) -> None:
        if rows:
            start = len(self.rows)
            self.beginInsertRows(QModelIndex(), start, start + len(rows) - 1)
            self.rows.extend(rows)
            self.endInsertRows()

    def update_rows(self, rows: Sequence[tuple[list[str], QColor | None]]) -> None:
        count = min(len(rows), len(self.rows))
        if count:
            self.rows[:count] = list(rows[:count])
            self.dataChanged.emit(self.index(0, 0), self.index(count - 1, len(self.headers) - 1))


def table_model(view: QTableView) -> FileTableModel:
    model = view.model()
    assert isinstance(model, FileTableModel)
    return model
