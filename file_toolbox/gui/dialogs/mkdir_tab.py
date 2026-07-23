"""建文件夹 Tab:从层级或粘贴的 Excel 表格批量创建文件夹结构。"""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QTableWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_mkdir import (
    ConflictStrategy,
    FolderCreatorService,
    FolderStructureItem,
)
from file_toolbox.gui.controllers.mkdir_controller import MkdirController
from file_toolbox.gui.generated.ui_mkdir_dialog import Ui_BatchFolderCreatorDialog

# 冲突策略下拉框:显示文本 -> ConflictStrategy
_CONFLICT_OPTIONS = {
    "合并(保留已存在)": ConflictStrategy.MERGE,
    "跳过已存在": ConflictStrategy.SKIP,
    "逐个确认": ConflictStrategy.CONFIRM,
}


class BatchFolderCreatorDialog(QDialog):
    """批量创建文件夹对话框(作为 Tab 嵌入)。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_BatchFolderCreatorDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI code
        self._svc = FolderCreatorService()
        self._controller = MkdirController(self._svc)
        self._history = JsonHistoryStore()

        self.ui.btn_cancel.setVisible(False)
        # label_error 带红色边框样式,默认空内容时会显示一个空红框 -> 默认隐藏
        self.ui.label_error.setVisible(False)

        self._add_conflict_selector()
        self._connect_signals()
        self._refresh_ui_state()

    # ---------- 初始化 ----------

    def _add_conflict_selector(self) -> None:
        """在特殊字符按钮所在行追加冲突策略下拉框。

        生成的 UI 没有冲突策略控件,这里以最小侵入方式补充。
        """
        self._combo_conflict = QComboBox(self)
        for label in _CONFLICT_OPTIONS:
            self._combo_conflict.addItem(label)
        # 复用 label_error 之后的布局:新建一行放冲突策略
        row = QHBoxLayout()
        row.addWidget(self.ui.btn_fix_special_chars)
        row.addStretch(1)
        row.addWidget(self._combo_conflict)
        # btn_fix_special_chars 原本是直接加到 verticalLayout_main,
        # 把它从原布局移除后重新装入新行
        self.ui.verticalLayout_main.removeWidget(self.ui.btn_fix_special_chars)
        wrap = QWidget(self)
        wrap.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.ui.verticalLayout_main.insertWidget(
            self.ui.verticalLayout_main.indexOf(self.ui.btn_fix_special_chars) + 1, wrap
        )

    def _connect_signals(self) -> None:
        self.ui.btn_browse_root.clicked.connect(self._browse_root)
        self.ui.btn_clear.clicked.connect(self._clear)
        self.ui.btn_fix_special_chars.clicked.connect(self._fix_special_chars)
        self.ui.btn_create_folders.clicked.connect(self._create_folders)
        self.ui.btn_open_root.clicked.connect(self._open_root)
        self.ui.table_paste.cellChanged.connect(self._on_table_changed)
        self.ui.line_edit_root_path.textChanged.connect(self._refresh_ui_state)

    # ---------- UI 状态 ----------

    def _refresh_ui_state(self) -> None:
        """根据表格/根目录内容刷新各按钮启用状态与预览树。"""
        has_structures = bool(self._collect_structures())
        self.ui.btn_create_folders.setEnabled(has_structures)
        self.ui.btn_fix_special_chars.setEnabled(has_structures)

        root = self._root_path()
        self.ui.btn_open_root.setEnabled(root.exists() and root.is_dir())

        self._refresh_preview()

    def _on_table_changed(self) -> None:
        self._refresh_ui_state()

    # ---------- 错误提示 ----------

    def _show_error(self, message: str) -> None:
        self.ui.label_error.setText(message)
        self.ui.label_error.setVisible(bool(message))

    # ---------- 文件/目录 ----------

    def _browse_root(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择根目录")
        if d:
            self.ui.line_edit_root_path.setText(d)

    def _root_path(self) -> Path:
        return Path(self.ui.line_edit_root_path.text().strip() or ".")

    def _clear(self) -> None:
        self._paste_table().clearContents()
        self._paste_table().setRowCount(0)
        self._show_error("")
        self._refresh_ui_state()

    def _paste_table(self) -> QTableWidget:
        return self.ui.table_paste

    # ---------- 预览 ----------

    def _refresh_preview(self) -> None:
        """根据表格内容重建右侧文件夹结构预览树。"""
        tree: QTreeWidget = self.ui.tree_preview
        tree.clear()
        structures = self._collect_structures()
        if not structures:
            return
        root = self._root_path()
        items = self._svc.build_folder_paths(root, structures)
        # 用字典缓存已创建的顶层节点,按 levels 前缀聚合,避免重复显示
        nodes: dict[tuple[str, ...], QTreeWidgetItem] = {}
        for it in items:
            parent: QTreeWidgetItem | None = None
            prefix: tuple[str, ...] = ()
            for level in it.levels:
                prefix = prefix + (level,)
                if prefix in nodes:
                    parent = nodes[prefix]
                    continue
                node = QTreeWidgetItem([level])
                node.setData(0, Qt.ItemDataRole.UserRole, str(root.joinpath(*prefix)))
                if it.exists and prefix == it.levels:
                    node.setForeground(0, Qt.GlobalColor.gray)
                if parent is None:
                    tree.addTopLevelItem(node)
                else:
                    parent.addChild(node)
                nodes[prefix] = node
                parent = node
        tree.expandAll()

    # ---------- 特殊字符处理 ----------

    def _fix_special_chars(self) -> None:
        """处理粘贴表中的特殊字符:替换为下划线 或 直接删除。

        对应 service 的 replace_special_chars / remove_special_chars。
        """
        mode, ok = QInputDialog.getItem(
            self,
            "处理特殊字符",
            "选择处理方式:",
            ["替换为下划线", "删除"],
            0,
            editable=False,
        )
        if not ok:
            return
        is_delete = mode == "删除"
        process = self._svc.remove_special_chars if is_delete else self._svc.replace_special_chars
        action = "删除" if is_delete else "替换"

        tbl = self._paste_table()
        changed = 0
        # 暂时阻塞信号,避免 cellChanged 反复触发预览重建
        tbl.blockSignals(True)
        try:
            for r in range(tbl.rowCount()):
                for c in range(tbl.columnCount()):
                    item = tbl.item(r, c)
                    if item and item.text():
                        fixed = process(item.text())
                        if fixed != item.text():
                            item.setText(fixed)
                            changed += 1
        finally:
            tbl.blockSignals(False)
        self._refresh_ui_state()
        QMessageBox.information(self, "处理完成", f"已{action} {changed} 处特殊字符。")

    # ---------- 结构收集与校验 ----------

    def _collect_structures(self) -> list[tuple[str, ...]]:
        """从粘贴表格读取层级结构(按行,Tab 感知用列)。

        表格读取留在 View,结构构建委托给 controller(纯 Python,可单测)。
        """
        tbl = self._paste_table()
        rows: list[list[str]] = []
        for r in range(tbl.rowCount()):
            cells: list[str] = []
            for c in range(tbl.columnCount()):
                item = tbl.item(r, c)
                cells.append(item.text() if item else "")
            rows.append(cells)
        return self._controller.collect_structures(rows)

    def _find_invalid_names(self, structures: list[tuple[str, ...]]) -> list[str]:
        """返回含非法字符的文件夹名。"""
        return self._controller.find_invalid_names(structures)

    # ---------- 创建 ----------

    def _selected_strategy(self) -> ConflictStrategy:
        return _CONFLICT_OPTIONS.get(self._combo_conflict.currentText(), ConflictStrategy.MERGE)

    def _make_skip_callback(self) -> Callable[[FolderStructureItem], bool]:
        """构造逐个确认回调:对已存在文件夹弹窗询问,返回 True 表示跳过。

        对应 service.create_folders 的 skip_callback 参数(CONFIRM 策略)。
        """

        def _ask(item: FolderStructureItem) -> bool:
            reply = QMessageBox.question(
                self,
                "文件夹已存在",
                f"已存在:\n{item.path}\n\n是否跳过?(选「否」则保留/合并)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return reply == QMessageBox.StandardButton.Yes

        return _ask

    def _create_folders(self) -> None:
        structures = self._collect_structures()
        if not structures:
            QMessageBox.information(self, "提示", "请先在表格中粘贴或输入文件夹结构。")
            return

        # 校验非法字符
        invalid = self._find_invalid_names(structures)
        if invalid:
            preview = "、".join(invalid[:5])
            self._show_error(
                f'以下名称含非法字符 \\ / : * ? " < > |: {preview}'
                + (" 等" if len(invalid) > 5 else "")
                + "。请点击「处理特殊字符」或手动修改。"
            )
            return
        self._show_error("")

        root = self._root_path()
        items = self._svc.build_folder_paths(root, structures)
        existing = self._svc.count_existing_folders(items)
        strategy = self._selected_strategy()
        strategy_label = {
            ConflictStrategy.MERGE: "合并",
            ConflictStrategy.SKIP: "跳过",
            ConflictStrategy.CONFIRM: "逐个确认",
        }[strategy]
        reply = QMessageBox.question(
            self,
            "确认创建",
            f"将在 {root} 下创建 {len(items)} 个文件夹"
            f"({existing} 个已存在,处理方式: {strategy_label})。",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        # CONFIRM 策略:对每个已存在文件夹弹窗询问是否跳过
        skip_callback = self._make_skip_callback() if strategy == ConflictStrategy.CONFIRM else None
        result = self._svc.create_folders(items, strategy, skip_callback=skip_callback)
        # 记录历史(文件夹创建不可逆,仅供审计/复现)
        self._history.add_record(
            "mkdir",
            self._controller.build_history_record(
                root=root,
                structure_count=len(structures),
                strategy=strategy,
                created=result.created_count,
                skipped=result.skipped_count,
                success=result.success,
            ),
        )
        QMessageBox.information(
            self,
            "完成" if result.success else "出错",
            f"新建 {result.created_count}, 跳过 {result.skipped_count}, 共 {result.total_count}"
            + (f"\n{result.error_message}" if result.error_message else ""),
        )
        self._refresh_ui_state()

    def _open_root(self) -> None:
        import os
        import sys

        root = str(self._root_path())
        if sys.platform == "win32":
            os.startfile(root)
        elif sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", root])
        else:
            import subprocess

            subprocess.Popen(["xdg-open", root])

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)
