"""mkdir_tab 未覆盖分支补充测试。

覆盖:_browse_root、_refresh_preview 分支、_fix_special_chars、_make_skip_callback、
_create_folders 各路径、_open_root、closeEvent。
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.gui.dialogs.mkdir_tab import BatchFolderCreatorDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dlg(app, tmp_path):
    d = BatchFolderCreatorDialog()
    d._history = JsonHistoryStore(tmp_path)
    return d


def _fill_row(dlg, row, *values):
    """填充一行单元格。"""
    dlg.ui.table_paste.setRowCount(max(dlg.ui.table_paste.rowCount(), row + 1))
    for col, val in enumerate(values):
        from PySide6.QtWidgets import QTableWidgetItem

        dlg.ui.table_paste.setItem(row, col, QTableWidgetItem(val))


# ---------------------------------------------------------------------------
# _browse_root(行 115-118)
# ---------------------------------------------------------------------------


def test_browse_root_sets_path(dlg, monkeypatch, tmp_path):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    dlg._browse_root()
    assert dlg.ui.line_edit_root_path.text() == str(tmp_path)


def test_browse_root_cancelled(dlg, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    dlg._browse_root()
    assert dlg.ui.line_edit_root_path.text() == ""


# ---------------------------------------------------------------------------
# _show_error(行 109-111,已部分覆盖)
# ---------------------------------------------------------------------------


def test_show_error_empty_hides(dlg):
    dlg._show_error("")
    assert dlg.ui.label_error.isHidden()


# ---------------------------------------------------------------------------
# _refresh_preview 分支(行 150-156)
# ---------------------------------------------------------------------------


def test_refresh_preview_empty_no_tree(dlg):
    """无结构 → 不填充树(行 139-140)。"""
    dlg._refresh_preview()
    assert dlg.ui.tree_preview.topLevelItemCount() == 0


def test_refresh_preview_builds_tree(dlg, tmp_path):
    """有结构 → 构建预览树,含已存在节点灰显(行 145-163)。"""
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    (tmp_path / "exists").mkdir()  # 已存在 → 灰显分支
    _fill_row(dlg, 0, "exists", "sub")
    dlg._refresh_preview()
    assert dlg.ui.tree_preview.topLevelItemCount() >= 1


def test_refresh_preview_shared_prefix_dedup(dlg, tmp_path):
    """共享前缀的节点不重复创建(行 150-152 continue 分支)。"""
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    _fill_row(dlg, 0, "a", "b")
    _fill_row(dlg, 1, "a", "c")  # 'a' 共享
    dlg._refresh_preview()
    # 顶层只有 'a' 一个
    assert dlg.ui.tree_preview.topLevelItemCount() == 1


# ---------------------------------------------------------------------------
# _fix_special_chars(行 167-202)
# ---------------------------------------------------------------------------


def test_fix_special_chars_replace(dlg, monkeypatch):
    """选'替换为下划线' → 替换非法字符(行 172-202)。"""
    _fill_row(dlg, 0, "a*b")
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("替换为下划线", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg._fix_special_chars()
    assert dlg.ui.table_paste.item(0, 0).text() == "a_b"


def test_fix_special_chars_delete(dlg, monkeypatch):
    """选'删除' → 删除非法字符。"""
    _fill_row(dlg, 0, "a*b")
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("删除", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg._fix_special_chars()
    assert dlg.ui.table_paste.item(0, 0).text() == "ab"


def test_fix_special_chars_cancelled(dlg, monkeypatch):
    """取消 → 不处理(行 180-181)。"""
    _fill_row(dlg, 0, "a*b")
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("替换为下划线", False))
    dlg._fix_special_chars()
    assert dlg.ui.table_paste.item(0, 0).text() == "a*b"


def test_fix_special_chars_no_change(dlg, monkeypatch):
    """无非法字符 → changed=0。"""
    _fill_row(dlg, 0, "normal")
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("替换为下划线", True))
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._fix_special_chars()
    assert info_calls


# ---------------------------------------------------------------------------
# _make_skip_callback(行 230-246)
# ---------------------------------------------------------------------------


def test_make_skip_callback_yes(dlg, monkeypatch):
    """callback:question Yes → 返回 True(跳过)。"""
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    cb = dlg._make_skip_callback()
    from file_toolbox.core.batch_mkdir import FolderStructureItem

    assert cb(FolderStructureItem(path=Path("x"), levels=("x",))) is True


def test_make_skip_callback_no(dlg, monkeypatch):
    """callback:question No → 返回 False(保留)。"""
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    cb = dlg._make_skip_callback()
    from file_toolbox.core.batch_mkdir import FolderStructureItem

    assert cb(FolderStructureItem(path=Path("x"), levels=("x",))) is False


# ---------------------------------------------------------------------------
# _create_folders(行 248-304)
# ---------------------------------------------------------------------------


def test_create_folders_no_structures_warns(dlg, monkeypatch):
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    dlg._create_folders()
    assert info_calls


def test_create_folders_invalid_chars_shows_error(dlg, tmp_path, monkeypatch):
    """含非法字符 → show_error(行 254-263)。"""
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    _fill_row(dlg, 0, "a*b")  # 非法 *
    dlg._create_folders()
    assert not dlg.ui.label_error.isHidden()
    assert "非法字符" in dlg.ui.label_error.text()


def test_create_folders_many_invalid_etc_suffix(dlg, tmp_path):
    """超过 5 个非法名 → 加 ' 等'(行 260)。"""
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    # 6 行,每行一个含非法字符的文件夹名
    for i in range(6):
        _fill_row(dlg, i, f"a{i}*b")
    dlg._create_folders()
    assert "等" in dlg.ui.label_error.text()


def test_create_folders_success_merge(dlg, monkeypatch, tmp_path):
    """确认 Yes + merge → 创建成功(行 266-303)。"""
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    _fill_row(dlg, 0, "newdir")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    dlg._create_folders()
    assert (tmp_path / "newdir").exists()
    assert info_calls


def test_create_folders_declined(dlg, monkeypatch, tmp_path):
    """确认 No → 不创建(行 281-282)。"""
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    _fill_row(dlg, 0, "newdir")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dlg._create_folders()
    assert not (tmp_path / "newdir").exists()


def test_create_folders_confirm_strategy(dlg, monkeypatch, tmp_path):
    """CONFIRM 策略 → 用 skip_callback(行 283-285)。"""
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    (tmp_path / "exists").mkdir()  # 已存在 → 触发 callback
    _fill_row(dlg, 0, "exists")
    # 设 combo 到 CONFIRM
    dlg._combo_conflict.setCurrentText("逐个确认")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg._create_folders()


def test_create_folders_failure_shown(dlg, monkeypatch, tmp_path):
    """create 失败 → information 显示错误(行 300-303)。"""
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    _fill_row(dlg, 0, "newdir")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    # mock create_folders 返回失败
    from file_toolbox.core.batch_mkdir import CreateResult

    monkeypatch.setattr(
        dlg._svc,
        "create_folders",
        lambda *a, **k: CreateResult(0, 0, 1, False, "创建失败原因"),
    )
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._create_folders()
    assert any("创建失败原因" in s for s in info_calls)


# ---------------------------------------------------------------------------
# _open_root(行 306-320)
# ---------------------------------------------------------------------------


def test_open_root_windows(dlg, monkeypatch, tmp_path):
    """win32 → os.startfile(行 311-312)。"""
    import os
    import sys

    monkeypatch.setattr(sys, "platform", "win32")
    started = []
    monkeypatch.setattr(os, "startfile", lambda p: started.append(p), raising=False)
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    dlg._open_root()
    assert started


def test_open_root_darwin(dlg, monkeypatch, tmp_path):
    """darwin → subprocess.Popen(['open', ...])(行 313-316)。"""
    import subprocess
    import sys

    monkeypatch.setattr(sys, "platform", "darwin")
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append(a))
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    dlg._open_root()
    assert calls and "open" in calls[0][0]


def test_open_root_linux(dlg, monkeypatch, tmp_path):
    """linux → subprocess.Popen(['xdg-open', ...])(行 317-320)。"""
    import subprocess
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append(a))
    dlg.ui.line_edit_root_path.setText(str(tmp_path))
    dlg._open_root()
    assert calls and "xdg-open" in calls[0][0]


# ---------------------------------------------------------------------------
# closeEvent(行 322-323)
# ---------------------------------------------------------------------------


def test_close_event(dlg):
    from PySide6.QtGui import QCloseEvent

    dlg.closeEvent(QCloseEvent())  # 不抛即通过
