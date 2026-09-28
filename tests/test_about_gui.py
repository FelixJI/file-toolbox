"""AboutTab GUI 冒烟测试:验证控件存在 + 数据正确渲染,不实际点按钮。"""

import pytest

# 用 QtWidgets 子模块做 importorskip:仅检查顶层 PySide6 包不够——它会成功 import,
# 但 from PySide6.QtWidgets import ... 才真正加载 libEGL/libGL 等原生库。Linux 无
# 这些系统库时,顶层 importorskip 不跳过,反而在后续 import 处抛 ImportError 致收集失败。
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QPushButton,
    QTextEdit,
    QWidget,
)

from file_toolbox import __version__  # noqa: E402
from file_toolbox.common import metadata  # noqa: E402
from file_toolbox.gui.dialogs.about_tab import AboutTab  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _collect_text(tab: AboutTab) -> str:
    """递归收集 Tab 内所有 QLabel/QTextEdit 文本(不依赖具体控件名)。

    QTextEdit 覆盖 QTextBrowser(markdown 渲染的更新日志/新版更新内容)。
    """
    parts: list[str] = []

    def walk(widget):
        if isinstance(widget, QLabel):
            parts.append(widget.text())
        elif isinstance(widget, QTextEdit):
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
    # 精确匹配权威仓库 URL,而非 "github.com" 子串(避免 notgithub.com 等误匹配,
    # 也消除 CodeQL Incomplete URL substring sanitization 告警)。
    assert metadata.REPO_URL in _collect_text(tab)


def test_about_tab_shows_changelog(app):
    tab = AboutTab()
    assert "Changelog" in _collect_text(tab) or "版本" in _collect_text(tab)


def test_about_tab_changelog_renders_markdown(app):
    """更新日志区用 QTextBrowser 渲染 markdown,而非裸放源码。"""
    from PySide6.QtWidgets import QTextBrowser

    tab = AboutTab()
    assert isinstance(tab._changelog, QTextBrowser)
    # markdown 标题("# Changelog"/"## 0.x.y")渲染后以纯文本形式保留标题文字
    text = tab._changelog.toPlainText()
    assert "Changelog" in text or "当前版本" in text  # 兜底文本含"当前版本"


def test_about_tab_has_four_shortcut_buttons(app):
    tab = AboutTab()
    buttons = tab.findChildren(QPushButton)
    texts = [b.text() for b in buttons]
    assert any("桌面" in t for t in texts)
    assert any("开始菜单" in t for t in texts)
    # 创建 + 删除 各两类
    assert sum(1 for t in texts if "添加" in t) >= 2
    assert sum(1 for t in texts if "移除" in t) >= 2


