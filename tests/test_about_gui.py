"""AboutTab GUI 冒烟测试:验证控件存在 + 数据正确渲染,不实际点按钮。"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from file_toolbox import __version__  # noqa: E402
from file_toolbox.gui.dialogs.about_tab import AboutTab  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _collect_text(tab: AboutTab) -> str:
    """递归收集 Tab 内所有 QLabel/QPlainTextEdit 文本(不依赖具体控件名)。"""
    parts: list[str] = []

    def walk(widget):
        if isinstance(widget, QLabel):
            parts.append(widget.text())
        elif isinstance(widget, QPlainTextEdit):
            parts.append(widget.toPlainText())
        # 递归所有子 widget
        for child in widget.children():
            walk(child)

    walk(tab)
    return "\n".join(parts)


def test_about_tab_instantiates(app):
    """AboutTab 应为合法 QWidget 且已构建出可见子控件(而非空壳)。"""
    tab = AboutTab()
    assert isinstance(tab, QWidget)
    assert tab.findChildren(QWidget)  # 有子控件,确认 _init_ui 已执行


def test_about_tab_shows_app_name(app):
    tab = AboutTab()
    assert "File Toolbox" in _collect_text(tab)


def test_about_tab_shows_version(app):
    tab = AboutTab()
    assert __version__ in _collect_text(tab)


def test_about_tab_shows_repo_url(app):
    tab = AboutTab()
    assert "github.com" in _collect_text(tab)


def test_about_tab_shows_changelog(app):
    tab = AboutTab()
    assert "Changelog" in _collect_text(tab) or "版本" in _collect_text(tab)


def test_about_tab_has_four_shortcut_buttons(app):
    tab = AboutTab()
    buttons = tab.findChildren(QPushButton)
    texts = [b.text() for b in buttons]
    assert any("桌面" in t for t in texts)
    assert any("开始菜单" in t for t in texts)
    # 创建 + 删除 各两类
    assert sum(1 for t in texts if "添加" in t) >= 2
    assert sum(1 for t in texts if "移除" in t) >= 2
