"""建文件夹 Tab GUI 测试:红框隐藏、预览、校验、按钮启用状态。

不触发真实文件创建,仅校验控件状态与逻辑。
"""

import pytest

# 用 QtWidgets 子模块做 importorskip(而非顶层 PySide6):后者只校验包可 import,
# 不触发 libEGL/libGL 原生库加载;真实 import QtWidgets 才会,缺库时应跳过而非收集失败。
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QTableWidgetItem  # noqa: E402

from file_toolbox.core.batch_mkdir import ConflictStrategy  # noqa: E402
from file_toolbox.gui.dialogs.mkdir_tab import BatchFolderCreatorDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dlg(app):
    return BatchFolderCreatorDialog()


def _fill_row(dlg, row, *values):
    """填充一行单元格。"""
    dlg.ui.table_paste.setRowCount(max(dlg.ui.table_paste.rowCount(), row + 1))
    for col, val in enumerate(values):
        dlg.ui.table_paste.setItem(row, col, QTableWidgetItem(val))


# ---------- 红框 / 错误提示 ----------


def test_error_label_hidden_by_default(dlg):
    """label_error 带红色边框样式,默认必须隐藏,否则显示空红框。"""
    dlg.show()
    QApplication.processEvents()
    assert dlg.ui.label_error.isHidden()


def test_show_error_then_clear(dlg):
    dlg.show()
    dlg._show_error("出错了")
    QApplication.processEvents()
    assert not dlg.ui.label_error.isHidden()
    assert dlg.ui.label_error.text() == "出错了"
    dlg._show_error("")
    QApplication.processEvents()
    assert dlg.ui.label_error.isHidden()


# ---------- 按钮启用状态 ----------


def test_create_button_disabled_when_empty(dlg):
    assert not dlg.ui.btn_create_folders.isEnabled()
    assert not dlg.ui.btn_fix_special_chars.isEnabled()


def test_create_button_enabled_when_filled(dlg):
    _fill_row(dlg, 0, "项目A", "文档")
    dlg._refresh_ui_state()
    assert dlg.ui.btn_create_folders.isEnabled()
    assert dlg.ui.btn_fix_special_chars.isEnabled()


# ---------- 预览 ----------


def test_preview_populated_from_table(dlg):
    _fill_row(dlg, 0, "项目A", "文档")
    _fill_row(dlg, 1, "项目B")
    dlg._refresh_ui_state()
    assert dlg.ui.tree_preview.topLevelItemCount() == 2
    # 项目A 下应有子节点"文档"
    top = dlg.ui.tree_preview.topLevelItem(0)
    assert top.text(0) == "项目A"
    assert top.childCount() == 1
    assert top.child(0).text(0) == "文档"


def test_preview_cleared_on_clear(dlg):
    _fill_row(dlg, 0, "项目A")
    dlg._refresh_ui_state()
    dlg._clear()
    assert dlg.ui.tree_preview.topLevelItemCount() == 0


# ---------- 校验 ----------


def test_invalid_names_detected(dlg):
    _fill_row(dlg, 0, "a*b", "c?d")
    structures = dlg._collect_structures()
    invalid = dlg._find_invalid_names(structures)
    assert "a*b" in invalid
    assert "c?d" in invalid


def test_collect_structures_ignores_empty_rows(dlg):
    _fill_row(dlg, 0, "项目A")
    dlg.ui.table_paste.setRowCount(2)  # 第二行全空
    structures = dlg._collect_structures()
    assert structures == [("项目A",)]


# ---------- 冲突策略 ----------


def test_default_strategy_is_merge(dlg):
    assert dlg._selected_strategy() == ConflictStrategy.MERGE


def test_strategy_switches_to_skip(dlg):
    dlg._combo_conflict.setCurrentText("跳过已存在")
    assert dlg._selected_strategy() == ConflictStrategy.SKIP
