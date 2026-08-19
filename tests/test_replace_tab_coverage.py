"""replace_tab GUI 测试:操作增删改、预览、执行、历史(mock 输入对话框)。

预览/执行已异步化(worker 后台线程):涉及 service 结果的断言需泵送事件
等待 worker 完成信号(queued)回到主线程。
"""

import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_replace.types import ReplaceOperationType
from file_toolbox.gui.dialogs.replace_tab import ContentReplaceDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dlg(app, tmp_path):
    d = ContentReplaceDialog()
    d._history = JsonHistoryStore(tmp_path)
    yield d
    # 异步 worker 兜底:确保测试结束时没有仍运行的线程(避免 QThread 随对话框
    # 析构触发 Windows 堆损坏)
    d._stop_worker(5000)


def _pump_until(app, cond, timeout_s: float = 5.0) -> bool:
    """泵送事件直到 cond() 为真(等待 worker 信号回主线程);超时返回 False。"""
    deadline = time.monotonic() + timeout_s
    while not cond():
        if time.monotonic() > deadline:
            return False
        app.processEvents()
        time.sleep(0.01)
    return True


SIMPLE = ReplaceOperationType.SIMPLE_REPLACE.value
REGEX = ReplaceOperationType.REGEX_REPLACE.value


# ---------------------------------------------------------------------------
# 操作增删改
# ---------------------------------------------------------------------------


def test_add_operation(dlg, monkeypatch):
    monkeypatch.setattr(dlg, "_prompt_params", lambda t, e=None: {"find": "a", "replace": "b"})
    dlg._add_operation(SIMPLE)
    assert len(dlg.operations) == 1
    assert dlg.ui.list_operations.count() == 1


def test_add_operation_cancelled(dlg, monkeypatch):
    monkeypatch.setattr(dlg, "_prompt_params", lambda t, e=None: None)
    dlg._add_operation(SIMPLE)
    assert dlg.operations == []


def test_remove_operation(dlg, monkeypatch):
    monkeypatch.setattr(dlg, "_prompt_params", lambda t, e=None: {"find": "a", "replace": "b"})
    dlg._add_operation(SIMPLE)
    dlg._add_operation(SIMPLE)
    dlg.ui.list_operations.setCurrentRow(0)
    dlg._remove_operation()
    assert len(dlg.operations) == 1


def test_remove_no_selection(dlg):
    dlg.operations = [{"type": SIMPLE, "params": {"find": "a", "replace": "b"}}]
    dlg._remove_operation()
    assert len(dlg.operations) == 1


def test_edit_operation(dlg, monkeypatch):
    monkeypatch.setattr(dlg, "_prompt_params", lambda t, e=None: {"find": "new", "replace": "x"})
    dlg.operations = [{"type": SIMPLE, "params": {"find": "old", "replace": "x"}}]
    dlg._refresh_op_list()
    dlg.ui.list_operations.setCurrentRow(0)
    dlg._edit_operation()
    assert dlg.operations[0]["params"]["find"] == "new"


def test_edit_no_selection(dlg):
    dlg.operations = [{"type": SIMPLE, "params": {"find": "a", "replace": "b"}}]
    dlg._edit_operation()
    assert dlg.operations[0]["params"]["find"] == "a"


def test_edit_cancelled(dlg, monkeypatch):
    monkeypatch.setattr(dlg, "_prompt_params", lambda t, e=None: None)
    dlg.operations = [{"type": SIMPLE, "params": {"find": "a", "replace": "b"}}]
    dlg._refresh_op_list()
    dlg.ui.list_operations.setCurrentRow(0)
    dlg._edit_operation()
    assert dlg.operations[0]["params"]["find"] == "a"


def test_refresh_op_list_regex_label(dlg):
    """regex 操作的标签格式(行 93-94)。"""
    dlg.operations = [{"type": REGEX, "params": {"pattern": r"\d+", "replace": "X"}}]
    dlg._refresh_op_list()
    assert dlg.ui.list_operations.count() == 1
    assert "正则" in dlg.ui.list_operations.item(0).text()


def test_refresh_op_list_simple_label(dlg):
    dlg.operations = [{"type": SIMPLE, "params": {"find": "a", "replace": "b"}}]
    dlg._refresh_op_list()
    assert "替换" in dlg.ui.list_operations.item(0).text()


# ---------------------------------------------------------------------------
# _prompt_params(行 101-102):委托给 OperationParamCollector
# ---------------------------------------------------------------------------


