"""建文件夹 Tab GUI 测试:红框隐藏、预览、校验、按钮启用状态。

不触发真实文件创建,仅校验控件状态与逻辑。
"""

import pytest

# 用 QtWidgets 子模块做 importorskip(而非顶层 PySide6):后者只校验包可 import,
# 不触发 libEGL/libGL 原生库加载;真实 import QtWidgets 才会,缺库时应跳过而非收集失败。
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QTableWidgetItem  # noqa: E402

from file_toolbox.core.batch_mkdir import ConflictStrategy  # noqa: E402
from file_toolbox.gui.dialogs.mkdir_tab import _INITIAL_ROWS, BatchFolderCreatorDialog  # noqa: E402


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


class _FakeClipboard:
    """离屏平台插件的剪贴板行为不保证跨平台,测试注入 fake 避免依赖。"""

    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


def _paste(dlg, monkeypatch, text):
    """把 text 注入剪贴板并按 Ctrl+V(走 eventFilter 的真实按键路径)。"""
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: _FakeClipboard(text)))
    QTest.keyClick(dlg.ui.table_paste, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)


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


# ---------- 表格可输入性(回归:0 行表格导致整个 Tab 无法使用) ----------


def test_table_has_initial_editable_rows(dlg):
    """初始预置空行:有可点击/可输入的单元格,且按钮仍禁用(空行不构成结构)。"""
    assert dlg.ui.table_paste.rowCount() == _INITIAL_ROWS >= 1
    assert not dlg.ui.btn_create_folders.isEnabled()


def test_clear_restores_initial_rows(dlg):
    """清空后回到初始空行数(而非 0 行),保持可继续输入/粘贴。"""
    _fill_row(dlg, 0, "项目A")
    dlg._clear()
    assert dlg.ui.table_paste.rowCount() == _INITIAL_ROWS
    assert dlg.ui.table_paste.rowCount() > 0


def test_typing_in_last_row_appends_blank_row(dlg):
    """末行有输入 → 自动追加一个空行,保证可继续向下输入。"""
    last = dlg.ui.table_paste.rowCount() - 1
    _fill_row(dlg, last, "项目A")
    assert dlg.ui.table_paste.rowCount() == last + 2


# ---------- Ctrl+V 粘贴 TSV(回归:QTableWidget 无多单元格粘贴,实测粘贴无效) ----------


def test_paste_fills_table_and_enables_buttons(dlg, monkeypatch):
    _paste(dlg, monkeypatch, "项目A\t文档\n项目B\t\t资料")
    assert dlg.ui.table_paste.item(0, 0).text() == "项目A"
    assert dlg.ui.table_paste.item(0, 1).text() == "文档"
    assert dlg.ui.table_paste.item(1, 0).text() == "项目B"
    assert dlg.ui.table_paste.item(1, 2).text() == "资料"
    assert dlg.ui.btn_create_folders.isEnabled()
    assert dlg.ui.btn_fix_special_chars.isEnabled()


def test_paste_populates_preview(dlg, monkeypatch):
    _paste(dlg, monkeypatch, "项目A\t文档\n项目B")
    assert dlg.ui.tree_preview.topLevelItemCount() == 2
    assert dlg.ui.tree_preview.topLevelItem(0).childCount() == 1


def test_paste_overwrites_existing_cell(dlg, monkeypatch):
    """粘贴覆盖落点已有内容(Excel 语义)。"""
    _fill_row(dlg, 0, "旧内容")
    dlg.ui.table_paste.setCurrentCell(0, 0)
    _paste(dlg, monkeypatch, "新内容")
    assert dlg.ui.table_paste.item(0, 0).text() == "新内容"


def test_paste_at_selected_cell(dlg, monkeypatch):
    """有选中单元格时从该位置开始粘贴,而非固定 (0,0)。"""
    dlg.ui.table_paste.setCurrentCell(1, 1)
    _paste(dlg, monkeypatch, "a\tb")
    assert dlg.ui.table_paste.item(1, 1).text() == "a"
    assert dlg.ui.table_paste.item(1, 2).text() == "b"
    assert dlg.ui.table_paste.item(0, 0) is None  # 未触及 (0,0)


def test_paste_expands_columns_with_headers(dlg, monkeypatch):
    """粘贴超过 3 列 → 扩列并补中文列头,状态与预览同步刷新。"""
    _paste(dlg, monkeypatch, "一\t二\t三\t四\t五")
    assert dlg.ui.table_paste.columnCount() == 5
    assert dlg.ui.table_paste.horizontalHeaderItem(3).text() == "四级文件夹"
    assert dlg.ui.table_paste.horizontalHeaderItem(4).text() == "五级文件夹"
    assert dlg.ui.btn_create_folders.isEnabled()


def test_paste_expands_rows_beyond_initial(dlg, monkeypatch):
    """粘贴行数超过初始行数 → 扩行到恰好容纳。"""
    lines = "\n".join(f"行{i}" for i in range(_INITIAL_ROWS + 3))
    _paste(dlg, monkeypatch, lines)
    assert dlg.ui.table_paste.rowCount() == _INITIAL_ROWS + 3
    assert dlg.ui.table_paste.item(_INITIAL_ROWS + 2, 0).text() == f"行{_INITIAL_ROWS + 2}"


def test_paste_empty_clipboard_is_noop(dlg, monkeypatch):
    """空剪贴板/纯空白文本 → 不处理、不抛错。"""
    _paste(dlg, monkeypatch, "")
    assert dlg.ui.table_paste.item(0, 0) is None
    assert not dlg.ui.btn_create_folders.isEnabled()


def test_paste_crlf_normalized(dlg, monkeypatch):
    """Excel 在 Windows 复制的 CRLF 文本按行正确落入表格。"""
    _paste(dlg, monkeypatch, "项目A\t文档\r\n项目B")
    assert dlg.ui.table_paste.item(0, 0).text() == "项目A"
    assert dlg.ui.table_paste.item(1, 0).text() == "项目B"
    assert dlg._collect_structures() == [("项目A", "文档"), ("项目B",)]
