"""rename_tab GUI 测试:操作增删改、预览、执行、历史、模板(mock 输入对话框)。

不触发真实文件操作的重命名(用 tmp_path 真文件 + mock QMessageBox 确认)。
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from pathlib import Path

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from file_toolbox.gui.dialogs.rename_tab import FileRenamerDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dlg(app, tmp_path):
    """每个测试用独立 tmp_path 的历史/模板存储,避免跨测试残留。

    构造后替换 _history 与 _template_svc 为 tmp_path 隔离版本。
    """
    from file_toolbox.common.history import JsonHistoryStore
    from file_toolbox.core.rename_template import RenameTemplateService

    d = FileRenamerDialog()
    d._history = JsonHistoryStore(tmp_path)
    d._template_svc = RenameTemplateService(tmp_path / "templates.json")
    return d


# ---------------------------------------------------------------------------
# 初始状态
# ---------------------------------------------------------------------------


def test_init_status(dlg):
    assert dlg.ui.label_status.text() == "已选择 0 个文件"
    assert dlg.operations == []


def test_op_labels_complete(dlg):
    """所有操作类型有中文标签。"""
    assert len(dlg._OP_LABELS) == 7


# ---------------------------------------------------------------------------
# 操作增删改(mock _prompt_operation_params)
# ---------------------------------------------------------------------------


def test_add_operation_appends(dlg, monkeypatch):
    """_add_operation:prompt 返回参数 → 加入 operations + 刷新(行 93-99)。"""
    monkeypatch.setattr(dlg, "_prompt_operation_params", lambda t, e=None: {"text": "P_"})
    dlg._add_operation("add_prefix")
    assert len(dlg.operations) == 1
    assert dlg.operations[0] == {"type": "add_prefix", "params": {"text": "P_"}}
    assert dlg.ui.list_operations.count() == 1


def test_add_operation_cancelled_noop(dlg, monkeypatch):
    """prompt 返回 None → 不加(行 95-96)。"""
    monkeypatch.setattr(dlg, "_prompt_operation_params", lambda t, e=None: None)
    dlg._add_operation("add_prefix")
    assert dlg.operations == []


def test_remove_operation(dlg, monkeypatch):
    monkeypatch.setattr(dlg, "_prompt_operation_params", lambda t, e=None: {"text": "P_"})
    dlg._add_operation("add_prefix")
    dlg._add_operation("add_suffix")
    dlg.ui.list_operations.setCurrentRow(0)
    dlg._remove_operation()
    assert len(dlg.operations) == 1
    assert dlg.operations[0]["type"] == "add_suffix"


def test_remove_operation_no_selection(dlg):
    """无选中行 → 不删(行 114-116)。"""
    dlg.operations = [{"type": "add_prefix", "params": {"text": "P_"}}]
    dlg._remove_operation()  # 无选中
    assert len(dlg.operations) == 1


def test_edit_operation(dlg, monkeypatch):
    monkeypatch.setattr(dlg, "_prompt_operation_params", lambda t, e=None: {"text": "NEW_"})
    dlg.operations = [{"type": "add_prefix", "params": {"text": "OLD_"}}]
    dlg._refresh_operation_list()  # 填充列表使 currentRow 可选
    dlg.ui.list_operations.setCurrentRow(0)
    dlg._edit_operation()
    assert dlg.operations[0]["params"] == {"text": "NEW_"}


def test_edit_operation_no_selection(dlg):
    dlg.operations = [{"type": "add_prefix", "params": {"text": "X"}}]
    dlg._edit_operation()  # 无选中
    assert dlg.operations[0]["params"] == {"text": "X"}


def test_edit_operation_cancelled(dlg, monkeypatch):
    monkeypatch.setattr(dlg, "_prompt_operation_params", lambda t, e=None: None)
    dlg.operations = [{"type": "add_prefix", "params": {"text": "X"}}]
    dlg.ui.list_operations.setCurrentRow(0)
    dlg._edit_operation()
    assert dlg.operations[0]["params"] == {"text": "X"}


# ---------------------------------------------------------------------------
# _do_refresh_preview
# ---------------------------------------------------------------------------


def test_do_refresh_preview_empty(dlg):
    """无文件/操作 → 清空预览(行 140-142)。"""
    dlg._do_refresh_preview()
    assert dlg.ui.table_preview.rowCount() == 0


def test_do_refresh_preview_invalid_op(dlg, monkeypatch):
    """操作无效 → 弹警告(行 143-146)。"""
    dlg.selected_files = [Path("a.txt")]
    dlg.operations = [{"type": "bogus", "params": {}}]
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(a) or QMessageBox.StandardButton.Ok
    )
    dlg._do_refresh_preview()
    assert warned


def test_do_refresh_preview_renders(dlg, monkeypatch, tmp_path):
    """有效操作 + 文件 → 渲染预览表(行 147-158)。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    dlg.selected_files = [f1]
    dlg.operations = [{"type": "add_prefix", "params": {"text": "P_"}}]
    dlg._do_refresh_preview()
    assert dlg.ui.table_preview.rowCount() == 1
    assert dlg.ui.table_preview.item(0, 0).text() == "a.txt"
    assert dlg.ui.table_preview.item(0, 1).text() == "P_a.txt"


# ---------------------------------------------------------------------------
# _execute
# ---------------------------------------------------------------------------


def test_execute_no_files_warns(dlg, monkeypatch):
    """无文件/操作 → 提示(行 161-163)。"""
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(a) or QMessageBox.StandardButton.Ok,
    )
    dlg._execute()
    assert info_calls


