"""history_dialog 的单元测试。

覆盖:
- _summary_label 各工具分支(纯函数)
- HistoryDialog 加载(有/无记录)、撤销流程(mock QMessageBox/service)
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QMessageBox

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.gui.dialogs.history_dialog import HistoryDialog, _summary_label


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# _summary_label:各工具分支(行 27-48)
# ---------------------------------------------------------------------------


def test_summary_label_rename():
    assert _summary_label("rename", {"rename_map": {"a": "b", "c": "d"}}) == "2 个文件"


def test_summary_label_rename_empty():
    assert _summary_label("rename", {}) == "0 个文件"


def test_summary_label_replace():
    assert _summary_label("replace", {"files": ["a", "b", "c"]}) == "3 个文件"


def test_summary_label_pdf():
    assert _summary_label("pdf", {"files": ["a", "b", "c"], "success": 2}) == "2/3 个成功"


def test_summary_label_mkdir():
    label = _summary_label(
        "mkdir", {"created": 5, "skipped": 1, "strategy": "merge", "root": "/out"}
    )
    assert "新建 5" in label and "跳过 1" in label and "merge" in label and "/out" in label


def test_summary_label_invoice():
    label = _summary_label("invoice", {"invoice_count": 3, "file_count": 5, "fmt": "excel"})
    assert "3 张发票" in label and "5 文件" in label and "excel" in label


def test_summary_label_attendance():
    label = _summary_label(
        "attendance",
        {"employee_count": 8, "year": 2026, "month": 7, "output": "C:/out/汇总.xlsx"},
    )
    assert label == "2026-7 / 8 人 → 汇总.xlsx"


def test_summary_label_unknown_tool():
    """未知工具 → str(data)[:40]。"""
    data = {"key": "value"}
    assert _summary_label("unknown", data) == str(data)[:40]


# ---------------------------------------------------------------------------
# HistoryDialog:加载
# ---------------------------------------------------------------------------


def _store_with_records(tmp_path, tool, records):
    store = JsonHistoryStore(tmp_path / "h.json")
    for r in records:
        store.add_record(tool, r)
    return store


def test_history_dialog_empty_records(app, tmp_path):
    """无记录 → 显示 '(无历史记录)',撤销按钮禁用。"""
    store = JsonHistoryStore(tmp_path / "h.json")
    dlg = HistoryDialog(store, tool="rename")
    assert dlg.list_widget.count() == 1
    assert dlg.list_widget.item(0).text() == "(无历史记录)"
    assert dlg.btn_undo.isEnabled() is False


def test_history_dialog_loads_records(app, tmp_path):
    """有记录 → 列表显示,撤销按钮启用(rename)。"""
    store = _store_with_records(
        tmp_path,
        "rename",
        [{"rename_map": {"a": "b"}}],
    )
    dlg = HistoryDialog(store, tool="rename")
    assert dlg.list_widget.count() == 1
    assert "1 个文件" in dlg.list_widget.item(0).text()
    assert dlg.btn_undo.isEnabled() is True
    # rename 工具:btn_undo 的可见性策略为 True(setVisible(True))
    # (未 show 的对话框 isVisible() 恒 False,改查 isHidden)
    assert not dlg.btn_undo.isHidden()


def test_history_dialog_non_rename_undo_hidden(app, tmp_path):
    """非 rename 工具 → 撤销按钮隐藏(setVisible(False))。"""
    store = _store_with_records(tmp_path, "pdf", [{"files": [], "success": 0}])
    dlg = HistoryDialog(store, tool="pdf")
    assert dlg.btn_undo.isHidden()


def test_history_dialog_undone_marker_shown(app, tmp_path):
    """已撤销记录显示 [已撤销] 标记。"""
    store = _store_with_records(tmp_path, "rename", [{"rename_map": {"a": "b"}}])
    # 标记第一条为已撤销
    records = store.get_records("rename")
    store.mark_undone("rename", records[0]["id"])
    dlg = HistoryDialog(store, tool="rename")
    assert "[已撤销]" in dlg.list_widget.item(0).text()


# ---------------------------------------------------------------------------
# HistoryDialog:撤销流程(mock QMessageBox 与 service)
# ---------------------------------------------------------------------------


def test_history_dialog_undo_no_selection(app, tmp_path, monkeypatch):
    """无选中项 → 提示选择(行 102-105)。"""
    store = _store_with_records(tmp_path, "rename", [{"rename_map": {"a": "b"}}])
    dlg = HistoryDialog(store, tool="rename")
    # 不选中任何项
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(a) or QMessageBox.StandardButton.Ok,
    )
    dlg._undo_selected()
    assert info_calls  # 弹了提示


def test_history_dialog_undo_cancelled(app, tmp_path, monkeypatch):
    """撤销确认选 No → 不执行(行 131-132)。"""
    store = _store_with_records(
        tmp_path,
        "rename",
        [{"rename_map": {str(tmp_path / "a.txt"): str(tmp_path / "b.txt")}}],
    )
    (tmp_path / "b.txt").write_text("x")  # 目标存在,可反向
    dlg = HistoryDialog(store, tool="rename")
    dlg.list_widget.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    # 不应抛异常,不执行重命名
    dlg._undo_selected()


def test_history_dialog_undo_empty_map(app, tmp_path, monkeypatch):
    """记录 rename_map 为空 → 提示无可撤销(行 113-116)。"""
    store = _store_with_records(tmp_path, "rename", [{"rename_map": {}}])
    dlg = HistoryDialog(store, tool="rename")
    dlg.list_widget.setCurrentRow(0)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(a) or QMessageBox.StandardButton.Ok,
    )
    dlg._undo_selected()
    assert any("无可撤销" in str(args) for args in info_calls)


def test_history_dialog_undo_success(app, tmp_path, monkeypatch):
    """撤销确认 Yes → 反向重命名成功 + mark_undone + 重新加载(行 118-141)。"""
    store = _store_with_records(
        tmp_path,
        "rename",
        [{"rename_map": {str(tmp_path / "a.txt"): str(tmp_path / "b.txt")}}],
    )
    (tmp_path / "b.txt").write_text("x")  # b 存在,反向 b→a
    dlg = HistoryDialog(store, tool="rename")
    dlg.list_widget.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(a) or QMessageBox.StandardButton.Ok,
    )
    dlg._undo_selected()
    # b.txt 被改回 a.txt
    assert (tmp_path / "a.txt").exists()
    assert not (tmp_path / "b.txt").exists()
    # 弹了完成提示
    assert info_calls


def test_history_dialog_undo_record_not_found(app, tmp_path, monkeypatch):
    """get_record 返回 None → 提示找不到(行 109-112)。"""
    store = _store_with_records(tmp_path, "rename", [{"rename_map": {"a": "b"}}])
    dlg = HistoryDialog(store, tool="rename")
    dlg.list_widget.setCurrentRow(0)
    # mock get_record 返回 None
    dlg._history = MagicMock()
    dlg._history.get_record.return_value = None
    warn_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *a, **k: warn_calls.append(a) or QMessageBox.StandardButton.Ok,
    )
    dlg._undo_selected()
    assert warn_calls


def test_history_dialog_undo_with_errors(app, tmp_path, monkeypatch):
    """撤销时部分文件反向重命名失败 → 错误信息拼入提示(行 138-139)。"""
    # rename_map 指向不存在的目标 → execute_rename 失败
    store = _store_with_records(
        tmp_path,
        "rename",
        [{"rename_map": {str(tmp_path / "missing_a.txt"): str(tmp_path / "missing_b.txt")}}],
    )
    dlg = HistoryDialog(store, tool="rename")
    dlg.list_widget.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(str(a)) or QMessageBox.StandardButton.Ok,
    )
    dlg._undo_selected()
    # 失败信息应出现在提示中(reverse_map 的目标 missing_b.txt 不存在)
    assert info_calls


def test_history_dialog_undo_partial_failure_still_marks_undone(app, tmp_path, monkeypatch):
    """部分失败(count < len)时,mark_undone 仍被调用(锁定当前行为)。

    回归风险:execute_rename 返回 count=0(全失败)时,当前实现仍调用 mark_undone,
    把这条历史标记为「已撤销」——即使没真正撤销任何文件。这可能误导用户认为撤销成功。
    锁定该行为:未来若改为「部分失败不标记已撤销」,该测试应变红提醒有意更新。
    """
    store = _store_with_records(
        tmp_path,
        "rename",
        [{"rename_map": {str(tmp_path / "ghost_a.txt"): str(tmp_path / "ghost_b.txt")}}],
    )
    rid = store.get_records("rename")[0]["id"]
    dlg = HistoryDialog(store, tool="rename")
    dlg.list_widget.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg._undo_selected()
    # 当前:部分/全失败仍 mark_undone
    rec = store.get_record("rename", rid)
    assert rec is not None
    assert rec["undone"] is True


def test_history_dialog_undo_rid_none_returns(app, tmp_path, monkeypatch):
    """选中项的 data(0x0100) 为 None → 直接 return(行 106-108)。

    构造一个 data 为 None 的 item。
    """
    store = _store_with_records(tmp_path, "rename", [{"rename_map": {"a": "b"}}])
    dlg = HistoryDialog(store, tool="rename")
    # 选中项存在,但其 data 为 None(模拟异常 item)
    from PySide6.QtWidgets import QListWidgetItem

    none_item = QListWidgetItem("fake")
    dlg.list_widget.addItem(none_item)
    dlg.list_widget.setCurrentItem(none_item)
    # 不应抛异常,不弹任何框
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(a) or QMessageBox.StandardButton.Ok,
    )
    dlg._undo_selected()
    # rid None → 直接 return,未进入后续逻辑
    assert not any("无可撤销" in str(a) or "找不到" in str(a) for a in info_calls)
