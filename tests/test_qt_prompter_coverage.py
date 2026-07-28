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
