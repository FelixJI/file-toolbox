"""考勤预览的专属 Model:数据行是唯一身份,排序/筛选只影响显示。

分组表与人员表分别对应 core.form_state 的 GroupPreviewRow 与两种员工行;
模型行序即业务身份(名单模式工号、非名单模式(原组, 姓名)),视图经
QSortFilterProxyModel 排序或筛选不会改变回收时应用到的人员。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from file_toolbox.core.attendance.form_state import (
    GroupEmployeePreviewRow,
    GroupPreviewRow,
    PreviewRows,
    RosterEmployeePreviewRow,
)

_GROUP_ROSTER_HEADERS = ("名单分组", "别名", "人数", "明细 Sheet", "汇总 Sheet")
_GROUP_PLAIN_HEADERS = ("输出考勤组", "人数", "明细 Sheet", "汇总 Sheet")
_EMPLOYEE_ROSTER_HEADERS = ("导出", "工号", "姓名", "部门", "名单分组", "别名", "状态")
_EMPLOYEE_PLAIN_HEADERS = ("姓名", "原考勤组", "输出考勤组", "未匹配")
# B008:模型方法默认 parent 用模块级单例(QModelIndex 是轻量值类型,可安全共享)。
_ROOT_INDEX = QModelIndex()


class GroupPreviewModel(QAbstractTableModel):
    """分组预览:名单模式可编辑别名/Sheet 名,非名单模式可编辑 Sheet 名。"""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[GroupPreviewRow] = []
        self._roster_mode = False

    def rowCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX
    ) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX
    ) -> int:
        return 0 if parent.isValid() else len(self._headers())

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self._headers())
        ):
            return self._headers()[section]
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.ItemIsEnabled
        result = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self._is_editable(index.column()):
            result |= Qt.ItemFlag.ItemIsEditable
        return result

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return None
        row = self._rows[index.row()]
        if self._roster_mode:
            values: tuple[str, ...] = (
                row.attendance_group,
                row.group_alias,
                str(row.employee_count),
                row.detail_sheet,
                row.summary_sheet,
            )
        else:
            values = (
                row.attendance_group,
                str(row.employee_count),
                row.detail_sheet,
                row.summary_sheet,
            )
        if not 0 <= index.column() < len(values):
            return None
        return values[index.column()]

    def setData(  # noqa: N802
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: object,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if (
            role != Qt.ItemDataRole.EditRole
            or not index.isValid()
            or not 0 <= index.row() < len(self._rows)
            or not self._is_editable(index.column())
        ):
            return False
        text = str(value)
        row = self._rows[index.row()]
        if self._roster_mode:
            if index.column() == 1:
                new_row = replace(row, group_alias=text)
            elif index.column() == 3:
                new_row = replace(row, detail_sheet=text)
            else:
                new_row = replace(row, summary_sheet=text)
        else:
            new_row = (
                replace(row, detail_sheet=text)
                if index.column() == 2
                else replace(row, summary_sheet=text)
            )
        self._rows[index.row()] = new_row
        self.dataChanged.emit(index, index, (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole))
        return True

    def set_rows(self, rows: Sequence[GroupPreviewRow], *, roster_mode: bool) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self._roster_mode = roster_mode
        self.endResetModel()

    def set_mode(self, roster_mode: bool) -> None:
        self.beginResetModel()
        self._roster_mode = roster_mode
        self._rows = []
        self.endResetModel()

    def clear(self) -> None:
        self.beginResetModel()
        self._rows = []
        self.endResetModel()

    def rows(self) -> tuple[GroupPreviewRow, ...]:
        return tuple(self._rows)

    def _headers(self) -> tuple[str, ...]:
        return _GROUP_ROSTER_HEADERS if self._roster_mode else _GROUP_PLAIN_HEADERS

    def _is_editable(self, column: int) -> bool:
        return column in ((1, 3, 4) if self._roster_mode else (2, 3))


class EmployeePreviewModel(QAbstractTableModel):
    """人员预览:名单模式可勾选导出,非名单模式可调整输出考勤组。"""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._roster_rows: list[RosterEmployeePreviewRow] = []
        self._group_rows: list[GroupEmployeePreviewRow] = []
        self._roster_mode = False
        self._target_editable = False

    def rowCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._roster_rows) if self._roster_mode else len(self._group_rows)

    def columnCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX
    ) -> int:
        if parent.isValid():
            return 0
        return 7 if self._roster_mode else 4

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        headers = _EMPLOYEE_ROSTER_HEADERS if self._roster_mode else _EMPLOYEE_PLAIN_HEADERS
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(headers)
        ):
            return headers[section]
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.ItemIsEnabled
        result = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self._roster_mode:
            if index.column() == 0:
                result |= Qt.ItemFlag.ItemIsUserCheckable
        elif index.column() == 2 and self._target_editable:
            result |= Qt.ItemFlag.ItemIsEditable
        return result

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < self.rowCount():
            return None
        column = index.column()
        if self._roster_mode:
            roster_row = self._roster_rows[index.row()]
            if column == 0:
                if role == Qt.ItemDataRole.CheckStateRole:
                    return Qt.CheckState.Checked if roster_row.exported else Qt.CheckState.Unchecked
                return None
            if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                return None
            roster_values = (
                roster_row.employee_id,
                roster_row.name,
                roster_row.department,
                roster_row.target_group,
                roster_row.group_alias,
                roster_row.status,
            )
            if not 1 <= column <= 6:
                return None
            return roster_values[column - 1]
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return None
        group_row = self._group_rows[index.row()]
        group_values = (
            group_row.name,
            group_row.source_group,
            group_row.target_group,
            group_row.unmatched,
        )
        if not 0 <= column < len(group_values):
            return None
        return group_values[column]

    def setData(  # noqa: N802
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: object,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if not index.isValid() or not 0 <= index.row() < self.rowCount():
            return False
        if self._roster_mode:
            if role != Qt.ItemDataRole.CheckStateRole or index.column() != 0:
                return False
            state = value if isinstance(value, Qt.CheckState) else Qt.CheckState(value)
            exported = state == Qt.CheckState.Checked
            self._roster_rows[index.row()] = replace(
                self._roster_rows[index.row()], exported=exported
            )
            self.dataChanged.emit(index, index, (Qt.ItemDataRole.CheckStateRole,))
            return True
        if role != Qt.ItemDataRole.EditRole or index.column() != 2 or not self._target_editable:
            return False
        self._group_rows[index.row()] = replace(
            self._group_rows[index.row()], target_group=str(value)
        )
        self.dataChanged.emit(index, index, (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole))
        return True

    def set_rows(self, rows: PreviewRows) -> None:
        self.beginResetModel()
        self._roster_mode = rows.roster_mode
        self._target_editable = rows.target_editable
        self._roster_rows = list(rows.roster_employees)
        self._group_rows = list(rows.group_employees)
        self.endResetModel()

    def set_mode(self, roster_mode: bool) -> None:
        self.beginResetModel()
        self._roster_mode = roster_mode
        self._target_editable = False
        self._roster_rows = []
        self._group_rows = []
        self.endResetModel()

    def clear(self) -> None:
        self.beginResetModel()
        self._roster_rows = []
        self._group_rows = []
        self.endResetModel()

    def roster_rows(self) -> tuple[RosterEmployeePreviewRow, ...]:
        return tuple(self._roster_rows)

    def group_rows(self) -> tuple[GroupEmployeePreviewRow, ...]:
        return tuple(self._group_rows)
