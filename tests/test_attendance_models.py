"""考勤预览 Model 的数据行、可编辑性与排序身份测试(offscreen Qt)。"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSortFilterProxyModel, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from file_toolbox.core.attendance.form_state import (  # noqa: E402
    GroupEmployeePreviewRow,
    GroupPreviewRow,
    PreviewRows,
    RosterEmployeePreviewRow,
)
from file_toolbox.gui.dialogs.attendance_models import (  # noqa: E402
    EmployeePreviewModel,
    GroupPreviewModel,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _group_rows() -> tuple[GroupPreviewRow, ...]:
    return (
        GroupPreviewRow("售后组", "售后明细", "售后汇总", "正式", 2),
        GroupPreviewRow("管理组", "管理明细", "管理汇总", "", 1),
    )


def test_group_model_roster_columns_and_editable_fields(app):
    model = GroupPreviewModel()
    model.set_rows(_group_rows(), roster_mode=True)

    assert model.columnCount() == 5
    assert model.rowCount() == 2
    assert [model.headerData(i, Qt.Orientation.Horizontal) for i in range(5)] == [
        "名单分组",
        "别名",
        "人数",
        "明细 Sheet",
        "汇总 Sheet",
    ]
    # 组名与人数只读,别名/明细/汇总可编辑
    assert not model.flags(model.index(0, 0)) & Qt.ItemFlag.ItemIsEditable
    assert not model.flags(model.index(0, 2)) & Qt.ItemFlag.ItemIsEditable
    for column in (1, 3, 4):
        assert model.flags(model.index(0, column)) & Qt.ItemFlag.ItemIsEditable

    assert model.setData(model.index(1, 1), "劳务")
    assert model.rows()[1].group_alias == "劳务"
    assert model.setData(model.index(1, 3), "改名明细")
    assert model.rows()[1].detail_sheet == "改名明细"
    assert model.setData(model.index(1, 4), "改名汇总")
    assert model.rows()[1].summary_sheet == "改名汇总"
    # 只读列拒绝编辑
    assert not model.setData(model.index(1, 0), "改名分组")
    assert not model.setData(model.index(1, 2), "9")
    assert model.rows()[1].attendance_group == "管理组"


def test_group_model_plain_columns_and_editable_fields(app):
    model = GroupPreviewModel()
    model.set_rows(_group_rows(), roster_mode=False)

    assert model.columnCount() == 4
    assert [model.headerData(i, Qt.Orientation.Horizontal) for i in range(4)] == [
        "输出考勤组",
        "人数",
        "明细 Sheet",
        "汇总 Sheet",
    ]
    assert not model.flags(model.index(0, 0)) & Qt.ItemFlag.ItemIsEditable
    assert not model.flags(model.index(0, 1)) & Qt.ItemFlag.ItemIsEditable
    for column in (2, 3):
        assert model.flags(model.index(0, column)) & Qt.ItemFlag.ItemIsEditable

    assert model.data(model.index(0, 1)) == "2"
    assert model.setData(model.index(0, 2), "自定义明细")
    assert model.rows()[0].detail_sheet == "自定义明细"
    # roster 模式专属列不可用
    assert model.data(model.index(0, 4)) is None
    assert not model.setData(model.index(0, 4), "x")


def test_employee_model_roster_check_toggle(app):
    model = EmployeePreviewModel()
    model.set_rows(
        PreviewRows(
            roster_mode=True,
            target_editable=False,
            roster_employees=(
                RosterEmployeePreviewRow(
                    "001", "张三", "市场部", "徐州中车", "正式", True, "已匹配"
                ),
                RosterEmployeePreviewRow(
                    "wb002", "李四", "市场部", "徐州中车", "正式", False, "已排除"
                ),
            ),
        )
    )

    assert model.columnCount() == 7
    assert model.rowCount() == 2
    assert model.flags(model.index(0, 0)) & Qt.ItemFlag.ItemIsUserCheckable
    assert not model.flags(model.index(0, 1)) & Qt.ItemFlag.ItemIsEditable
    assert model.data(model.index(0, 0), Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert model.data(model.index(1, 0), Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert model.data(model.index(1, 0)) is None  # 勾选列无显示文本
    assert model.data(model.index(1, 1)) == "wb002"
    assert model.data(model.index(1, 6)) == "已排除"

    assert model.setData(model.index(0, 0), Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    assert model.roster_rows()[0].exported is False
    assert model.data(model.index(0, 0), Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    # 只读列拒绝文本编辑
    assert not model.setData(model.index(0, 1), "改名")


def test_employee_model_plain_target_editability(app):
    model = EmployeePreviewModel()
    rows = PreviewRows(
        roster_mode=False,
        target_editable=False,
        group_employees=(GroupEmployeePreviewRow("张三", "售后组", "售后组", ""),),
    )
    model.set_rows(rows)

    assert model.columnCount() == 4
    assert model.data(model.index(0, 2)) == "售后组"
    # 预览无分组计数时目标列只读
    assert not model.flags(model.index(0, 2)) & Qt.ItemFlag.ItemIsEditable
    assert not model.setData(model.index(0, 2), "管理组")

    rows = PreviewRows(
        roster_mode=False,
        target_editable=True,
        group_employees=(GroupEmployeePreviewRow("张三", "售后组", "售后组", "2日: 异常"),),
    )
    model.set_rows(rows)
    assert model.flags(model.index(0, 2)) & Qt.ItemFlag.ItemIsEditable
    assert model.setData(model.index(0, 2), "管理组")
    assert model.group_rows()[0].target_group == "管理组"
    assert model.group_rows()[0].source_group == "售后组"


def test_proxy_sorting_keeps_model_row_identity(app):
    """显示排序改变视图行序,源模型数据行(身份)与回收结果不变。"""
    model = EmployeePreviewModel()
    model.set_rows(
        PreviewRows(
            roster_mode=False,
            target_editable=True,
            group_employees=(
                GroupEmployeePreviewRow("张三", "售后组", "售后组", ""),
                GroupEmployeePreviewRow("李四", "管理组", "管理组", ""),
                GroupEmployeePreviewRow("王五", "售后组", "售后组", ""),
            ),
        )
    )
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.sort(0, Qt.SortOrder.AscendingOrder)

    # 视图首行是姓名排序后的“张三”,但源模型行序保持预览顺序
    assert proxy.data(proxy.index(0, 0)) == "张三"
    assert [row.name for row in model.group_rows()] == ["张三", "李四", "王五"]

    # 通过排序视图编辑首行(张三)的输出考勤组,落到正确的数据行
    assert proxy.setData(proxy.index(0, 2), "管理组")
    moved = [row for row in model.group_rows() if row.target_group != row.source_group]
    assert [(row.name, row.source_group, row.target_group) for row in moved] == [
        ("张三", "售后组", "管理组")
    ]


def test_models_clear_and_mode_reset(app):
    group_model = GroupPreviewModel()
    group_model.set_rows(_group_rows(), roster_mode=True)
    group_model.clear()
    assert group_model.rowCount() == 0
    assert group_model.columnCount() == 5  # 清空行但保持当前模式

    employee_model = EmployeePreviewModel()
    employee_model.set_rows(
        PreviewRows(
            roster_mode=True,
            target_editable=False,
            roster_employees=(RosterEmployeePreviewRow("001", "张三", "", "A", "", True, ""),),
        )
    )
    employee_model.set_mode(False)
    assert employee_model.rowCount() == 0
    assert employee_model.columnCount() == 4
    assert employee_model.headerData(2, Qt.Orientation.Horizontal) == "输出考勤组"
