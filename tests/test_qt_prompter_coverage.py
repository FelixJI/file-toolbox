"""QInputDialogPrompter 的单元测试。

mock QInputDialog 的静态方法,验证 get_text/get_int/get_item 的成功与取消行为。
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QInputDialog

from file_toolbox.gui.controllers.operation_params import PromptCancelled
from file_toolbox.gui.controllers.qt_prompter import QInputDialogPrompter


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _patch(monkeypatch, method, return_value):
    """替换 QInputDialog.<method> 返回 (value, ok)。"""
    monkeypatch.setattr(QInputDialog, method, lambda *a, **k: return_value)


# ---------------------------------------------------------------------------
# get_text
# ---------------------------------------------------------------------------


def test_get_text_success(app, monkeypatch):
    _patch(monkeypatch, "getText", ("hello", True))
    p = QInputDialogPrompter()
    assert p.get_text("Title", "Label") == "hello"


def test_get_text_cancelled_raises(app, monkeypatch):
    _patch(monkeypatch, "getText", ("", False))
    p = QInputDialogPrompter()
    with pytest.raises(PromptCancelled):
        p.get_text("Title", "Label", text="default")


def test_get_text_with_parent(app, monkeypatch):
    """传 parent 不抛(验证 parent 透传)。"""
    _patch(monkeypatch, "getText", ("x", True))
    p = QInputDialogPrompter(parent=MagicMock())
    assert p.get_text("T", "L") == "x"


# ---------------------------------------------------------------------------
# get_int
# ---------------------------------------------------------------------------


def test_get_int_success(app, monkeypatch):
    _patch(monkeypatch, "getInt", (42, True))
    p = QInputDialogPrompter()
    assert p.get_int("T", "L", value=5, minimum=0, maximum=100) == 42


def test_get_int_cancelled_raises(app, monkeypatch):
    _patch(monkeypatch, "getInt", (0, False))
    p = QInputDialogPrompter()
    with pytest.raises(PromptCancelled):
        p.get_int("T", "L")


# ---------------------------------------------------------------------------
# get_item
# ---------------------------------------------------------------------------


def test_get_item_success(app, monkeypatch):
    _patch(monkeypatch, "getItem", ("b", True))
    p = QInputDialogPrompter()
    assert p.get_item("T", "L", ["a", "b", "c"], current=1, editable=False) == "b"


def test_get_item_cancelled_raises(app, monkeypatch):
    _patch(monkeypatch, "getItem", ("", False))
    p = QInputDialogPrompter()
    with pytest.raises(PromptCancelled):
        p.get_item("T", "L", ["a"])


# ---------------------------------------------------------------------------
# 参数透传:get_int 的 minValue/maxValue、get_item 的 current/editable 必须转发给
# QInputDialog(回归保护:旧测试用 lambda *a,**k 丢弃参数,删除这些 kw 静默通过)
# ---------------------------------------------------------------------------


def test_get_int_forwards_min_max_value_to_qinputdialog(app, monkeypatch):
    """get_int 的 value/minimum/maximum 必须以 minValue/maxValue/value 转发。"""
    captured = {}

    def fake_get_int(*a, **k):
        captured.update(k)
        return (k.get("value", 0), True)

    monkeypatch.setattr(QInputDialog, "getInt", fake_get_int)
    p = QInputDialogPrompter()
    p.get_int("T", "L", value=7, minimum=1, maximum=50)
    assert captured["value"] == 7
    assert captured["minValue"] == 1
    assert captured["maxValue"] == 50


def test_get_item_forwards_current_editable_to_qinputdialog(app, monkeypatch):
    """get_item 的 current(位置参数)/editable 必须转发。"""
    captured = {}

    def fake_get_item(*a, **k):
        captured.update(k)
        captured["_args"] = a
        return ("x", True)

    monkeypatch.setattr(QInputDialog, "getItem", fake_get_item)
    p = QInputDialogPrompter()
    p.get_item("T", "L", ["a", "b"], current=1, editable=True)
    # QInputDialog.getItem(parent, title, label, items, current, editable=...)
    # args: a[0]=parent, a[1]=title, a[2]=label, a[3]=items, a[4]=current
    assert captured["_args"][3] == ["a", "b"]
    assert captured["_args"][4] == 1  # current 透传
    assert captured["editable"] is True


def test_get_text_empty_string_ok_returns_empty(app, monkeypatch):
    """get_text 返回 ('', True)(用户对空输入点 OK)→ 返回 ''(与取消区分:取消抛异常)。"""
    _patch(monkeypatch, "getText", ("", True))
    p = QInputDialogPrompter()
    assert p.get_text("T", "L") == ""
