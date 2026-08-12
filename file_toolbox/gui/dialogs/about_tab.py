"""关于 Tab:展示软件名称/版本/开源地址/技术路线/更新日志 + 快捷方式管理。

第 6 个 Tab,嵌入主窗口。纯展示 QWidget + 4 个快捷方式按钮。
只调用 common 层(metadata / shortcuts)返回值,不混入业务逻辑。
"""

import platform

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from file_toolbox.common import metadata, settings, shortcuts
from file_toolbox.common.paths import get_log_dir
from file_toolbox.updater.proxy import DEFAULT_PROXIES


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

        log_row = QHBoxLayout()
        log_row.addWidget(QLabel(f"日志目录: {get_log_dir()}"), stretch=1)
        btn_logs = QPushButton("打开日志目录")
        btn_logs.clicked.connect(self._open_log_directory)
        log_row.addWidget(btn_logs)
        info_layout.addLayout(log_row)

        root.addWidget(info_box)

        # --- 更新与代理组(检查更新 + 代理设置整合) ---
        update_box = QGroupBox("更新与代理")
        update_layout = QVBoxLayout(update_box)

        # 上半:检查更新
        check_row = QHBoxLayout()
        self.btn_check_update = QPushButton("检查更新")
        self.btn_check_update.clicked.connect(self._on_check_clicked)
        check_row.addWidget(self.btn_check_update)
        self._check_result_lbl = QLabel("")
        check_row.addWidget(self._check_result_lbl, stretch=1)
        update_layout.addLayout(check_row)

        # 下半:代理设置
        proxy_intro = QLabel(
            "URL 加速前缀会拼在完整 GitHub feed 地址之前，并按勾选顺序尝试；"
            "全部失败后回退直连。它不同于下方标准 forward proxy。"
        )
        proxy_intro.setWordWrap(True)
        update_layout.addWidget(proxy_intro)

        self._proxy_list = QListWidget()
        update_layout.addWidget(self._proxy_list)

        proxy_btn_row = QHBoxLayout()
        self.btn_proxy_select_all = QPushButton("全选")
        self.btn_proxy_select_all.clicked.connect(self._select_all_proxies)
        proxy_btn_row.addWidget(self.btn_proxy_select_all)
        self.btn_proxy_select_none = QPushButton("全不选")
        self.btn_proxy_select_none.clicked.connect(self._select_no_proxies)
        proxy_btn_row.addWidget(self.btn_proxy_select_none)
        proxy_btn_row.addStretch(1)
        update_layout.addLayout(proxy_btn_row)

        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("自定义代理:"))
        self._proxy_edit = QLineEdit()
        self._proxy_edit.setPlaceholderText("如 https://your-proxy.example")
        add_row.addWidget(self._proxy_edit, stretch=1)
        self.btn_proxy_add = QPushButton("添加")
        self.btn_proxy_add.clicked.connect(self._add_custom_proxy)
        add_row.addWidget(self.btn_proxy_add)
        self.btn_proxy_remove = QPushButton("移除选中")
        self.btn_proxy_remove.clicked.connect(self._remove_selected_proxy)
        add_row.addWidget(self.btn_proxy_remove)
        update_layout.addLayout(add_row)

        forward_row = QHBoxLayout()
        forward_row.addWidget(QLabel("标准 forward proxy:"))
        self._forward_proxy_edit = QLineEdit()
        self._forward_proxy_edit.setPlaceholderText("如 http://127.0.0.1:7890（留空沿用系统环境）")
        saved_forward_proxy = settings.get("forward_proxy", "")
        if isinstance(saved_forward_proxy, str):
            self._forward_proxy_edit.setText(saved_forward_proxy)
        forward_row.addWidget(self._forward_proxy_edit, stretch=1)
        update_layout.addLayout(forward_row)

        save_row = QHBoxLayout()
        self.btn_proxy_save = QPushButton("保存代理设置")
        self.btn_proxy_save.clicked.connect(self._save_proxy)
        save_row.addWidget(self.btn_proxy_save)
        save_row.addStretch(1)
        update_layout.addLayout(save_row)

        self._proxy_status_lbl = QLabel("")
        update_layout.addWidget(self._proxy_status_lbl)
        root.addWidget(update_box)

        # 填充代理列表(默认候选 + 已保存的自定义/勾选状态)
        self._populate_proxy_list()

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

    @staticmethod
    def _open_log_directory() -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(get_log_dir())))

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

        kind: "latest" | "available" | "failed"(预留:未来可按状态着色/加图标,当前仅用 text)
        text: 展示文本。
        """
        self.btn_check_update.setEnabled(True)
        self._check_result_lbl.setText(text)

    # --- GitHub 代理设置 ---
    # 列表项数据:UserRole 存归一化代理 URL;UserRole+1 存是否默认项(True 不可移除)。
    _ROLE_URL = Qt.ItemDataRole.UserRole
    _ROLE_DEFAULT = Qt.ItemDataRole.UserRole + 1

    def _populate_proxy_list(self) -> None:
        """填充代理列表:默认候选 + 已保存的自定义项,并回显勾选状态。"""
        self._proxy_list.clear()
        from file_toolbox.updater.proxy import get_enabled_proxies

        enabled = [p for p in get_enabled_proxies() if p]
        enabled_set = set(enabled)

        # 默认候选(标记为默认项,不可移除)
        for proxy in DEFAULT_PROXIES:
            item = QListWidgetItem(f"{proxy}    (默认)")
            item.setData(self._ROLE_URL, proxy)
            item.setData(self._ROLE_DEFAULT, True)
            item.setCheckState(
                Qt.CheckState.Checked if proxy in enabled_set else Qt.CheckState.Unchecked
            )
            self._proxy_list.addItem(item)

        # 已保存但不在默认列表中的 → 自定义项
        for proxy in enabled:
            if proxy not in DEFAULT_PROXIES:
                item = QListWidgetItem(proxy)
                item.setData(self._ROLE_URL, proxy)
                item.setData(self._ROLE_DEFAULT, False)
                item.setCheckState(Qt.CheckState.Checked)
                self._proxy_list.addItem(item)

        # 若旧单值 gh_proxy 未迁移进列表(冗余兜底),忽略:已被 get_enabled_proxies 迁移。

    def _select_all_proxies(self) -> None:
        """全选:勾选列表中所有代理项。"""
        for i in range(self._proxy_list.count()):
            self._proxy_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _select_no_proxies(self) -> None:
        """全不选:取消勾选所有代理项。"""
        for i in range(self._proxy_list.count()):
            self._proxy_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _add_custom_proxy(self) -> None:
        """添加自定义代理到列表(归一化后追加,默认勾选,标记为非默认项可移除)。"""
        from file_toolbox.updater.proxy import _normalize

        raw = self._proxy_edit.text().strip()
        if not raw:
            self._proxy_status_lbl.setText("请输入代理地址")
            return
        proxy = _normalize(raw)
        if not proxy:
            self._proxy_status_lbl.setText("代理地址无效")
            return
        # 去重:已存在则不重复添加,仅勾选
        for i in range(self._proxy_list.count()):
            if self._proxy_list.item(i).data(self._ROLE_URL) == proxy:
                self._proxy_list.item(i).setCheckState(Qt.CheckState.Checked)
                self._proxy_edit.clear()
                self._proxy_status_lbl.setText(f"已存在:{proxy}")
                return
        item = QListWidgetItem(proxy)
        item.setData(self._ROLE_URL, proxy)
        item.setData(self._ROLE_DEFAULT, False)
        item.setCheckState(Qt.CheckState.Checked)
        self._proxy_list.addItem(item)
        self._proxy_edit.clear()
        self._proxy_status_lbl.setText(f"已添加:{proxy}(记得保存)")

    def _remove_selected_proxy(self) -> None:
        """移除当前选中的自定义代理项(默认项不可移除,仅取消勾选)。"""
        removed = 0
        for item in self._proxy_list.selectedItems():
            if item.data(self._ROLE_DEFAULT):
                # 默认项:不可移除,仅取消勾选
                item.setCheckState(Qt.CheckState.Unchecked)
                continue
            self._proxy_list.takeItem(self._proxy_list.row(item))
            removed += 1
        if removed:
            self._proxy_status_lbl.setText(f"已移除 {removed} 个自定义代理(记得保存)")
        else:
            self._proxy_status_lbl.setText("无可移除的自定义项(默认项不可移除)")

    def _save_proxy(self) -> None:
        """分别保存 URL-prefix 候选与 standard forward proxy。"""
        enabled: list[str] = []
        for i in range(self._proxy_list.count()):
            item = self._proxy_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                url = item.data(self._ROLE_URL)
                if isinstance(url, str) and url:
                    enabled.append(url)
        # 去重保序(防重复勾选)
        seen: set[str] = set()
        deduped: list[str] = []
        for p in enabled:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        settings.set("gh_proxies", deduped)
        settings.set("forward_proxy", self._forward_proxy_edit.text().strip())
        n = len(deduped)
        self._proxy_status_lbl.setText(
            f"已保存 {n} 个代理" if n else "已保存(无勾选 = 直连 GitHub)"
        )
