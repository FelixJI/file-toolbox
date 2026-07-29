"""AboutTab GUI 冒烟测试:验证控件存在 + 数据正确渲染,不实际点按钮。"""

import pytest

# 用 QtWidgets 子模块做 importorskip:仅检查顶层 PySide6 包不够——它会成功 import,
# 但 from PySide6.QtWidgets import ... 才真正加载 libEGL/libGL 等原生库。Linux 无
# 这些系统库时,顶层 importorskip 不跳过,反而在后续 import 处抛 ImportError 致收集失败。
pytest.importorskip("PySide6.QtWidgets")

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


from PySide6.QtWidgets import QLineEdit  # noqa: E402


def test_about_tab_has_check_update_button(app):
    tab = AboutTab()
    buttons = tab.findChildren(QPushButton)
    texts = [b.text() for b in buttons]
    assert any("检查更新" in t for t in texts)


def test_about_tab_emits_check_requested(app):
    """点检查更新按钮 → emit check_requested。"""
    tab = AboutTab()
    received: list = []
    tab.check_requested.connect(lambda: received.append(1))
    # 找到检查更新按钮并点击
    btn = next(b for b in tab.findChildren(QPushButton) if "检查更新" in b.text())
    btn.click()
    assert received == [1]


def test_about_tab_check_button_disables_during_check(app):
    """点击后按钮立即禁用 + 结果标签显示检查中。"""
    tab = AboutTab()
    btn = next(b for b in tab.findChildren(QPushButton) if "检查更新" in b.text())
    btn.click()
    assert btn.isEnabled() is False
    assert "检查中" in tab._check_result_lbl.text()


def test_about_tab_display_check_result_latest(app):
    tab = AboutTab()
    # 先触发检查(禁用按钮),再回调结果
    btn = next(b for b in tab.findChildren(QPushButton) if "检查更新" in b.text())
    btn.click()
    tab.display_check_result("latest", "✓ 当前为最新版本 v0.1.11")
    assert btn.isEnabled() is True
    assert "最新" in tab._check_result_lbl.text()


def test_about_tab_display_check_result_available(app):
    tab = AboutTab()
    btn = next(b for b in tab.findChildren(QPushButton) if "检查更新" in b.text())
    btn.click()
    tab.display_check_result("available", "🆕 发现新版本 v9.9.9")
    assert btn.isEnabled() is True
    assert "9.9.9" in tab._check_result_lbl.text()


def test_about_tab_display_check_result_failed(app):
    tab = AboutTab()
    btn = next(b for b in tab.findChildren(QPushButton) if "检查更新" in b.text())
    btn.click()
    tab.display_check_result("failed", "⚠ 检查失败")
    assert btn.isEnabled() is True
    assert "检查失败" in tab._check_result_lbl.text()


def test_about_tab_has_proxy_edit(app):
    tab = AboutTab()
    assert isinstance(tab._proxy_edit, QLineEdit)


def test_about_tab_save_proxy_writes_settings(app, monkeypatch, tmp_path):
    """保存按钮 → settings 写入输入框值。"""
    monkeypatch.chdir(tmp_path)
    from file_toolbox.common import settings

    tab = AboutTab()
    tab._proxy_edit.setText("https://ghproxy.example")
    tab.btn_proxy_save.click()
    assert settings.get("gh_proxy") == "https://ghproxy.example"


def test_about_tab_clear_proxy_empties_settings(app, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from file_toolbox.common import settings

    settings.set("gh_proxy", "https://old.example")
    tab = AboutTab()
    tab.btn_proxy_clear.click()
    assert settings.get("gh_proxy") == ""


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
