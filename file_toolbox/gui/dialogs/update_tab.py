"""更新 Tab:唯一承载检查、下载/应用进度与取消的独立更新页。

本页是纯视图:不持有第二份更新状态、不创建 worker/coordinator,全部展示
由主窗口按 #128 的单一更新状态推送;页面信号(检查/下载/取消)只是请求,
由主窗口复用既有更新链执行。代理设置随本页迁移(关于页不再保留),保存后
下一轮检查即经 coordinator 工厂使用新快照。
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from file_toolbox.common import metadata, settings
from file_toolbox.updater.models import UpdateCheckResult, UpdateCheckStatus
from file_toolbox.updater.proxy import DEFAULT_PROXIES

_STATUS_COLORS = {"available": "#0969da", "failed": "#d1242f"}


class UpdateTab(QWidget):
    """独立更新页面(状态视图;主动作只有"下载并更新")。"""

    check_requested = Signal()
    download_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- 版本行:当前运行版本与目标版本分开展示(目标未知时显示 —)---
        version_row = QHBoxLayout()
        self._current_version_lbl = QLabel(f"当前运行版本 v{metadata.runtime_version()}")
        version_row.addWidget(self._current_version_lbl)
        version_row.addStretch(1)
        self._target_version_lbl = QLabel("目标版本 —")
        version_row.addWidget(self._target_version_lbl)
        layout.addLayout(version_row)

        # --- 动作行:检查更新 / 下载并更新 / 取消 ---
        action_row = QHBoxLayout()
        self.btn_check_update = QPushButton("检查更新")
        self.btn_check_update.clicked.connect(self._on_check_clicked)
        action_row.addWidget(self.btn_check_update)
        self.btn_download_update = QPushButton("下载并更新")
        self.btn_download_update.setToolTip("下载新版本,准备完成后自动退出并重启应用")
        self.btn_download_update.clicked.connect(self._on_download_clicked)
        self.btn_download_update.hide()
        action_row.addWidget(self.btn_download_update)
        self.btn_cancel_update = QPushButton("取消")
        self.btn_cancel_update.setToolTip("取消本次下载(进入应用阶段后无法取消)")
        self.btn_cancel_update.clicked.connect(self._on_cancel_clicked)
        self.btn_cancel_update.hide()
        action_row.addWidget(self.btn_cancel_update)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        restart_note = QLabel(
            "点击“下载并更新”并确认后:下载 → 校验 → 自动退出并重启;进入应用阶段后不可取消。"
        )
        restart_note.setWordWrap(True)
        layout.addWidget(restart_note)

        self._status_lbl = QLabel("尚未检查更新。可点击“检查更新”,也可等待启动时的自动检查。")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        # 启动对账结果(上次更新是否真正完成,#128 AC5)持久展示位
        self._outcome_lbl = QLabel("")
        self._outcome_lbl.setWordWrap(True)
        self._outcome_lbl.hide()
        layout.addWidget(self._outcome_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.hide()
        layout.addWidget(self._progress)

        # --- 新版本更新内容(有 release notes 时显示) ---
        self._notes_lbl = QLabel("新版本更新内容:")
        self._notes_lbl.hide()
        layout.addWidget(self._notes_lbl)
        self._notes_view = QTextBrowser()
        self._notes_view.setOpenExternalLinks(True)
        self._notes_view.setMaximumHeight(180)
        self._notes_view.hide()
        layout.addWidget(self._notes_view, stretch=1)

        # --- 高级:更新源与代理(默认折叠,不淹没版本与主动作) ---
        # checkable QGroupBox 未勾选只禁用不隐藏;内容随 toggled 真正显隐,
        # 构造末尾显式应用一次初始折叠态(toggled 只在变更时触发)。
        self._proxy_box = QGroupBox("高级:更新源与代理(点击展开)")
        self._proxy_box.setCheckable(True)
        self._proxy_box.setChecked(False)
        self._build_proxy_ui(self._proxy_box)
        self._proxy_box.toggled.connect(self._on_proxy_box_toggled)
        self._on_proxy_box_toggled(False)
        layout.addWidget(self._proxy_box)

    # --- 代理设置(自关于页迁移,语义不变) ---
    _ROLE_URL = Qt.ItemDataRole.UserRole
    _ROLE_DEFAULT = Qt.ItemDataRole.UserRole + 1

    def _on_proxy_box_toggled(self, checked: bool) -> None:
        """折叠组只保留标题行,内容随勾选真正显隐(不淹没主要动作)。"""
        # 内容行多为嵌套布局(layout 项无 widget),按后代 widget 统一处理。
        for widget in self._proxy_box.findChildren(QWidget):
            widget.setVisible(checked)

    def _build_proxy_ui(self, box: QGroupBox) -> None:
        proxy_layout = QVBoxLayout(box)

        proxy_intro = QLabel(
            "URL 加速前缀会拼在完整 GitHub feed 地址之前；检查更新时会并发探测所有勾选镜像"
            "与直连，自动选用最快可用者（勾选顺序不影响速度）；全部失败才整体失败。"
            "它不同于下方标准 forward proxy。保存后下一轮检查即生效。"
        )
        proxy_intro.setWordWrap(True)
        proxy_layout.addWidget(proxy_intro)

        self._proxy_list = QListWidget()
        self._proxy_list.setMaximumHeight(140)
        proxy_layout.addWidget(self._proxy_list)

        btn_row = QHBoxLayout()
        self.btn_proxy_select_all = QPushButton("全选")
        self.btn_proxy_select_all.clicked.connect(self._select_all_proxies)
        btn_row.addWidget(self.btn_proxy_select_all)
        self.btn_proxy_select_none = QPushButton("全不选")
        self.btn_proxy_select_none.clicked.connect(self._select_no_proxies)
        btn_row.addWidget(self.btn_proxy_select_none)
        btn_row.addStretch(1)
        proxy_layout.addLayout(btn_row)

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
        proxy_layout.addLayout(add_row)

        forward_row = QHBoxLayout()
        forward_row.addWidget(QLabel("标准 forward proxy:"))
        self._forward_proxy_edit = QLineEdit()
        self._forward_proxy_edit.setPlaceholderText("如 http://127.0.0.1:7890（留空沿用系统环境）")
        saved_forward_proxy = settings.get("forward_proxy", "")
        if isinstance(saved_forward_proxy, str):
            self._forward_proxy_edit.setText(saved_forward_proxy)
        forward_row.addWidget(self._forward_proxy_edit, stretch=1)
        proxy_layout.addLayout(forward_row)

        save_row = QHBoxLayout()
        self.btn_proxy_save = QPushButton("保存代理设置")
        self.btn_proxy_save.clicked.connect(self._save_proxy)
        save_row.addWidget(self.btn_proxy_save)
        save_row.addStretch(1)
        proxy_layout.addLayout(save_row)

        self._proxy_status_lbl = QLabel("")
        self._proxy_status_lbl.setWordWrap(True)
        proxy_layout.addWidget(self._proxy_status_lbl)

        self._populate_proxy_list()

    def _populate_proxy_list(self) -> None:
        """填充代理列表:默认候选 + 已保存的自定义项,并回显勾选状态。"""
        from file_toolbox.updater.proxy import get_enabled_proxies

        self._proxy_list.clear()
        enabled = [p for p in get_enabled_proxies() if p]
        enabled_set = set(enabled)

        for proxy in DEFAULT_PROXIES:
            item = QListWidgetItem(f"{proxy}    (默认)")
            item.setData(self._ROLE_URL, proxy)
            item.setData(self._ROLE_DEFAULT, True)
            item.setCheckState(
                Qt.CheckState.Checked if proxy in enabled_set else Qt.CheckState.Unchecked
            )
            self._proxy_list.addItem(item)

        for proxy in enabled:
            if proxy not in DEFAULT_PROXIES:
                item = QListWidgetItem(proxy)
                item.setData(self._ROLE_URL, proxy)
                item.setData(self._ROLE_DEFAULT, False)
                item.setCheckState(Qt.CheckState.Checked)
                self._proxy_list.addItem(item)

    def _select_all_proxies(self) -> None:
        for i in range(self._proxy_list.count()):
            self._proxy_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _select_no_proxies(self) -> None:
        for i in range(self._proxy_list.count()):
            self._proxy_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _add_custom_proxy(self) -> None:
        from file_toolbox.updater.proxy import _normalize

        raw = self._proxy_edit.text().strip()
        if not raw:
            self._proxy_status_lbl.setText("请输入代理地址")
            return
        proxy = _normalize(raw)
        if not proxy:
            self._proxy_status_lbl.setText("代理地址无效")
            return
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
        removed = 0
        for item in self._proxy_list.selectedItems():
            if item.data(self._ROLE_DEFAULT):
                item.setCheckState(Qt.CheckState.Unchecked)
                continue
            self._proxy_list.takeItem(self._proxy_list.row(item))
            removed += 1
        if removed:
            self._proxy_status_lbl.setText(f"已移除 {removed} 个自定义代理(记得保存)")
        else:
            self._proxy_status_lbl.setText("无可移除的自定义项(默认项不可移除)")

    def _save_proxy(self) -> None:
        enabled: list[str] = []
        for i in range(self._proxy_list.count()):
            item = self._proxy_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                url = item.data(self._ROLE_URL)
                if isinstance(url, str) and url:
                    enabled.append(url)
        seen: set[str] = set()
        deduped: list[str] = []
        for proxy in enabled:
            if proxy not in seen:
                seen.add(proxy)
                deduped.append(proxy)
        settings.set("gh_proxies", deduped)
        settings.set("forward_proxy", self._forward_proxy_edit.text().strip())
        n = len(deduped)
        self._proxy_status_lbl.setText(
            f"已保存 {n} 个代理" if n else "已保存(无勾选 = 直连 GitHub)"
        )

    # --- 动作信号 ---
    def _on_check_clicked(self) -> None:
        self.set_checking()
        self.check_requested.emit()

    def _on_download_clicked(self) -> None:
        self.download_requested.emit()

    def _on_cancel_clicked(self) -> None:
        self.cancel_requested.emit()

    # --- 主窗口推送的展示状态 ---
    def _set_status(self, text: str, kind: str = "") -> None:
        color = _STATUS_COLORS.get(kind)
        self._status_lbl.setStyleSheet(f"color: {color}; font-weight: 600;" if color else "")
        self._status_lbl.setText(text)

    def set_checking(self) -> None:
        self.btn_check_update.setEnabled(False)
        self._target_version_lbl.setText("目标版本 —")
        self._hide_update_affordances()
        self._set_status("检查更新中…")

    def display_check_result(self, result: UpdateCheckResult) -> None:
        """任何检查结果(自动/手动)的完整展示;状态语义来自 #128 契约。"""
        self.btn_check_update.setEnabled(True)
        self._current_version_lbl.setText(
            f"当前运行版本 v{result.current_version or metadata.runtime_version()}"
        )
        if result.status is UpdateCheckStatus.AVAILABLE:
            self._target_version_lbl.setText(f"目标版本 v{result.version}")
            self._set_status(f"🆕 发现新版本 v{result.version},可下载并更新", "available")
            notes = result.release_notes.strip()
            if notes:
                self._notes_view.setMarkdown(notes)
                self._notes_lbl.show()
                self._notes_view.show()
            else:
                self._notes_lbl.hide()
                self._notes_view.hide()
            self.btn_download_update.show()
        else:
            self._target_version_lbl.setText("目标版本 —")
            self._hide_update_affordances()
            if result.status is UpdateCheckStatus.UNSUPPORTED:
                self._set_status(f"⚠ {result.message or '当前运行形态不支持应用内更新'}", "failed")
            elif result.status is UpdateCheckStatus.FAILED:
                self._set_status(
                    f"⚠ {result.message or '检查更新失败,请检查网络或代理设置'}", "failed"
                )
            else:  # latest
                self._set_status("✓ 当前为最新版本,无需更新")

    def set_startup_outcome(self, message: str) -> None:
        """上次更新跨启动对账结果(#128 AC5);为空则隐藏。"""
        if message:
            self._outcome_lbl.setText(message)
            self._outcome_lbl.show()
        else:
            self._outcome_lbl.hide()

    def begin_download(self, version: str) -> None:
        """下载开始:进度与取消就位,主动作与检查禁用。"""
        self.btn_check_update.setEnabled(False)
        self.btn_download_update.setEnabled(False)
        self.btn_download_update.setText("下载中…")
        self.btn_cancel_update.show()
        self.btn_cancel_update.setEnabled(True)
        self._progress.setValue(0)
        self._progress.show()
        self._set_status(f"正在下载 v{version}…")

    def set_download_progress(self, value: int) -> None:
        clamped = max(0, min(100, value))
        self._progress.setValue(clamped)
        if clamped >= 100:
            self._set_status("已下载完成,正在校验并准备更新…")

    def set_cancelling(self) -> None:
        self.btn_cancel_update.setEnabled(False)
        self._set_status("正在取消更新,请等待当前请求结束…")

    def enter_apply_phase(self) -> None:
        """已跨过不可取消边界:隐藏取消,明确重启语义。"""
        self.btn_cancel_update.hide()
        self._set_status("正在应用更新,已无法取消;完成后应用将自动重启。")

    def set_uncertain(self, message: str) -> None:
        """apply 提交后结果不确定:如实呈现,保持动作禁用以防重复提交。"""
        self.btn_cancel_update.hide()
        self._set_status(f"⚠ {message}", "failed")

    def finish_download(self, *, restored: bool) -> None:
        """下载事务结束(取消/失败);恢复可重试入口。"""
        self._progress.hide()
        self.btn_cancel_update.hide()
        self.btn_cancel_update.setEnabled(True)
        self.btn_check_update.setEnabled(True)
        self.btn_download_update.setEnabled(True)
        self.btn_download_update.setText("下载并更新")
        if not restored:
            # 过期候选已被后续检查清除:收起主动作
            self._hide_update_affordances()
            self._target_version_lbl.setText("目标版本 —")

    def set_status_message(self, text: str, kind: str = "") -> None:
        """下载事务结束后的结果性提示(已取消/失败等)。"""
        self._set_status(text, kind)

    def _hide_update_affordances(self) -> None:
        self.btn_download_update.hide()
        self._notes_lbl.hide()
        self._notes_view.hide()
