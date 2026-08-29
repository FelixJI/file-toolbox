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
    """所有操作类型有中文标签(标签已迁至 RenameController.OP_LABELS)。"""
    assert len(dlg._controller.OP_LABELS) == 7


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


def test_edit_operation_cancelled_with_valid_row(dlg, monkeypatch):
    """_edit_operation:prompt 返回 None 且行选中有效 → 提前 return 不改操作(行 107-108)。

    注:test_edit_operation_cancelled 未调 _refresh_operation_list,list 为空导致
    setCurrentRow(0) 实际为 -1,命中行 103-104 的早退。本用例先填充列表使行有效,
    专门覆盖行 107-108 的取消分支。
    """
    monkeypatch.setattr(dlg, "_prompt_operation_params", lambda t, e=None: None)
    dlg.operations = [{"type": "add_prefix", "params": {"text": "X"}}]
    dlg._refresh_operation_list()  # 先填充,使 setCurrentRow(0) 选中有效行
    dlg.ui.list_operations.setCurrentRow(0)
    assert dlg.ui.list_operations.currentRow() == 0  # 确认选中
    prompted_types: list = []
    monkeypatch.setattr(
        dlg,
        "_prompt_operation_params",
        lambda t, e=None: prompted_types.append(t) or None,
    )
    dlg._edit_operation()
    assert dlg.operations[0]["params"] == {"text": "X"}  # 未改
    assert prompted_types == ["add_prefix"]  # prompt 被调用且 type 正确


# ---------------------------------------------------------------------------
# _prompt_operation_params(行 135-136):委托给 OperationParamCollector
# ---------------------------------------------------------------------------


def test_prompt_operation_params_delegates_to_collector(dlg, monkeypatch):
    """_prompt_operation_params:构造 collector 并委托 collect(行 135-136)。

    monkeypatch QInputDialog.getText 使 prompter 返回确定值,验证返回结构。
    """
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("PREFIX_", True))
    result = dlg._prompt_operation_params("add_prefix")
    assert result == {"text": "PREFIX_"}


def test_prompt_operation_params_passes_existing(dlg, monkeypatch):
    """编辑预填:existing 透传给 collector(行 135-136 的 existing 参数链路)。"""
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("EDITED", True))
    result = dlg._prompt_operation_params("add_prefix", existing={"text": "old"})
    assert result == {"text": "EDITED"}


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


def test_execute_syncs_files_and_preview_to_new_paths(dlg, monkeypatch, tmp_path):
    """执行后文件列表/预览必须落到新路径(回归:曾仍持旧路径,预览误报冲突+未知)。

    旧行为:selected_files 保持 a.txt(已不存在),刷新预览时 new P_a.txt 已存在
    → 状态列"⚠️ 文件名冲突",大小/时间列"未知"。修复后列表与预览基于新路径,
    状态列为就绪、大小/时间可读取。
    """
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    dlg.selected_files = [f1]
    dlg.ui.list_files.addItem(str(f1))
    dlg.operations = [{"type": "add_prefix", "params": {"text": "P_"}}]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg._execute()

    new_path = tmp_path / "P_a.txt"
    assert new_path.exists()
    assert dlg.selected_files == [new_path]
    assert dlg.ui.list_files.item(0).text() == str(new_path)
    # 预览基于新路径:旧文件名不再出现,状态不再误报冲突,大小/时间不再"未知"
    assert dlg.ui.table_preview.item(0, 0).text() == "P_a.txt"
    assert "冲突" not in dlg.ui.table_preview.item(0, 4).text()
    assert dlg.ui.table_preview.item(0, 2).text() != "未知"
    assert dlg.ui.table_preview.item(0, 3).text() != "未知"


def test_execute_failure_keeps_old_paths(dlg, monkeypatch, tmp_path):
    """执行全部失败(如权限) → 文件列表保持原路径,不误同步。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    dlg.selected_files = [f1]
    dlg.ui.list_files.addItem(str(f1))
    dlg.operations = [{"type": "add_prefix", "params": {"text": "P_"}}]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(dlg._svc, "execute_rename", lambda m: (0, ["权限不足: a.txt"]))
    dlg._execute()
    assert f1.exists()
    assert dlg.selected_files == [f1]
    assert dlg.ui.list_files.item(0).text() == str(f1)


def test_sync_selected_paths_partial_success(dlg, tmp_path):
    """_sync_selected_paths_after_rename:仅同步成功项(原路径消失且新路径存在)。"""
    old1, new1 = tmp_path / "a.txt", tmp_path / "P_a.txt"
    old2, new2 = tmp_path / "b.txt", tmp_path / "P_b.txt"
    new1.write_text("1")  # 已改名成功:仅新路径存在
    old2.write_text("2")  # 改名失败:old2 仍在,new2 不存在
    dlg.selected_files = [old1, old2]
    dlg.ui.list_files.addItem(str(old1))
    dlg.ui.list_files.addItem(str(old2))
    dlg._sync_selected_paths_after_rename({old1: new1, old2: new2})
    assert dlg.selected_files == [new1, old2]
    assert dlg.ui.list_files.item(0).text() == str(new1)
    assert dlg.ui.list_files.item(1).text() == str(old2)


def test_sync_selected_paths_nothing_renamed_is_noop(dlg, tmp_path):
    """无成功项 → selected_files 与列表控件均不变。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    dlg.selected_files = [f1]
    dlg.ui.list_files.addItem(str(f1))
    dlg._sync_selected_paths_after_rename({f1: tmp_path / "P_a.txt"})
    assert dlg.selected_files == [f1]
    assert dlg.ui.list_files.item(0).text() == str(f1)


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


def test_execute_invalid_operations_warns(dlg, monkeypatch, tmp_path):
    """有文件+操作但操作非法 → 弹'操作无效'警告并不执行(行 164-167)。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    dlg.selected_files = [f1]
    dlg.operations = [{"type": "bogus_op", "params": {}}]  # 未知 op_type → 校验失败
    warned = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *a, **k: warned.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    # question/information 不应被调用(校验失败提前 return)
    questioned = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: questioned.append(1) or QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg._execute()
    assert warned and any("无效" in w for w in warned)
    assert questioned == []  # 未进入确认分支


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
    """type 非 str → 经 RenameController.op_label 的 str() 强转后回退为字符串形式。"""
    assert dlg._op_label({"type": 123, "params": {}}) == "123"


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
