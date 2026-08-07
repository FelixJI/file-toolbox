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
from file_toolbox.common import metadata  # noqa: E402
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
    # 精确匹配权威仓库 URL,而非 "github.com" 子串(避免 notgithub.com 等误匹配,
    # 也消除 CodeQL Incomplete URL substring sanitization 告警)。
    assert metadata.REPO_URL in _collect_text(tab)


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


# ---------------------------------------------------------------------------
# 更新与代理整合分组 + 默认候选 / 全选 / 自定义添加 / 保存
# ---------------------------------------------------------------------------


def test_about_tab_has_update_and_proxy_group(app):
    """关于 Tab 应含'更新与代理'分组(整合检查更新与代理设置)。"""
    from PySide6.QtWidgets import QGroupBox

    tab = AboutTab()
    boxes = [b.title() for b in tab.findChildren(QGroupBox)]
    assert any("更新与代理" in t for t in boxes)


def test_about_tab_proxy_list_has_defaults(app):
    """代理列表应列出 DEFAULT_PROXIES(默认项)。"""
    from PySide6.QtWidgets import QListWidget

    from file_toolbox.updater.proxy import DEFAULT_PROXIES

    tab = AboutTab()
    lst = tab.findChild(QListWidget)
    assert lst is not None
    texts = [lst.item(i).text() for i in range(lst.count())]
    # 每个默认代理出现在某条目文本中(默认项带"(默认)"后缀)
    for p in DEFAULT_PROXIES:
        assert any(p in t for t in texts), f"默认代理 {p} 未出现在列表"


def test_about_tab_proxy_select_all(app):
    """全选按钮 → 列表所有项 checked。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidget

    tab = AboutTab()
    tab.btn_proxy_select_none.click()  # 先全不选
    tab.btn_proxy_select_all.click()
    lst = tab.findChild(QListWidget)
    for i in range(lst.count()):
        assert lst.item(i).checkState() == Qt.CheckState.Checked


def test_about_tab_proxy_select_none(app):
    """全不选按钮 → 列表所有项 unchecked。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidget

    tab = AboutTab()
    tab.btn_proxy_select_all.click()  # 先全选
    tab.btn_proxy_select_none.click()
    lst = tab.findChild(QListWidget)
    for i in range(lst.count()):
        assert lst.item(i).checkState() == Qt.CheckState.Unchecked


def test_about_tab_add_custom_proxy(app):
    """添加自定义代理 → 列表新增一项且默认勾选。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidget

    tab = AboutTab()
    tab._proxy_edit.setText("https://my-proxy.example")
    tab.btn_proxy_add.click()
    lst = tab.findChild(QListWidget)
    urls = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
    assert "https://my-proxy.example" in urls
    # 新增项默认勾选
    idx = urls.index("https://my-proxy.example")
    assert lst.item(idx).checkState() == Qt.CheckState.Checked
    # 输入框被清空
    assert tab._proxy_edit.text() == ""


def test_about_tab_add_duplicate_proxy_no_dup(app):
    """添加已存在的代理 → 不重复添加,仅勾选已存在项。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidget

    from file_toolbox.updater.proxy import DEFAULT_PROXIES

    tab = AboutTab()
    tab._proxy_edit.setText(DEFAULT_PROXIES[0])  # 与默认项重复
    tab.btn_proxy_add.click()
    lst = tab.findChild(QListWidget)
    urls = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
    assert urls.count(DEFAULT_PROXIES[0]) == 1  # 仍只有一项


def test_about_tab_save_writes_checked_proxies(app, monkeypatch, tmp_path):
    """保存按钮 → settings['gh_proxies'] = 列表中所有已勾选项。"""
    monkeypatch.chdir(tmp_path)
    from file_toolbox.common import settings

    tab = AboutTab()
    tab.btn_proxy_select_none.click()  # 先全不选
    # 手动勾选第一个默认项
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidget

    lst = tab.findChild(QListWidget)
    first_url = lst.item(0).data(Qt.ItemDataRole.UserRole)
    lst.item(0).setCheckState(Qt.CheckState.Checked)
    tab.btn_proxy_save.click()
    assert settings.get("gh_proxies") == [first_url]


def test_about_tab_save_none_means_direct(app, monkeypatch, tmp_path):
    """全不选保存 → settings['gh_proxies'] 为空列表(= 直连)。"""
    monkeypatch.chdir(tmp_path)
    from file_toolbox.common import settings

    tab = AboutTab()
    tab.btn_proxy_select_none.click()
    tab.btn_proxy_save.click()
    assert settings.get("gh_proxies") == []


def test_about_tab_remove_custom_proxy(app):
    """移除选中 → 自定义项被移除;默认项不可移除(仅取消勾选)。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidget

    tab = AboutTab()
    # 添加一个自定义项
    tab._proxy_edit.setText("https://removable.example")
    tab.btn_proxy_add.click()
    lst = tab.findChild(QListWidget)
    # 找到自定义项并选中
    custom_row = None
    for i in range(lst.count()):
        if lst.item(i).data(Qt.ItemDataRole.UserRole) == "https://removable.example":
            custom_row = i
            break
    assert custom_row is not None
    lst.setCurrentRow(custom_row)
    urls_before = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
    assert "https://removable.example" in urls_before
    tab.btn_proxy_remove.click()
    urls_after = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
    assert "https://removable.example" not in urls_after


def test_about_tab_default_items_not_removable(app):
    """移除默认项 → 不删除,仅取消勾选。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidget

    tab = AboutTab()
    lst = tab.findChild(QListWidget)
    # 选中第一个(默认)项并尝试移除
    lst.setCurrentRow(0)
    first_url = lst.item(0).data(Qt.ItemDataRole.UserRole)
    count_before = lst.count()
    tab.btn_proxy_remove.click()
    # 默认项仍在(数量不变),只是被取消勾选
    urls = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
    assert first_url in urls
    assert lst.count() == count_before


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
