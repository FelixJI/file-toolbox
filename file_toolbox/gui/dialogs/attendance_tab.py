"""考勤汇总 Tab：配置方案、强制预览并安全另存结果。

页面控件只做编辑视图与交互绑定;表单字段、映射/规则与预览调整的权威状态在
core.attendance.form_state.AttendanceFormState(无 Qt),方案/请求构建与关键校验
复用该模块。分组/人员预览经专属 Model/View(attendance_models)展示,排序/筛选
只影响显示,不改变人员身份;映射与规则小表格继续用 QTableWidget 编辑并同步回
状态。任务结果/线程结束/异步关闭边界由 TaskLifecycle 统一管理。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import ClassVar, Literal, cast

from PySide6.QtCore import QSortFilterProxyModel, Qt, QThread
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.attendance import (
    AttendancePlan,
    AttendancePlanStore,
    AttendancePreview,
    AttendanceRequest,
    AttendanceResult,
    AttendanceRule,
    AttendanceService,
    CellMapping,
)
from file_toolbox.core.attendance.form_state import (
    MappingRole,
    MappingSelection,
    apply_plan_to_state,
    build_plan,
    build_preview_rows,
    build_request,
    capture_preview_adjustments,
    default_form_state,
    default_output_name,
)
from file_toolbox.core.office_capability import format_statuses, tool_capability_statuses
from file_toolbox.gui.dialogs.attendance_models import EmployeePreviewModel, GroupPreviewModel
from file_toolbox.gui.generated.ui_attendance_dialog import Ui_AttendanceDialog
from file_toolbox.gui.task_lifecycle import TaskLifecycle

_MAPPING_DETAIL_ROLE = "detail"
_MAPPING_SUMMARY_ROLE = "summary"
_MAPPING_LEGACY_ROLE = "legacy"


class AttendanceTab(QWidget):
    """当前给定格式的可配置考勤汇总原型。"""

    # 表单状态字段 -> 页面输入控件名(绑定 textChanged 同步状态)。
    _EDIT_FIELDS: ClassVar[dict[str, str]] = {
        "source_path": "edit_source",
        "template_path": "edit_template",
        "output_dir": "edit_output_dir",
        "output_name": "edit_output_name",
        "plan_name": "edit_plan_name",
        "source_sheet": "edit_source_sheet",
        "source_name": "edit_source_name",
        "source_department": "edit_source_department",
        "source_group": "edit_source_group",
        "source_detail": "edit_source_detail",
        "detail_sheet": "edit_detail_sheet",
        "detail_name": "edit_detail_name",
        "detail_matrix": "edit_detail_matrix",
        "summary_sheet": "edit_summary_sheet",
        "summary_name": "edit_summary_name",
        "roster_path": "edit_roster",
        "roster_sheet": "edit_roster_sheet",
        "roster_group": "edit_roster_group",
        "roster_department": "edit_roster_department",
        "roster_name": "edit_roster_name",
        "roster_employee_id": "edit_roster_employee_id",
        "detail_serial": "edit_detail_serial",
        "detail_employee_id": "edit_detail_employee_id",
        "summary_serial": "edit_summary_serial",
        "summary_employee_id": "edit_summary_employee_id",
    }

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        service: AttendanceService | None = None,
        plan_store: AttendancePlanStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.ui = Ui_AttendanceDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI code
        self._service = service or AttendanceService(history_store=JsonHistoryStore())
        self._plans = plan_store or AttendancePlanStore()
        # 生命周期句柄:单一事实保存当前任务与延迟关闭,只在真实 finished 释放。
        # _next_status/_preview_can_generate 记录结果槽的终态,真实 finished 后
        # 用于恢复控件(结果信号不恢复启动按钮,仍忙至真实结束)。
        self._task = TaskLifecycle(self)
        self._next_status = "就绪"
        self._preview_can_generate = False
        self._preview_request: AttendanceRequest | None = None
        # 在途任务的冻结请求快照:预览结果绑定启动时的请求,不以结果到达时的
        # 当前表单替代;真实 finished 后释放。
        self._active_request: AttendanceRequest | None = None
        # 表单权威状态(无 Qt):控件编辑即时同步,构建方案/请求时不再反读控件。
        self._state = default_form_state()
        self._loading = False
        self._group_model = GroupPreviewModel(self)
        self._employee_model = EmployeePreviewModel(self)
        self._group_proxy = QSortFilterProxyModel(self)
        self._group_proxy.setSourceModel(self._group_model)
        self._employee_proxy = QSortFilterProxyModel(self)
        self._employee_proxy.setSourceModel(self._employee_model)
        self._setup_tables()
        self._set_defaults()
        self._connect()
        self._refresh_plans()
        self._refresh_excel_status()

    def _refresh_excel_status(self) -> None:
        """Excel 能力提示:消费统一登记声明(预筛结论,不禁用任何控件)。

        考勤读写均经真实 Excel 会话;任务真实结束后刷新一次,让本进程内
        实际 Dispatch 成功的证据(已验证)如实呈现。
        """
        self.ui.label_excel_status.setText(format_statuses(tool_capability_statuses("attendance")))

    # 兼容旧 _worker 字段:读写均转发 TaskLifecycle;只有真实
    # finished(task.finish 精确身份校验)才清空,结果信号不提前释放引用。
    @property
    def _worker(self) -> QThread | None:
        return self._task.worker

    @_worker.setter
    def _worker(self, value: QThread | None) -> None:
        self._task.worker = value

    @property
    def close_pending(self) -> bool:
        """是否正等待 COM worker 安全退出后重试关闭主窗口。"""
        return self._task.close_pending

    def _setup_tables(self) -> None:
        for table in (self.ui.table_mappings, self.ui.table_rules):
            table.horizontalHeader().setStretchLastSection(True)
            table.setAlternatingRowColors(True)
        self.ui.table_rules.setColumnWidth(0, 52)
        self.ui.table_rules.setColumnWidth(1, 260)
        self.ui.table_mappings.setColumnWidth(0, 150)
        self.ui.table_mappings.setColumnWidth(1, 90)
        for view, proxy in (
            (self.ui.table_group_preview, self._group_proxy),
            (self.ui.table_employee_preview, self._employee_proxy),
        ):
            view.horizontalHeader().setStretchLastSection(True)
            view.setAlternatingRowColors(True)
            view.setModel(proxy)
            # 排序/筛选只作用于显示代理;回收调整始终读取源模型数据行,
            # 不会把调整应用到错误的人。
            view.setSortingEnabled(True)
        self._configure_preview_tables(False)

    def _set_defaults(self) -> None:
        self._state = default_form_state()
        self._sync_widgets_from_state()

    def _sync_widgets_from_state(self) -> None:
        """把权威状态推送到全部控件(加载方案/恢复默认时使用)。"""
        self._loading = True
        try:
            for attr, widget_name in self._EDIT_FIELDS.items():
                getattr(self.ui, widget_name).setText(getattr(self._state, attr))
            self.ui.spin_year.setValue(self._state.year)
            self.ui.spin_month.setValue(self._state.month)
            self.ui.chk_split_groups.setChecked(self._state.split_by_group)
            self.ui.chk_fill_serial.setChecked(self._state.fill_serial_numbers)
            self.ui.chk_fill_employee_id.setChecked(self._state.fill_employee_ids)
            self._set_roster_controls(self._state.roster_enabled)
            self.ui.chk_roster_enabled.setChecked(self._state.roster_enabled)
            self._configure_preview_tables(self._state.roster_enabled)
            self._render_mappings()
            self._render_rules()
        finally:
            self._loading = False

    def _set_roster_controls(self, enabled: bool) -> None:
        for widget in (
            self.ui.label_roster_file,
            self.ui.edit_roster,
            self.ui.btn_roster,
            self.ui.group_roster_layout,
            self.ui.group_roster_output,
            self.ui.label_roster_help,
        ):
            widget.setEnabled(enabled)
        self.ui.label_source_group.setEnabled(not enabled)
        self.ui.edit_source_group.setEnabled(not enabled)
        self.ui.chk_split_groups.setEnabled(not enabled)

    def _configure_preview_tables(self, roster_mode: bool) -> None:
        self._group_model.set_mode(roster_mode)
        self._employee_model.set_mode(roster_mode)
        widths: tuple[int, ...] = (58, 130, 110, 110, 130, 100) if roster_mode else (120, 140, 140)
        for column, width in enumerate(widths):
            self.ui.table_employee_preview.setColumnWidth(column, width)
        self.ui.table_group_preview.setColumnWidth(0, 150)
        self.ui.table_group_preview.setColumnWidth(1, 100 if roster_mode else 60)
        self.ui.table_group_preview.setColumnWidth(2, 80 if roster_mode else 220)
        self.ui.table_group_preview.setColumnWidth(3, 220)
        if roster_mode:
            self.ui.table_group_preview.setColumnWidth(4, 220)

    def _connect(self) -> None:
        self.ui.btn_source.clicked.connect(self._browse_source)
        self.ui.btn_roster.clicked.connect(self._browse_roster)
        self.ui.btn_template.clicked.connect(self._browse_template)
        self.ui.btn_output.clicked.connect(self._browse_output)
        self.ui.btn_output_name.clicked.connect(self._generate_output_name)
        self.ui.btn_load_plan.clicked.connect(self._load_plan)
        self.ui.btn_save_plan.clicked.connect(self._save_plan)
        self.ui.btn_delete_plan.clicked.connect(self._delete_plan)
        self.ui.btn_add_mapping.clicked.connect(self._add_mapping)
        self.ui.btn_remove_mapping.clicked.connect(
            lambda: self._remove_selected(self.ui.table_mappings)
        )
        self.ui.btn_add_rule.clicked.connect(self._add_rule)
        self.ui.btn_remove_rule.clicked.connect(lambda: self._remove_selected(self.ui.table_rules))
        self.ui.btn_rule_up.clicked.connect(lambda: self._move_rule(-1))
        self.ui.btn_rule_down.clicked.connect(lambda: self._move_rule(1))
        self.ui.btn_preview.clicked.connect(self._preview)
        self.ui.btn_generate.clicked.connect(self._generate)
        self.ui.btn_apply_adjustments.clicked.connect(self._apply_preview_adjustments)

        for attr, widget_name in self._EDIT_FIELDS.items():
            getattr(self.ui, widget_name).textChanged.connect(
                lambda text, a=attr: self._on_field_changed(a, text)
            )
        self.ui.spin_year.valueChanged.connect(self._on_year_changed)
        self.ui.spin_month.valueChanged.connect(self._on_month_changed)
        self.ui.table_mappings.cellChanged.connect(self._on_mapping_cell_changed)
        self.ui.table_rules.cellChanged.connect(self._on_rule_cell_changed)
        self._group_model.dataChanged.connect(self._preview_adjustments_changed)
        self._employee_model.dataChanged.connect(self._preview_adjustments_changed)
        self.ui.chk_split_groups.toggled.connect(self._on_split_changed)
        self.ui.chk_roster_enabled.toggled.connect(self._roster_mode_changed)
        self.ui.chk_fill_serial.toggled.connect(
            lambda checked: self._on_flag_changed("fill_serial_numbers", checked)
        )
        self.ui.chk_fill_employee_id.toggled.connect(
            lambda checked: self._on_flag_changed("fill_employee_ids", checked)
        )

    # --- 字段 -> 状态同步 ---

    def _on_field_changed(self, attr: str, text: str) -> None:
        setattr(self._state, attr, text)
        if attr in ("detail_sheet", "summary_sheet"):
            self._refresh_mapping_sheet_selectors()
        self._invalidate_preview()

    def _on_flag_changed(self, attr: str, checked: bool) -> None:
        setattr(self._state, attr, checked)
        self._invalidate_preview()

    def _on_year_changed(self, value: int) -> None:
        self._state.year = value
        self._invalidate_preview()

    def _on_month_changed(self, value: int) -> None:
        self._state.month = value
        self._invalidate_preview()

    def _on_split_changed(self, checked: bool) -> None:
        self._state.split_by_group = checked
        self._invalidate_preview()

    def _roster_mode_changed(self, enabled: bool) -> None:
        self._state.roster_enabled = enabled
        if enabled and not self._state.split_by_group:
            self._state.split_by_group = True
            self.ui.chk_split_groups.setChecked(True)
        self._set_roster_controls(enabled)
        self._configure_preview_tables(enabled)
        self._invalidate_preview()

    # --- 文件浏览 ---

    def _browse_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择原始考勤", "", "Excel (*.xlsx)")
        if path:
            self.ui.edit_source.setText(path)

    def _browse_roster(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择人员名单", "", "Excel (*.xlsx)")
        if path:
            self.ui.edit_roster.setText(path)

    def _browse_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择汇总模板", "", "Excel (*.xlsx)")
        if path:
            self.ui.edit_template.setText(path)

    def _browse_output(self) -> None:
        current = self._state.output_dir.strip()
        initial = current if Path(current).is_dir() else ""
        path = QFileDialog.getExistingDirectory(self, "选择考勤汇总保存目录", initial)
        if not path:
            return
        self.ui.edit_output_dir.setText(path)
        if not self._state.output_name.strip():
            self._generate_output_name()

    def _generate_output_name(self) -> None:
        self.ui.edit_output_name.setText(default_output_name(self._state))

    # --- 方案 ---

    def _refresh_plans(self, selected: str = "") -> None:
        self.ui.cmb_plan.clear()
        self.ui.cmb_plan.addItems([plan.name for plan in self._plans.list()])
        if selected:
            self.ui.cmb_plan.setCurrentText(selected)

    def _load_plan(self) -> None:
        plan = self._plans.get(self.ui.cmb_plan.currentText())
        if plan is None:
            QMessageBox.warning(self, "加载方案", "请选择已保存的方案")
            return
        self._apply_plan(plan)
        self.ui.lbl_status.setText(f"已加载方案：{plan.name}")

    def _save_plan(self) -> None:
        try:
            has_adjustments = self._group_model.rowCount() > 0 or (
                self._state.roster_enabled and self._employee_model.rowCount() > 0
            )
            if self._state.split_by_group and has_adjustments:
                self._capture_preview_adjustments()
                self._invalidate_preview()
            plan = build_plan(self._state)
        except ValueError as exc:
            QMessageBox.warning(self, "方案无效", str(exc))
            return
        overwrite = self._plans.get(plan.name) is not None
        if (
            overwrite
            and QMessageBox.question(
                self,
                "覆盖方案",
                f"方案“{plan.name}”已存在，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self._plans.save(plan, overwrite=overwrite)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "保存方案失败", str(exc))
            return
        self._refresh_plans(plan.name)
        self.ui.lbl_status.setText(f"已保存方案：{plan.name}")

    def _delete_plan(self) -> None:
        name = self.ui.cmb_plan.currentText()
        if not name:
            return
        if (
            QMessageBox.question(
                self,
                "删除方案",
                f"确定删除方案“{name}”？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self._plans.delete(name)
        except OSError as exc:
            QMessageBox.critical(self, "删除方案失败", str(exc))
            return
        self._refresh_plans()
        self.ui.lbl_status.setText(f"已删除方案：{name}")

    def _apply_plan(self, plan: AttendancePlan) -> None:
        self._loading = True
        try:
            apply_plan_to_state(self._state, plan)
        finally:
            self._loading = False
        self._sync_widgets_from_state()
        self._clear_preview_tables()
        self._invalidate_preview()

    # --- 状态 <-> 方案/请求构建(委托无 Qt 的 form_state 模块) ---

    def _build_plan(self) -> AttendancePlan:
        return build_plan(self._state)

    def _build_request(self, *, allow_overwrite: bool = False) -> AttendanceRequest:
        return build_request(self._state, allow_overwrite=allow_overwrite)

    # --- 固定单元格映射小表格(编辑后同步回状态) ---

    def _set_mappings(self, mappings: tuple[CellMapping, ...]) -> None:
        self._state.mappings = tuple(
            MappingSelection.for_sheet_name(
                mapping.sheet_name,
                self._state.detail_sheet,
                self._state.summary_sheet,
                cell=mapping.cell.address,
                content=mapping.content_template,
            )
            for mapping in mappings
        )
        self._render_mappings()

    def _render_mappings(self) -> None:
        self._loading = True
        try:
            self.ui.table_mappings.setRowCount(0)
            for selection in self._state.mappings:
                row = self.ui.table_mappings.rowCount()
                self.ui.table_mappings.insertRow(row)
                self._install_mapping_row(row, selection)
        finally:
            self._loading = False

    def _install_mapping_row(self, row: int, selection: MappingSelection) -> None:
        self.ui.table_mappings.setCellWidget(row, 0, self._mapping_sheet_selector(selection))
        self.ui.table_mappings.setItem(row, 1, QTableWidgetItem(selection.cell))
        self.ui.table_mappings.setItem(row, 2, QTableWidgetItem(selection.content))

    def _mapping_sheet_selector(self, selection: MappingSelection | None = None) -> QComboBox:
        selector = QComboBox(self.ui.table_mappings)
        detail_sheet = self._state.detail_sheet.strip()
        summary_sheet = self._state.summary_sheet.strip()
        selector.addItem(detail_sheet or "明细 Sheet", _MAPPING_DETAIL_ROLE)
        selector.addItem(summary_sheet or "汇总 Sheet", _MAPPING_SUMMARY_ROLE)
        if selection is not None:
            if selection.role == "summary":
                selector.setCurrentIndex(1)
            elif selection.role == "legacy" and selection.legacy_sheet.strip():
                selector.addItem(selection.legacy_sheet, _MAPPING_LEGACY_ROLE)
                selector.setCurrentIndex(2)
        selector.currentIndexChanged.connect(self._on_mapping_selector_changed)
        return selector

    def _on_mapping_selector_changed(self, *_args: object) -> None:
        if self._loading:
            return
        selector = self.sender()
        if not isinstance(selector, QComboBox):
            return
        row = self._mapping_selector_row(selector)
        if row < 0 or row >= len(self._state.mappings):
            return
        role = selector.currentData()
        if role not in (_MAPPING_DETAIL_ROLE, _MAPPING_SUMMARY_ROLE, _MAPPING_LEGACY_ROLE):
            return
        legacy = selector.currentText().strip() if role == _MAPPING_LEGACY_ROLE else ""
        mappings = list(self._state.mappings)
        mappings[row] = replace(mappings[row], role=cast(MappingRole, role), legacy_sheet=legacy)
        self._state.mappings = tuple(mappings)
        self._invalidate_preview()

    def _mapping_selector_row(self, selector: QComboBox) -> int:
        for row in range(self.ui.table_mappings.rowCount()):
            if self.ui.table_mappings.cellWidget(row, 0) is selector:
                return row
        return -1

    def _refresh_mapping_sheet_selectors(self, *_args: object) -> None:
        detail_sheet = self._state.detail_sheet.strip() or "明细 Sheet"
        summary_sheet = self._state.summary_sheet.strip() or "汇总 Sheet"
        for row in range(self.ui.table_mappings.rowCount()):
            selector = self.ui.table_mappings.cellWidget(row, 0)
            if not isinstance(selector, QComboBox):
                continue
            detail_index = selector.findData(_MAPPING_DETAIL_ROLE)
            summary_index = selector.findData(_MAPPING_SUMMARY_ROLE)
            if detail_index >= 0:
                selector.setItemText(detail_index, detail_sheet)
            if summary_index >= 0:
                selector.setItemText(summary_index, summary_sheet)

    def _on_mapping_cell_changed(self, row: int, column: int) -> None:
        if self._loading or column not in (1, 2) or row >= len(self._state.mappings):
            return
        text = self._item_text(self.ui.table_mappings, row, column)
        mappings = list(self._state.mappings)
        selection = mappings[row]
        mappings[row] = (
            replace(selection, cell=text) if column == 1 else replace(selection, content=text)
        )
        self._state.mappings = tuple(mappings)
        self._invalidate_preview()

    def _add_mapping(self) -> None:
        selection = MappingSelection()
        self._state.mappings = (*self._state.mappings, selection)
        row = self.ui.table_mappings.rowCount()
        self._loading = True
        try:
            self.ui.table_mappings.insertRow(row)
            self._install_mapping_row(row, selection)
        finally:
            self._loading = False
        self.ui.table_mappings.setCurrentCell(row, 1)
        self._invalidate_preview()

    # --- 判定规则小表格(编辑后同步回状态) ---

    def _set_rules(self, rules: tuple[AttendanceRule, ...]) -> None:
        self._state.rules = rules
        self._render_rules()

    def _render_rules(self) -> None:
        self._loading = True
        try:
            self.ui.table_rules.setRowCount(0)
            for rule in self._state.rules:
                row = self.ui.table_rules.rowCount()
                self.ui.table_rules.insertRow(row)
                self._write_rule_row(row, rule)
        finally:
            self._loading = False

    def _write_rule_row(self, row: int, rule: AttendanceRule) -> None:
        enabled = QTableWidgetItem()
        enabled.setFlags(enabled.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        enabled.setCheckState(Qt.CheckState.Checked if rule.enabled else Qt.CheckState.Unchecked)
        self.ui.table_rules.setItem(row, 0, enabled)
        self.ui.table_rules.setItem(row, 1, QTableWidgetItem(rule.pattern))
        self.ui.table_rules.setItem(row, 2, QTableWidgetItem(rule.output))

    def _add_rule(self) -> None:
        rule = AttendanceRule("", "")
        self._state.rules = (*self._state.rules, rule)
        row = self.ui.table_rules.rowCount()
        self._loading = True
        try:
            self.ui.table_rules.insertRow(row)
            self._write_rule_row(row, rule)
        finally:
            self._loading = False
        self.ui.table_rules.setCurrentCell(row, 1)
        self._invalidate_preview()

    def _on_rule_cell_changed(self, row: int, column: int) -> None:
        if self._loading or row >= len(self._state.rules):
            return
        rules = list(self._state.rules)
        rule = rules[row]
        if column == 0:
            item = self.ui.table_rules.item(row, 0)
            enabled = item is not None and item.checkState() == Qt.CheckState.Checked
            rules[row] = replace(rule, enabled=enabled)
        else:
            text = self._item_text(self.ui.table_rules, row, column)
            rules[row] = replace(rule, pattern=text) if column == 1 else replace(rule, output=text)
        self._state.rules = tuple(rules)
        self._invalidate_preview()

    def _remove_selected(self, table: QTableWidget) -> None:
        rows = sorted({index.row() for index in table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        removed = set(rows)
        if table is self.ui.table_mappings:
            self._state.mappings = tuple(
                selection
                for row, selection in enumerate(self._state.mappings)
                if row not in removed
            )
        else:
            self._state.rules = tuple(
                rule for row, rule in enumerate(self._state.rules) if row not in removed
            )
        self._loading = True
        try:
            for row in rows:
                table.removeRow(row)
        finally:
            self._loading = False
        self._invalidate_preview()

    def _move_rule(self, delta: int) -> None:
        row = self.ui.table_rules.currentRow()
        target = row + delta
        if row < 0 or target < 0 or target >= self.ui.table_rules.rowCount():
            return
        rules = list(self._state.rules)
        rules[row], rules[target] = rules[target], rules[row]
        self._state.rules = tuple(rules)
        self._loading = True
        try:
            self._write_rule_row(row, rules[row])
            self._write_rule_row(target, rules[target])
            self.ui.table_rules.setCurrentCell(target, 1)
        finally:
            self._loading = False
        self._invalidate_preview()

    @staticmethod
    def _item_text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return "" if item is None else item.text().strip()

    # --- 预览调整(以模型数据行为权威) ---

    def _clear_preview_tables(self) -> None:
        self._group_model.clear()
        self._employee_model.clear()
        self.ui.btn_apply_adjustments.setEnabled(False)

    def _capture_preview_adjustments(self) -> None:
        capture_preview_adjustments(
            self._state,
            self._group_model.rows(),
            self._employee_model.roster_rows(),
            self._employee_model.group_rows(),
        )

    def _preview_adjustments_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self._preview_request = None
        self.ui.btn_generate.setEnabled(False)
        self.ui.btn_apply_adjustments.setEnabled(True)
        self.ui.lbl_status.setText("名单或分组调整已修改，请应用并重新预览")

    def _apply_preview_adjustments(self) -> None:
        if not self._state.split_by_group or (
            self._group_model.rowCount() == 0 and self._employee_model.rowCount() == 0
        ):
            return
        try:
            self._capture_preview_adjustments()
        except ValueError as exc:
            QMessageBox.warning(self, "分组调整无效", str(exc))
            return
        self._invalidate_preview()
        self._preview()

    def _invalidate_preview(self, *_args: object) -> None:
        if self._loading:
            return
        self._preview_request = None
        self.ui.btn_generate.setEnabled(False)
        self.ui.lbl_preview.setText("配置已变化，请重新预览")

    def _preview(self) -> None:
        try:
            request = self._build_request()
        except ValueError as exc:
            QMessageBox.warning(self, "配置无效", str(exc))
            return
        self._start_worker(request, "preview")

    def _generate(self) -> None:
        try:
            request = self._build_request()
        except ValueError as exc:
            QMessageBox.warning(self, "配置无效", str(exc))
            return
        if self._preview_request != request:
            self._invalidate_preview()
            QMessageBox.warning(self, "请重新预览", "配置已变化，生成前必须重新预览")
            return
        if request.output_path.exists():
            answer = QMessageBox.question(
                self,
                "覆盖结果",
                f"结果文件已存在，是否替换？\n{request.output_path}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            request = replace(request, allow_overwrite=True)
        self._start_worker(request, "generate")

    def _start_worker(
        self, request: AttendanceRequest, mode: Literal["preview", "generate"]
    ) -> None:
        # 任务未在真实 finished 中释放(或延迟关闭中)时拒绝,不以 isRunning() 为准
        if self._task.busy:
            return
        # 按需导入:worker 真正启动才拉起其依赖链,页面构造/首切不预付(Issue #124)。
        from file_toolbox.gui.workers import AttendanceWorker

        worker = AttendanceWorker(self._service, request, mode, self)
        worker.finished_ok.connect(
            self._on_preview_ok if mode == "preview" else self._on_generate_ok
        )
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self._task.track(worker)
        self._active_request = request
        self._set_busy(True, "正在预览并校验…" if mode == "preview" else "正在生成结果…")
        worker.start()

    def _set_busy(self, busy: bool, status: str) -> None:
        self.ui.group_files.setEnabled(not busy)
        self.ui.group_plan.setEnabled(not busy)
        self.ui.config_tabs.setEnabled(not busy)
        self.ui.btn_preview.setEnabled(not busy)
        self.ui.btn_generate.setEnabled(not busy and self._preview_request is not None)
        self.ui.btn_apply_adjustments.setEnabled(
            not busy
            and self._state.split_by_group
            and (
                self._group_model.rowCount() > 0
                or (self._state.roster_enabled and self._employee_model.rowCount() > 0)
            )
        )
        self.ui.lbl_status.setText(status)

    def _on_preview_ok(self, result: object) -> None:
        """结果槽:渲染预览与状态;控件恢复等真实 finished(仍忙至真实结束)。

        结果绑定启动预览时的冻结请求:worker 信号路径用快照比对当前表单,
        不以后果到达时的表单重建;同步直调(无在途快照,测试路径)以当前表单
        为快照。预览运行期间配置已变化时结果过期,保持失效,不渲染旧结果。
        """
        if not self._task.accepts(self.sender()):
            return
        if not isinstance(result, AttendancePreview):
            self._on_failed("预览返回了无效结果")
            return
        request = self._active_request
        if request is None:
            try:
                request = self._build_request()
            except ValueError as exc:
                self._on_failed(str(exc))
                return
        try:
            current = self._build_request()
        except ValueError:
            current = None
        if current != request:
            self._preview_request = None
            self._preview_can_generate = False
            self._next_status = "配置已变化，请重新预览"
            self.ui.lbl_status.setText(self._next_status)
            self.ui.lbl_preview.setText("配置已变化，请重新预览")
            return
        self._preview_request = request
        self._show_preview(result, request.plan)
        if result.can_generate:
            status = "预览通过"
        elif result.errors:
            status = "存在名单或配置错误"
        else:
            status = "存在未匹配记录"
        # 状态文案即时反馈;_set_busy(False)/启动按钮恢复延后到真实 finished
        self._next_status = status
        self._preview_can_generate = result.can_generate
        self.ui.lbl_status.setText(status)
        self.ui.config_tabs.setCurrentWidget(self.ui.tab_preview)

    def _show_preview(self, result: AttendancePreview, plan: AttendancePlan) -> None:
        roster_mode = result.roster_path is not None
        rows = build_preview_rows(result, plan.group_sheet_configs)
        self._configure_preview_tables(roster_mode)
        self._group_model.set_rows(rows.groups, roster_mode=roster_mode)
        self._employee_model.set_rows(rows)
        self.ui.lbl_preview.setText(self._preview_summary_text(result))
        self.ui.btn_apply_adjustments.setEnabled(
            bool(result.group_counts) or (roster_mode and bool(result.employees))
        )

    @staticmethod
    def _preview_summary_text(result: AttendancePreview) -> str:
        direction = "增加" if result.date_column_delta >= 0 else "删除"
        counts = "，".join(f"{key} {value}" for key, value in result.status_counts.items()) or "无"
        group_text = ""
        if result.group_counts:
            groups = "，".join(
                f"{name} {count} 人→{result.target_sheets[name][0]}/{result.target_sheets[name][1]}"
                for name, count in result.group_counts.items()
            )
            group_text = f"输出分组：{groups}；"
        error_text = ""
        if result.errors:
            visible_errors = "；".join(result.errors[:3])
            if len(result.errors) > 3:
                visible_errors += f"；另 {len(result.errors) - 3} 项"
            error_text = f"错误：{visible_errors}；"
        warning_text = ""
        if result.warnings:
            visible_warnings = "；".join(result.warnings[:3])
            if len(result.warnings) > 3:
                visible_warnings += f"；另 {len(result.warnings) - 3} 项"
            warning_text = f"警告：{visible_warnings}；"
        return (
            f"导出员工 {result.employee_count} 人；排除 {result.excluded_count} 人；"
            f"本月 {result.day_count} 天；"
            f"{direction}日期列 {abs(result.date_column_delta)}；"
            f"新增员工行 {result.extra_employee_rows}；判定：{counts}；"
            f"{group_text}{error_text}{warning_text}未匹配 {len(result.unmatched)} 条。"
        )

    def _on_generate_ok(self, result: object) -> None:
        """结果槽:展示生成结果;控件恢复等真实 finished(仍忙至真实结束)。"""
        if not self._task.accepts(self.sender()):
            return
        if not isinstance(result, AttendanceResult):
            self._on_failed("生成返回了无效结果")
            return
        self._preview_request = None
        self._preview_can_generate = False
        self._next_status = "生成完成"
        self.ui.lbl_status.setText("生成完成")
        warning_text = ""
        if result.warnings:
            warning_text = "\n\n注意：" + "；".join(result.warnings)
        if not self._task.close_pending:
            QMessageBox.information(
                self,
                "生成完成",
                f"已另存结果：\n{result.output_path}\n\n员工 {result.employee_count} 人，"
                f"{result.day_count} 天。{warning_text}",
            )

    def _on_failed(self, message: str) -> None:
        """结果槽/内部失败路径:反馈状态;控件恢复等真实 finished。"""
        if not self._task.accepts(self.sender()):
            return
        self._preview_request = None
        self._preview_can_generate = False
        self._next_status = "操作失败"
        self.ui.lbl_status.setText("操作失败")
        self.ui.btn_generate.setEnabled(False)
        self.ui.btn_apply_adjustments.setEnabled(
            self._state.split_by_group
            and (self._group_model.rowCount() > 0 or self._employee_model.rowCount() > 0)
        )
        if not self._task.close_pending:
            QMessageBox.critical(self, "考勤处理失败", message)

    def _on_worker_finished(self) -> None:
        """真实 finished 后释放线程并恢复控件;延迟关闭由 TaskLifecycle 续接。"""
        if not self._task.finish(self.sender()):
            return
        self._active_request = None
        self._set_busy(False, self._next_status)
        if self._preview_request is not None:
            self.ui.btn_generate.setEnabled(self._preview_can_generate)
        self._refresh_excel_status()

    def closeEvent(self, event: QCloseEvent) -> None:
        """任务未结束时延迟关闭:协作取消后等真实 finished 异步重关。

        旧实现在超时分支才延迟,且先同步 cancel + quit + wait(5000)——等待冻结
        关闭,wait 超时后清引用仍可能撞上运行中的 COM 线程。引用释放/重新关闭
        现在全部由 TaskLifecycle 在真实 finished 消费时完成。
        """
        if self._task.defer_close(event):
            self.ui.lbl_status.setText("正在等待 Excel 安全退出，完成后将自动关闭…")
            return
        super().closeEvent(event)