def test_about_tab_opens_log_directory(app, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    opened: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", opened.append)
    tab = AboutTab()

    button = next(b for b in tab.findChildren(QPushButton) if "日志目录" in b.text())
    button.click()

    assert len(opened) == 1
    assert opened[0].isLocalFile()
    assert opened[0].toLocalFile().endswith(".file_toolbox/logs")


# ---------------------------------------------------------------------------
# 更新入口:仅"打开更新页面"导航(检查/下载/代理已迁移至独立更新页)
# ---------------------------------------------------------------------------


def test_about_tab_has_open_update_page_button(app):
    tab = AboutTab()
    assert tab.btn_open_update_page.text() == "打开更新页面"


def test_about_tab_open_update_page_emits_signal(app):
    tab = AboutTab()
    received: list = []
    tab.open_update_page_requested.connect(lambda: received.append(1))
    tab.btn_open_update_page.click()
    assert received == [1]


def test_about_tab_has_no_update_actions(app):
    """关于页不再承载更新动作:无检查/下载按钮,也无代理输入控件。"""
    from PySide6.QtWidgets import QLineEdit

    tab = AboutTab()
    buttons = [b.text() for b in tab.findChildren(QPushButton)]
    assert not any(("检查更新" in t or "立即更新" in t or "下载并更新" in t) for t in buttons)
    assert tab.findChild(QLineEdit) is None


def test_about_tab_tech_and_changelog_collapsed_by_default(app):
    """技术路线与完整更新日志为次要长内容,默认真折叠(内容隐藏)。"""
    from PySide6.QtWidgets import QGroupBox, QWidget

    tab = AboutTab()
    tab.show()
    app.processEvents()
    boxes = {b.title(): b for b in tab.findChildren(QGroupBox)}
    tech = boxes[next(t for t in boxes if t.startswith("技术路线"))]
    changelog = boxes[next(t for t in boxes if t.startswith("更新日志"))]
    assert tech.isChecked() is False and changelog.isChecked() is False
    assert [c for c in tech.findChildren(QWidget) if c.isVisible()] == []
    assert [c for c in changelog.findChildren(QWidget) if c.isVisible()] == []
    # 展开恢复可见
    changelog.setChecked(True)
    app.processEvents()
    assert [c for c in changelog.findChildren(QWidget) if c.isVisible()] != []


# ---------------------------------------------------------------------------
# 快捷方式 / 复制 handler(行 162-179):monkeypatch shortcuts.* / clipboard
# ---------------------------------------------------------------------------


class _StubResult:
    """模拟 ShortcutResult(只需 .message 即可)。"""

    def __init__(self, message: str) -> None:
        self.message = message


def test_about_tab_copy_repo_url_sets_clipboard_and_status(app, monkeypatch):
    """_copy_repo_url:把 REPO_URL 写入剪贴板 + 状态文本(行 162-163)。"""
    from PySide6.QtGui import QGuiApplication

    from file_toolbox.common import metadata

    captured: list[str] = []
    clip = QGuiApplication.clipboard()
    monkeypatch.setattr(clip, "setText", lambda text: captured.append(text))

    tab = AboutTab()
    tab._copy_repo_url()

    assert captured == [metadata.REPO_URL]
    assert tab._status_lbl.text() == "已复制开源地址到剪贴板"


def test_about_tab_add_desktop_shows_shortcut_result(app, monkeypatch):
    """_add_desktop:把 create_desktop_shortcut().message 写状态(行 166-167)。"""
    from file_toolbox.common import shortcuts

    monkeypatch.setattr(
        shortcuts, "create_desktop_shortcut", lambda: _StubResult("已创建桌面快捷方式")
    )
    tab = AboutTab()
    tab._add_desktop()
    assert tab._status_lbl.text() == "已创建桌面快捷方式"


def test_about_tab_remove_desktop_shows_shortcut_result(app, monkeypatch):
    """_remove_desktop:把 remove_desktop_shortcut().message 写状态(行 170-171)。"""
    from file_toolbox.common import shortcuts

    monkeypatch.setattr(
        shortcuts, "remove_desktop_shortcut", lambda: _StubResult("未找到桌面快捷方式")
    )
    tab = AboutTab()
    tab._remove_desktop()
    assert tab._status_lbl.text() == "未找到桌面快捷方式"


def test_about_tab_add_start_menu_shows_shortcut_result(app, monkeypatch):
    """_add_start_menu:把 create_start_menu_shortcut().message 写状态(行 174-175)。"""
    from file_toolbox.common import shortcuts

    monkeypatch.setattr(
        shortcuts, "create_start_menu_shortcut", lambda: _StubResult("已创建开始菜单快捷方式")
    )
    tab = AboutTab()
    tab._add_start_menu()
    assert tab._status_lbl.text() == "已创建开始菜单快捷方式"


def test_about_tab_remove_start_menu_shows_shortcut_result(app, monkeypatch):
    """_remove_start_menu:把 remove_start_menu_shortcut().message 写状态(行 178-179)。"""
    from file_toolbox.common import shortcuts

    monkeypatch.setattr(
        shortcuts, "remove_start_menu_shortcut", lambda: _StubResult("已删除开始菜单快捷方式")
    )
    tab = AboutTab()
    tab._remove_start_menu()
    assert tab._status_lbl.text() == "已删除开始菜单快捷方式"
