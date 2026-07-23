"""关于 Tab:展示软件名称/版本/开源地址/技术路线/更新日志 + 快捷方式管理。

第 6 个 Tab,嵌入主窗口。纯展示 QWidget + 4 个快捷方式按钮。
只调用 common 层(metadata / shortcuts)返回值,不混入业务逻辑。
"""

import platform

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from file_toolbox.common import metadata, shortcuts


class AboutTab(QWidget):
    """关于界面 Tab。"""

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
        root.addWidget(info_box)

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
