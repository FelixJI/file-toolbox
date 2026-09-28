"""关于 Tab:应用名/版本/能力简介、仓库与许可证、运行信息、更新日志与快捷方式。

更新检查、下载与代理设置集中在独立"更新"页(见 update_tab.py);本页只保留
"打开更新页面"导航,不再承载任何更新动作。技术路线与完整更新日志为次要长
内容,默认折叠,需要时展开。
"""

import platform

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from file_toolbox.common import metadata, shortcuts
from file_toolbox.common.paths import get_log_dir


class AboutTab(QWidget):
    """关于界面 Tab(纯展示 + 快捷方式管理 + 更新页导航)。"""

    # 用户点"打开更新页面"时请求主窗口切换到独立更新页(不触发任何更新动作)
    open_update_page_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        # 内容整体包进 QScrollArea:关于页是长竖排,滚动容器把页最小尺寸压到
        # 滚动区级别,窗口可自由缩小、内容滚动查看。
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # --- 标题区 ---
        title = QLabel(metadata.APP_NAME)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = title.font()
        f.setPointSize(20)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        version_lbl = QLabel(f"版本 {metadata.runtime_version()}")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(version_lbl)

        desc_lbl = QLabel(metadata.APP_DESCRIPTION)
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)
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

        log_row = QHBoxLayout()
        log_row.addWidget(QLabel(f"日志目录: {get_log_dir()}"), stretch=1)
        btn_logs = QPushButton("打开日志目录")
        btn_logs.clicked.connect(self._open_log_directory)
        log_row.addWidget(btn_logs)
        info_layout.addLayout(log_row)
        root.addWidget(info_box)

        # --- 更新入口:仅导航 ---
        update_box = QGroupBox("软件更新")
        update_layout = QVBoxLayout(update_box)
        update_hint = QLabel("检查更新、下载与进度、更新源与代理设置都在“更新”页面。")
        update_hint.setWordWrap(True)
        update_layout.addWidget(update_hint)
        self.btn_open_update_page = QPushButton("打开更新页面")
        self.btn_open_update_page.clicked.connect(self._on_open_update_page)
        update_layout.addWidget(self.btn_open_update_page)
        root.addWidget(update_box)

        # --- 技术路线组(次要长内容,默认折叠) ---
        # checkable QGroupBox 未勾选时只禁用不隐藏子控件;用内容容器 +
        # toggled→setVisible 实现真正的折叠/展开。
        tech_box = QGroupBox("技术路线(点击展开)")
        tech_box.setCheckable(True)
        tech_box.setChecked(False)
        tech_layout = QVBoxLayout(tech_box)
        tech_body = QWidget()
        tech_body_layout = QVBoxLayout(tech_body)
        tech_body_layout.setContentsMargins(0, 0, 0, 0)
        for name, note in metadata.TECH_STACK:
            tech_body_layout.addWidget(QLabel(f"{name}    {note}"))
        tech_layout.addWidget(tech_body)
        tech_box.toggled.connect(tech_body.setVisible)
        tech_body.hide()
        root.addWidget(tech_box)

        # --- 更新日志组(次要长内容,默认折叠) ---
        log_box = QGroupBox("更新日志(点击展开)")
        log_box.setCheckable(True)
        log_box.setChecked(False)
        log_layout = QVBoxLayout(log_box)
        log_body = QWidget()
        log_body_layout = QVBoxLayout(log_body)
        log_body_layout.setContentsMargins(0, 0, 0, 0)
        self._changelog = QTextBrowser()
        self._changelog.setOpenExternalLinks(True)
        self._changelog.setMarkdown(metadata.get_changelog())
        self._changelog.setMinimumHeight(240)
        log_body_layout.addWidget(self._changelog)
        log_layout.addWidget(log_body)
        log_box.toggled.connect(log_body.setVisible)
        log_body.hide()
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

    @staticmethod
    def _open_log_directory() -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(get_log_dir())))

    def _on_open_update_page(self) -> None:
        self.open_update_page_requested.emit()

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