def test_prompt_params_delegates_to_collector(dlg, monkeypatch):
    """_prompt_params:构造 collector 并委托 collect,返回 simple_replace 参数(行 101-102)。

    monkeypatch QInputDialog.getText 以顺序返回 find/replace。
    """
    from PySide6.QtWidgets import QInputDialog

    answers = iter([("foo", True), ("bar", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers))
    result = dlg._prompt_params(SIMPLE)
    assert result == {"find": "foo", "replace": "bar", "case_sensitive": False}


def test_prompt_params_passes_existing(dlg, monkeypatch):
    """编辑预填:existing 透传给 collector(行 101-102 的 existing 参数链路)。"""
    from PySide6.QtWidgets import QInputDialog

    answers = iter([("newfind", True), ("newreplace", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers))
    result = dlg._prompt_params(SIMPLE, existing={"find": "old", "replace": "oldr"})
    assert result["find"] == "newfind"
    assert result["replace"] == "newreplace"


def test_prompt_params_cancelled_returns_none(dlg, monkeypatch):
    """_prompt_params:用户取消 → collector 返回 None(行 101-102 的取消路径)。"""
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    assert dlg._prompt_params(SIMPLE) is None


# ---------------------------------------------------------------------------
# _do_refresh_preview
# ---------------------------------------------------------------------------


def test_do_refresh_preview_empty(dlg):
    dlg._do_refresh_preview()
    assert dlg.ui.table_preview.rowCount() == 0


def test_do_refresh_preview_invalid(dlg, monkeypatch):
    dlg.selected_files = [Path("a.txt")]
    dlg.operations = [{"type": "bogus", "params": {}}]
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(1) or QMessageBox.StandardButton.Ok
    )
    dlg._do_refresh_preview()
    assert warned


def test_do_refresh_preview_renders(dlg, app, monkeypatch, tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("hello world")
    dlg.selected_files = [f1]
    dlg.operations = [{"type": SIMPLE, "params": {"find": "hello", "replace": "hi"}}]
    dlg._do_refresh_preview()
    assert _pump_until(app, lambda: dlg.ui.table_preview.rowCount() == 1), (
        "预览 worker 应完成并渲染"
    )


# ---------------------------------------------------------------------------
# _execute
# ---------------------------------------------------------------------------


def test_execute_no_files(dlg, monkeypatch):
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    dlg._execute()
    assert info_calls


def test_execute_confirm(dlg, app, monkeypatch, tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("hello")
    dlg.selected_files = [f1]
    dlg.operations = [{"type": SIMPLE, "params": {"find": "hello", "replace": "hi"}}]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    dlg._execute()
    assert _pump_until(app, lambda: info_calls), "执行 worker 应完成并弹提示"
    assert f1.read_text() == "hi"
    assert info_calls


def test_execute_declined(dlg, monkeypatch, tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("hello")
    dlg.selected_files = [f1]
    dlg.operations = [{"type": SIMPLE, "params": {"find": "hello", "replace": "hi"}}]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dlg._execute()
    assert f1.read_text() == "hello"  # 未改


def test_execute_with_errors(dlg, app, monkeypatch, tmp_path):
    """执行有错误 → 错误信息拼入提示(行 145-146)。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("hello")
    dlg.selected_files = [f1]
    dlg.operations = [{"type": SIMPLE, "params": {"find": "hello", "replace": "hi"}}]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._execute()
    assert _pump_until(app, lambda: info_calls), "执行 worker 应完成并弹提示"
    assert info_calls


def test_execute_passes_keep_new_format_when_checked(dlg, app, monkeypatch, tmp_path):
    """勾选"转换后保留新格式" → execute_replace 收到 keep_new_format=True。

    回归:此前 _execute 从未读取该复选框,GUI 选项长期失效。
    """
    f1 = tmp_path / "a.txt"
    f1.write_text("hello")
    dlg.selected_files = [f1]
    dlg.operations = [{"type": SIMPLE, "params": {"find": "hello", "replace": "hi"}}]
    dlg.ui.chk_keep_new_format.setChecked(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        dlg._svc,
        "execute_replace",
        lambda *a, **k: captured.update(k) or (0, 0, []),
    )
    dlg._execute()
    # 泵送到完成框已弹(而非 service 已被调):确保 _on_execute_ok 已在补丁
    # 有效期内执行,避免残余 queued 信号在 teardown 落到真实模态框上
    assert _pump_until(app, lambda: info_calls), "worker 应调用 execute_replace 并完成"
    assert captured.get("keep_new_format") is True


def test_execute_defaults_keep_new_format_false_when_unchecked(dlg, app, monkeypatch, tmp_path):
    """未勾选 → keep_new_format=False(保持默认行为)。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("hello")
    dlg.selected_files = [f1]
    dlg.operations = [{"type": SIMPLE, "params": {"find": "hello", "replace": "hi"}}]
    dlg.ui.chk_keep_new_format.setChecked(False)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        dlg._svc,
        "execute_replace",
        lambda *a, **k: captured.update(k) or (0, 0, []),
    )
    dlg._execute()
    assert _pump_until(app, lambda: info_calls), "worker 应调用 execute_replace 并完成"
    assert captured.get("keep_new_format") is False


# ---------------------------------------------------------------------------
# _show_history
# ---------------------------------------------------------------------------


def test_show_history_empty(dlg, monkeypatch):
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._show_history()
    assert any("暂无" in s for s in info_calls)


def test_show_history_with_records(dlg, monkeypatch):
    dlg._history.add_record("replace", {"files": ["a.txt"]})
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._show_history()
    assert info_calls


# ---------------------------------------------------------------------------
# _update_status / closeEvent
# ---------------------------------------------------------------------------


def test_update_status(dlg):
    dlg.selected_files = [Path("a"), Path("b")]
    dlg._update_status()
    assert "2" in dlg.ui.label_status.text()


def test_close_event(dlg, monkeypatch):
    """closeEvent 调 cleanup + svc.close(行 163-167)。"""
    cleaned = {"n": 0}
    closed = {"n": 0}
    monkeypatch.setattr(dlg, "_cleanup_batch_dialog", lambda: cleaned.__setitem__("n", 1))
    monkeypatch.setattr(dlg._svc, "close", lambda: closed.__setitem__("n", 1))
    from PySide6.QtGui import QCloseEvent

    dlg.closeEvent(QCloseEvent())
    assert cleaned["n"] == 1
    assert closed["n"] == 1