def test_execute_confirm_and_rename(dlg, monkeypatch, tmp_path):
    """确认执行 → 重命名 + 记录历史(行 160-186)。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    dlg.selected_files = [f1]
    dlg.operations = [{"type": "add_prefix", "params": {"text": "P_"}}]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._execute()
    assert (tmp_path / "P_a.txt").exists()
    assert info_calls


def test_execute_declined(dlg, monkeypatch, tmp_path):
    """用户选 No → 不执行(行 173-175)。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    dlg.selected_files = [f1]
    dlg.operations = [{"type": "add_prefix", "params": {"text": "P_"}}]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dlg._execute()
    assert not (tmp_path / "P_a.txt").exists()


def test_execute_no_ready_files(dlg, monkeypatch, tmp_path):
    """全部冲突 → 提示无可执行(行 169-172)。

    构造冲突:把 a.txt 重命名为 b.txt,但 b.txt 已存在 → 状态'文件名冲突' → ready 为空。
    """
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    (tmp_path / "b.txt").write_text("exists")  # 目标已存在 → 冲突
    dlg.selected_files = [f1]
    dlg.operations = [{"type": "replace_text", "params": {"find": "a", "replace": "b"}}]
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(a) or QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg._execute()
    assert warned


# ---------------------------------------------------------------------------
# _show_history
# ---------------------------------------------------------------------------


def test_show_history_empty(dlg, monkeypatch):
    """无历史 → 提示暂无(行 189-192)。"""
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._show_history()
    assert any("暂无" in s for s in info_calls)


def test_show_history_with_records(dlg, monkeypatch):
    dlg._history.add_record("rename", {"rename_map": {"a": "b"}})
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._show_history()
    assert info_calls


# ---------------------------------------------------------------------------
# 模板管理
# ---------------------------------------------------------------------------


def test_load_template_empty(dlg, monkeypatch):
    """无模板 → 提示(行 202-205)。"""
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._load_template()
    assert any("暂无" in s for s in info_calls)


def test_save_template_no_operations(dlg, monkeypatch):
    """无操作 → 提示(行 224-226)。"""
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._save_template()
    assert any("没有操作" in s for s in info_calls)


def test_save_template_new(dlg, monkeypatch):
    """保存新模板(行 222-239)。"""
    dlg.operations = [{"type": "add_prefix", "params": {"text": "P_"}}]
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("新模板", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg._save_template()
    assert dlg._template_svc.template_exists("新模板")


def test_load_template_success(dlg, monkeypatch):
    """加载已有模板(行 200-220)。"""
    dlg._template_svc.add_template("t1", [{"type": "add_prefix", "params": {"text": "X"}}])
    dlg.operations = []
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("t1  (添加前缀)", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg._load_template()
    assert len(dlg.operations) == 1


def test_save_template_overwrite_existing(dlg, monkeypatch):
    """同名模板 → 覆盖确认 Yes → update(行 231-236)。"""
    dlg._template_svc.add_template("dup", [{"type": "add_prefix", "params": {"text": "X"}}])
    dlg.operations = [{"type": "add_suffix", "params": {"text": "S_"}}]
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("dup", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg._save_template()
    # 模板被更新为新操作
    templates = dlg._template_svc.get_all_templates()
    dup = [t for t in templates if t["name"] == "dup"][0]
    assert dup["operations"][0]["type"] == "add_suffix"


def test_save_template_overwrite_declined(dlg, monkeypatch):
    """同名模板 → 选 No → 不覆盖(行 233-235)。"""
    dlg._template_svc.add_template("dup", [{"type": "add_prefix", "params": {"text": "X"}}])
    dlg.operations = [{"type": "add_suffix", "params": {"text": "S_"}}]
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("dup", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dlg._save_template()
    templates = dlg._template_svc.get_all_templates()
    dup = [t for t in templates if t["name"] == "dup"][0]
    assert dup["operations"][0]["type"] == "add_prefix"  # 未变


def test_save_template_cancelled(dlg, monkeypatch):
    """输入对话框取消 → 不保存(行 227-229)。"""
    dlg.operations = [{"type": "add_prefix", "params": {"text": "X"}}]
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    dlg._save_template()
    assert dlg._template_svc.get_all_templates() == []


def test_load_template_cancelled(dlg, monkeypatch):
    """加载模板取消 → 不改 operations(行 211-213)。"""
    dlg._template_svc.add_template("t1", [{"type": "add_prefix", "params": {"text": "X"}}])
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("t1", False))
    dlg._load_template()
    assert dlg.operations == []


# ---------------------------------------------------------------------------
# _op_label / _update_status / closeEvent
# ---------------------------------------------------------------------------


def test_op_label_known(dlg):
    assert dlg._op_label({"type": "add_prefix", "params": {}}) == "添加前缀"


def test_op_label_unknown(dlg):
    assert dlg._op_label({"type": "bogus", "params": {}}) == "bogus"


def test_op_label_non_string_type(dlg):
    """type 非 str → 返回空串(行 243-244)。"""
    assert dlg._op_label({"type": 123, "params": {}}) == ""


def test_update_status(dlg):
    dlg.selected_files = [Path("a"), Path("b")]
    dlg._update_status()
    assert "2" in dlg.ui.label_status.text()


def test_close_event_calls_cleanup(dlg, monkeypatch):
    """closeEvent 调 _cleanup_batch_dialog(不抛)。

    mock _cleanup_batch_dialog 避免触发真实 timer/worker 清理(行 252-254)。
    """
    cleaned = {"n": 0}
    monkeypatch.setattr(dlg, "_cleanup_batch_dialog", lambda: cleaned.__setitem__("n", 1))
    from PySide6.QtGui import QCloseEvent

    evt = QCloseEvent()  # 无参构造
    dlg.closeEvent(evt)
    assert cleaned["n"] == 1
