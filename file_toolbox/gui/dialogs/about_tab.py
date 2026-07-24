"""关于 Tab:展示软件名称/版本/开源地址/技术路线/更新日志 + 快捷方式管理。

第 6 个 Tab,嵌入主窗口。纯展示 QWidget + 4 个快捷方式按钮。
只调用 common 层(metadata / shortcuts)返回值,不混入业务逻辑。
"""

import platform

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from file_toolbox.common import metadata, settings, shortcuts


class AboutTab(QWidget):
    """关于界面 Tab。"""

    # 用户点检查更新时向主窗口请求(主窗口投递 worker 并回调结果)
    check_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- 标题区 ---
        title = QLabel(metadata.APP_NAME)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = title.font()
        f.setPointSize(20)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        version_lbl = QLabel(f"版本 {metadata.VERSION}")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(version_lbl)

        desc_lbl = QLabel(metadata.APP_DESCRIPTION)
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(desc_lbl)

        # --- 基本信息组 ---
        info_box = QGroupBox("基本信息")
        info_layout = QVBoxLayout(info_box)

        repo_row = QHBoxLayout()
        repo_row.addWidget(QLabel("开源地址:"))
        repo_link = QLabel(f'<a href="{metadata.REPO_URL}">{metadata.REPO_URL}</a>')
        repo_link.setOpenExternalLinks(True)
        repo_link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        repo_row.addWidget(repo_link, stretch=1)
        btn_copy = QPushButton("复制")
        btn_copy.clicked.connect(self._copy_repo_url)
        repo_row.addWidget(btn_copy)
        info_layout.addLayout(repo_row)

        info_layout.addWidget(QLabel(f"许可证: {metadata.LICENSE}"))
        info_layout.addWidget(QLabel(f"Python 要求: {metadata.PYTHON_REQUIREMENT}"))
        info_layout.addWidget(QLabel(f"运行环境: {platform.platform()}"))

        # --- 检查更新行(基本信息组内) ---
        check_row = QHBoxLayout()
        self.btn_check_update = QPushButton("检查更新")
        self.btn_check_update.clicked.connect(self._on_check_clicked)
        check_row.addWidget(self.btn_check_update)
        self._check_result_lbl = QLabel("")
        check_row.addWidget(self._check_result_lbl, stretch=1)
        info_layout.addLayout(check_row)

        root.addWidget(info_box)

        # --- GitHub 代理组 ---
        proxy_box = QGroupBox("GitHub 代理(可选)")
        proxy_layout = QVBoxLayout(proxy_box)
        proxy_intro = QLabel("用于加速版本检查与更新下载。留空则直连 GitHub。")
        proxy_intro.setWordWrap(True)
        proxy_layout.addWidget(proxy_intro)
        proxy_row = QHBoxLayout()
        proxy_row.addWidget(QLabel("代理地址:"))
        self._proxy_edit = QLineEdit()
        self._proxy_edit.setPlaceholderText("如 https://ghproxy.com")
        # 初始化为已保存的值(环境变量优先显示)
        from file_toolbox.updater.proxy import get_proxy

        self._proxy_edit.setText(get_proxy())
        proxy_row.addWidget(self._proxy_edit, stretch=1)
        self.btn_proxy_save = QPushButton("保存")
        self.btn_proxy_save.clicked.connect(self._save_proxy)
        proxy_row.addWidget(self.btn_proxy_save)
        self.btn_proxy_clear = QPushButton("清空")
        self.btn_proxy_clear.clicked.connect(self._clear_proxy)
        proxy_row.addWidget(self.btn_proxy_clear)
        proxy_layout.addLayout(proxy_row)
        self._proxy_status_lbl = QLabel("")
        proxy_layout.addWidget(self._proxy_status_lbl)
        root.addWidget(proxy_box)

        # --- 技术路线组 ---
        tech_box = QGroupBox("技术路线")
        tech_layout = QVBoxLayout(tech_box)
        for name, note in metadata.TECH_STACK:
            tech_layout.addWidget(QLabel(f"{name}    {note}"))
        root.addWidget(tech_box)

        # --- 更新日志组 ---
        log_box = QGroupBox("更新日志")
        log_layout = QVBoxLayout(log_box)
        self._changelog = QPlainTextEdit()
        self._changelog.setReadOnly(True)
        mono = self._changelog.font()
        mono.setFamily("Consolas, Monaco, monospace")
        self._changelog.setFont(mono)
        self._changelog.setPlainText(metadata.get_changelog())
        log_layout.addWidget(self._changelog)
        root.addWidget(log_box, stretch=1)

        # --- 快捷方式操作区 ---
        sc_box = QGroupBox("快捷方式")
        sc_layout = QVBoxLayout(sc_box)

        desk_row = QHBoxLayout()
        desk_row.addWidget(QLabel("桌面:"))
        btn_desk_add = QPushButton("添加到桌面")
        btn_desk_add.clicked.connect(self._add_desktop)
        btn_desk_rm = QPushButton("从桌面移除")
        btn_desk_rm.clicked.connect(self._remove_desktop)
        desk_row.addWidget(btn_desk_add)
        desk_row.addWidget(btn_desk_rm)
        desk_row.addStretch(1)
        sc_layout.addLayout(desk_row)

        start_row = QHBoxLayout()
        start_row.addWidget(QLabel("开始菜单:"))
        btn_start_add = QPushButton("添加到开始菜单")
        btn_start_add.clicked.connect(self._add_start_menu)
        btn_start_rm = QPushButton("从开始菜单移除")
        btn_start_rm.clicked.connect(self._remove_start_menu)
        start_row.addWidget(btn_start_add)
        start_row.addWidget(btn_start_rm)
        start_row.addStretch(1)
        sc_layout.addLayout(start_row)

        self._status_lbl = QLabel("")
        sc_layout.addWidget(self._status_lbl)
        root.addWidget(sc_box)

    # --- 快捷方式操作 ---
    def _copy_repo_url(self) -> None:
        QGuiApplication.clipboard().setText(metadata.REPO_URL)
        self._status_lbl.setText("已复制开源地址到剪贴板")

    def _add_desktop(self) -> None:
        r = shortcuts.create_desktop_shortcut()
        self._status_lbl.setText(r.message)

    def _remove_desktop(self) -> None:
        r = shortcuts.remove_desktop_shortcut()
        self._status_lbl.setText(r.message)

    def _add_start_menu(self) -> None:
        r = shortcuts.create_start_menu_shortcut()
        self._status_lbl.setText(r.message)

    def _remove_start_menu(self) -> None:
        r = shortcuts.remove_start_menu_shortcut()
        self._status_lbl.setText(r.message)

    # --- 检查更新 ---
    def _on_check_clicked(self) -> None:
        """点击检查更新:禁用按钮 + 显示检查中 + 请求主窗口执行。"""
        self.btn_check_update.setEnabled(False)
        self._check_result_lbl.setText("检查中…")
        self.check_requested.emit()

    def display_check_result(self, kind: str, text: str) -> None:
        """主窗口回调:显示检查结果并恢复按钮。

        kind: "latest" | "available" | "failed"
        text: 展示文本。
        """
        self.btn_check_update.setEnabled(True)
        self._check_result_lbl.setText(text)

    # --- GitHub 代理设置 ---
    def _save_proxy(self) -> None:
        value = self._proxy_edit.text().strip()
        settings.set("gh_proxy", value)
        self._proxy_status_lbl.setText("已保存" if value else "已保存(空 = 直连)")

    def _clear_proxy(self) -> None:
        self._proxy_edit.setText("")
        settings.set("gh_proxy", "")
        self._proxy_status_lbl.setText("已清空")
