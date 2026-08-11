"""考勤汇总 Tab：配置方案、强制预览并安全另存结果。"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Literal

from PySide6.QtCore import Qt, QTimer
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
    CellRef,
    EmployeeGroupOverride,
    GroupSheetConfig,
    SourceLayout,
    TargetLayout,
    default_rules,
)
from file_toolbox.gui.generated.ui_attendance_dialog import Ui_AttendanceDialog
from file_toolbox.gui.workers import AttendanceWorker

_WORKER_CLOSE_WAIT_MS = 5000
_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAPPING_DETAIL_ROLE = "detail"
_MAPPING_SUMMARY_ROLE = "summary"
_MAPPING_LEGACY_ROLE = "legacy"


class AttendanceTab(QWidget):
    """当前给定格式的可配置考勤汇总原型。"""

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
        self._worker: AttendanceWorker | None = None
        self._close_pending = False
        self._preview_request: AttendanceRequest | None = None
        self._employee_group_overrides: tuple[EmployeeGroupOverride, ...] = ()
        self._group_sheet_configs: tuple[GroupSheetConfig, ...] = ()
        self._loading = False
        self._setup_tables()
        self._set_defaults()
        self._connect()
        self._refresh_plans()

    def _setup_tables(self) -> None:
        for table in (
            self.ui.table_mappings,
            self.ui.table_rules,
            self.ui.table_group_preview,
            self.ui.table_employee_preview,
        ):
            table.horizontalHeader().setStretchLastSection(True)
            table.setAlternatingRowColors(True)
        self.ui.table_rules.setColumnWidth(0, 52)
        self.ui.table_rules.setColumnWidth(1, 260)
        self.ui.table_mappings.setColumnWidth(0, 150)
        self.ui.table_mappings.setColumnWidth(1, 90)
        self.ui.table_group_preview.setColumnWidth(0, 150)
        self.ui.table_group_preview.setColumnWidth(1, 60)
        self.ui.table_group_preview.setColumnWidth(2, 220)
        self.ui.table_employee_preview.setColumnWidth(0, 120)
        self.ui.table_employee_preview.setColumnWidth(1, 140)
        self.ui.table_employee_preview.setColumnWidth(2, 140)

    @property
    def close_pending(self) -> bool:
        """是否正等待 COM worker 安全退出后重试关闭主窗口。"""
        return self._close_pending

    def _set_defaults(self) -> None:
        today = date.today()
        self.ui.spin_year.setValue(today.year)
        self.ui.spin_month.setValue(today.month)
        self.ui.edit_plan_name.setText("给定格式")
        self.ui.edit_source_sheet.setText("Sheet1")
        self.ui.edit_source_name.setText("A2")
        self.ui.edit_source_department.setText("C2")
        self.ui.edit_source_group.setText("B2")
        self.ui.edit_source_detail.setText("G2")
        self.ui.edit_detail_sheet.setText("出勤明细")
        self.ui.edit_detail_name.setText("C7")
        self.ui.edit_detail_matrix.setText("D7")
        self.ui.edit_summary_sheet.setText("考勤汇总表")
        self.ui.edit_summary_name.setText("C8")
        self.ui.chk_split_groups.setChecked(True)
        self._set_rules(default_rules())

    def _connect(self) -> None:
        self.ui.btn_source.clicked.connect(self._browse_source)
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

        for edit in (
            self.ui.edit_source,
            self.ui.edit_template,
            self.ui.edit_output_dir,
            self.ui.edit_output_name,
            self.ui.edit_plan_name,
            self.ui.edit_source_sheet,
            self.ui.edit_source_name,
            self.ui.edit_source_department,
            self.ui.edit_source_group,
            self.ui.edit_source_detail,
            self.ui.edit_detail_sheet,
            self.ui.edit_detail_name,
            self.ui.edit_detail_matrix,
            self.ui.edit_summary_sheet,
            self.ui.edit_summary_name,
        ):
            edit.textChanged.connect(self._invalidate_preview)
        self.ui.spin_year.valueChanged.connect(self._invalidate_preview)
        self.ui.spin_month.valueChanged.connect(self._invalidate_preview)
        self.ui.table_mappings.cellChanged.connect(self._invalidate_preview)
        self.ui.table_rules.cellChanged.connect(self._invalidate_preview)
        self.ui.table_group_preview.cellChanged.connect(self._preview_adjustments_changed)
        self.ui.table_employee_preview.cellChanged.connect(self._preview_adjustments_changed)
        self.ui.chk_split_groups.toggled.connect(self._invalidate_preview)
        self.ui.edit_detail_sheet.textChanged.connect(self._refresh_mapping_sheet_selectors)
        self.ui.edit_summary_sheet.textChanged.connect(self._refresh_mapping_sheet_selectors)

    def _browse_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择原始考勤", "", "Excel (*.xlsx)")
        if path:
            self.ui.edit_source.setText(path)

    def _browse_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择汇总模板", "", "Excel (*.xlsx)")
        if path:
            self.ui.edit_template.setText(path)

    def _browse_output(self) -> None:
        current = self.ui.edit_output_dir.text().strip()
        initial = current if Path(current).is_dir() else ""
        path = QFileDialog.getExistingDirectory(self, "选择考勤汇总保存目录", initial)
        if not path:
            return
        self.ui.edit_output_dir.setText(path)
        if not self.ui.edit_output_name.text().strip():
            self._generate_output_name()

    def _generate_output_name(self) -> None:
        plan_name = _INVALID_FILENAME_CHARS_RE.sub(
            "_", self.ui.edit_plan_name.text().strip()
        ).strip(" .")
        prefix = plan_name or "考勤汇总"
        self.ui.edit_output_name.setText(
            f"{prefix}-{self.ui.spin_year.value()}年{self.ui.spin_month.value():02d}月考勤汇总.xlsx"
        )

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
            if self.ui.chk_split_groups.isChecked() and self.ui.table_group_preview.rowCount() > 0:
                self._capture_preview_adjustments()
                self._invalidate_preview()
            plan = self._build_plan()
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
            self.ui.edit_plan_name.setText(plan.name)
            self.ui.edit_template.setText(str(plan.template_path))
            self.ui.edit_source_sheet.setText(plan.source.sheet_name)
            self.ui.edit_source_name.setText(plan.source.name_start.address)
            self.ui.edit_source_department.setText(plan.source.department_start.address)
            self.ui.edit_source_group.setText(
                plan.source.attendance_group_start.address
                if plan.source.attendance_group_start is not None
                else "B2"
            )
            self.ui.edit_source_detail.setText(plan.source.detail_start.address)
            self.ui.edit_detail_sheet.setText(plan.target.detail_sheet)
            self.ui.edit_detail_name.setText(plan.target.detail_name_start.address)
            self.ui.edit_detail_matrix.setText(plan.target.detail_matrix_start.address)
            self.ui.edit_summary_sheet.setText(plan.target.summary_sheet)
            self.ui.edit_summary_name.setText(plan.target.summary_name_start.address)
            self.ui.chk_split_groups.setChecked(plan.split_by_group)
            self._employee_group_overrides = plan.employee_group_overrides
            self._group_sheet_configs = plan.group_sheet_configs
            self._set_mappings(plan.mappings)
            self._set_rules(plan.rules)
            self._clear_preview_tables()
        finally:
            self._loading = False
        self._invalidate_preview()

    def _build_plan(self) -> AttendancePlan:
        name = self.ui.edit_plan_name.text().strip()
        template = self.ui.edit_template.text().strip()
        if not name:
            raise ValueError("方案名称不能为空")
        if not template:
            raise ValueError("请选择汇总模板")
        return AttendancePlan(
            name=name,
            template_path=Path(template),
            source=SourceLayout(
                self._required_text(self.ui.edit_source_sheet.text(), "原始 Sheet 名"),
                CellRef.parse(self.ui.edit_source_name.text()),
                CellRef.parse(self.ui.edit_source_department.text()),
                CellRef.parse(self.ui.edit_source_detail.text()),
                CellRef.parse(self.ui.edit_source_group.text()),
            ),
            target=TargetLayout(
                self._required_text(self.ui.edit_detail_sheet.text(), "明细 Sheet 名"),
                CellRef.parse(self.ui.edit_detail_name.text()),
                CellRef.parse(self.ui.edit_detail_matrix.text()),
                self._required_text(self.ui.edit_summary_sheet.text(), "汇总 Sheet 名"),
                CellRef.parse(self.ui.edit_summary_name.text()),
            ),
            mappings=self._mappings(),
            rules=self._rules(),
            split_by_group=self.ui.chk_split_groups.isChecked(),
            employee_group_overrides=self._employee_group_overrides,
            group_sheet_configs=self._group_sheet_configs,
        )

    def _build_request(self, *, allow_overwrite: bool = False) -> AttendanceRequest:
        source = self.ui.edit_source.text().strip()
        output_dir = self.ui.edit_output_dir.text().strip()
        output_name = self.ui.edit_output_name.text().strip()
        if not source:
            raise ValueError("请选择原始考勤")
        if not output_dir:
            raise ValueError("请选择结果保存目录")
        if not output_name:
            raise ValueError("请指定结果文件名")
        if Path(output_name).name != output_name or _INVALID_FILENAME_CHARS_RE.search(output_name):
            raise ValueError("结果文件名不能包含路径或 Windows 非法字符")
        normalized_name = Path(output_name).with_suffix(".xlsx").name
        return AttendanceRequest(
            plan=self._build_plan(),
            source_path=Path(source),
            output_path=Path(output_dir) / normalized_name,
            year=self.ui.spin_year.value(),
            month=self.ui.spin_month.value(),
            allow_overwrite=allow_overwrite,
        )

    @staticmethod
    def _required_text(value: str, label: str) -> str:
        if not value.strip():
            raise ValueError(f"{label}不能为空")
        return value.strip()

    def _mappings(self) -> tuple[CellMapping, ...]:
        result: list[CellMapping] = []
        for row in range(self.ui.table_mappings.rowCount()):
            sheet = self._mapping_sheet_name(row)
            cell = self._item_text(self.ui.table_mappings, row, 1)
            content = self._item_text(self.ui.table_mappings, row, 2)
            if not cell and not content:
                continue
            result.append(
                CellMapping(
                    self._required_text(sheet, f"第 {row + 1} 条映射的 Sheet 名"),
                    CellRef.parse(cell),
                    content,
                )
            )
        return tuple(result)

    def _rules(self) -> tuple[AttendanceRule, ...]:
        result: list[AttendanceRule] = []
        for row in range(self.ui.table_rules.rowCount()):
            enabled_item = self.ui.table_rules.item(row, 0)
            pattern = self._item_text(self.ui.table_rules, row, 1)
            output = self._item_text(self.ui.table_rules, row, 2)
            enabled = (
                enabled_item is not None and enabled_item.checkState() == Qt.CheckState.Checked
            )
            if not pattern:
                raise ValueError(f"第 {row + 1} 条规则的正则不能为空")
            result.append(AttendanceRule(pattern, output, enabled))
        if not result:
            raise ValueError("至少需要一条判定规则")
        return tuple(result)

    @staticmethod
    def _item_text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return "" if item is None else item.text().strip()

    def _set_mappings(self, mappings: tuple[CellMapping, ...]) -> None:
        self.ui.table_mappings.setRowCount(0)
        for mapping in mappings:
            row = self.ui.table_mappings.rowCount()
            self.ui.table_mappings.insertRow(row)
            self.ui.table_mappings.setCellWidget(
                row, 0, self._mapping_sheet_selector(mapping.sheet_name)
            )
            self.ui.table_mappings.setItem(row, 1, QTableWidgetItem(mapping.cell.address))
            self.ui.table_mappings.setItem(row, 2, QTableWidgetItem(mapping.content_template))

    def _mapping_sheet_selector(self, selected: str = "") -> QComboBox:
        selector = QComboBox(self.ui.table_mappings)
        detail_sheet = self.ui.edit_detail_sheet.text().strip()
        summary_sheet = self.ui.edit_summary_sheet.text().strip()
        selector.addItem(detail_sheet or "明细 Sheet", _MAPPING_DETAIL_ROLE)
        selector.addItem(summary_sheet or "汇总 Sheet", _MAPPING_SUMMARY_ROLE)

        selected_key = selected.strip().casefold()
        if selected_key == summary_sheet.casefold():
            selector.setCurrentIndex(1)
        elif selected_key and selected_key != detail_sheet.casefold():
            selector.addItem(selected.strip(), _MAPPING_LEGACY_ROLE)
            selector.setCurrentIndex(2)
        selector.currentIndexChanged.connect(self._invalidate_preview)
        return selector

    def _mapping_sheet_name(self, row: int) -> str:
        selector = self.ui.table_mappings.cellWidget(row, 0)
        if not isinstance(selector, QComboBox):
            return self._item_text(self.ui.table_mappings, row, 0)
        role = selector.currentData()
        if role == _MAPPING_DETAIL_ROLE:
            return self.ui.edit_detail_sheet.text().strip()
        if role == _MAPPING_SUMMARY_ROLE:
            return self.ui.edit_summary_sheet.text().strip()
        return selector.currentText().strip()

    def _refresh_mapping_sheet_selectors(self, *_args: object) -> None:
        detail_sheet = self.ui.edit_detail_sheet.text().strip() or "明细 Sheet"
        summary_sheet = self.ui.edit_summary_sheet.text().strip() or "汇总 Sheet"
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

    def _set_rules(self, rules: tuple[AttendanceRule, ...]) -> None:
        self.ui.table_rules.setRowCount(0)
        for rule in rules:
            self._insert_rule(rule)

    def _insert_rule(self, rule: AttendanceRule) -> None:
        row = self.ui.table_rules.rowCount()
        self.ui.table_rules.insertRow(row)
        enabled = QTableWidgetItem()
        enabled.setFlags(enabled.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        enabled.setCheckState(Qt.CheckState.Checked if rule.enabled else Qt.CheckState.Unchecked)
        self.ui.table_rules.setItem(row, 0, enabled)
        self.ui.table_rules.setItem(row, 1, QTableWidgetItem(rule.pattern))
        self.ui.table_rules.setItem(row, 2, QTableWidgetItem(rule.output))

    def _add_mapping(self) -> None:
        row = self.ui.table_mappings.rowCount()
        self.ui.table_mappings.insertRow(row)
        self.ui.table_mappings.setCellWidget(row, 0, self._mapping_sheet_selector())
        self.ui.table_mappings.setItem(row, 1, QTableWidgetItem())
        self.ui.table_mappings.setItem(row, 2, QTableWidgetItem())
        self.ui.table_mappings.setCurrentCell(row, 1)
        self._invalidate_preview()

    def _add_rule(self) -> None:
        self._insert_rule(AttendanceRule("", ""))
        self.ui.table_rules.setCurrentCell(self.ui.table_rules.rowCount() - 1, 1)
        self._invalidate_preview()

    def _remove_selected(self, table: QTableWidget) -> None:
        rows = sorted({index.row() for index in table.selectedIndexes()}, reverse=True)
        for row in rows:
            table.removeRow(row)
        if rows:
            self._invalidate_preview()

    def _move_rule(self, delta: int) -> None:
        row = self.ui.table_rules.currentRow()
        target = row + delta
        if row < 0 or target < 0 or target >= self.ui.table_rules.rowCount():
            return
        self._loading = True
        try:
            first = [self.ui.table_rules.takeItem(row, column) for column in range(3)]
            second = [self.ui.table_rules.takeItem(target, column) for column in range(3)]
            for column in range(3):
                self.ui.table_rules.setItem(row, column, second[column] or QTableWidgetItem())
                self.ui.table_rules.setItem(target, column, first[column] or QTableWidgetItem())
            self.ui.table_rules.setCurrentCell(target, 1)
        finally:
            self._loading = False
        self._invalidate_preview()

    @staticmethod
    def _readonly_item(value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _clear_preview_tables(self) -> None:
        self.ui.table_group_preview.setRowCount(0)
        self.ui.table_employee_preview.setRowCount(0)
        self.ui.btn_apply_adjustments.setEnabled(False)

    def _capture_preview_adjustments(self) -> None:
        configs: list[GroupSheetConfig] = []
        for row in range(self.ui.table_group_preview.rowCount()):
            group_name = self._required_text(
                self._item_text(self.ui.table_group_preview, row, 0),
                f"第 {row + 1} 个输出考勤组",
            )
            detail_sheet = self._required_text(
                self._item_text(self.ui.table_group_preview, row, 2),
                f"考勤组“{group_name}”的明细 Sheet 名",
            )
            summary_sheet = self._required_text(
                self._item_text(self.ui.table_group_preview, row, 3),
                f"考勤组“{group_name}”的汇总 Sheet 名",
            )
            configs.append(GroupSheetConfig(group_name, detail_sheet, summary_sheet))

        overrides: dict[tuple[str, str], EmployeeGroupOverride] = {}
        for row in range(self.ui.table_employee_preview.rowCount()):
            employee_name = self._required_text(
                self._item_text(self.ui.table_employee_preview, row, 0),
                f"第 {row + 1} 名员工姓名",
            )
            source_group = self._required_text(
                self._item_text(self.ui.table_employee_preview, row, 1),
                f"员工“{employee_name}”的原考勤组",
            )
            target_group = self._required_text(
                self._item_text(self.ui.table_employee_preview, row, 2),
                f"员工“{employee_name}”的输出考勤组",
            )
            if source_group.casefold() == target_group.casefold():
                continue
            key = (source_group.casefold(), employee_name.casefold())
            override = EmployeeGroupOverride(employee_name, source_group, target_group)
            existing = overrides.get(key)
            if existing is not None and existing.target_group.casefold() != target_group.casefold():
                raise ValueError(f"同组同名员工“{source_group}/{employee_name}”存在不同调整")
            overrides[key] = override

        self._group_sheet_configs = tuple(configs)
        self._employee_group_overrides = tuple(overrides.values())

    def _preview_adjustments_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self._preview_request = None
        self.ui.btn_generate.setEnabled(False)
        self.ui.btn_apply_adjustments.setEnabled(True)
        self.ui.lbl_status.setText("分组调整已修改，请应用并重新预览")

    def _apply_preview_adjustments(self) -> None:
        if not self.ui.chk_split_groups.isChecked() or self.ui.table_group_preview.rowCount() == 0:
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
        if self._worker is not None:
            return
        worker = AttendanceWorker(self._service, request, mode, self)
        worker.finished_ok.connect(
            self._on_preview_ok if mode == "preview" else self._on_generate_ok
        )
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
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
            and self.ui.chk_split_groups.isChecked()
            and self.ui.table_group_preview.rowCount() > 0
        )
        self.ui.lbl_status.setText(status)

    def _on_preview_ok(self, result: object) -> None:
        if not isinstance(result, AttendancePreview):
            self._on_failed("预览返回了无效结果")
            return
        try:
            self._preview_request = self._build_request()
        except ValueError as exc:
            self._on_failed(str(exc))
            return
        self._show_preview(result)
        self._set_busy(False, "预览通过" if result.can_generate else "存在未匹配记录")
        self.ui.btn_generate.setEnabled(result.can_generate)
        self.ui.config_tabs.setCurrentWidget(self.ui.tab_preview)

    def _show_preview(self, result: AttendancePreview) -> None:
        direction = "增加" if result.date_column_delta >= 0 else "删除"
        counts = "，".join(f"{key} {value}" for key, value in result.status_counts.items()) or "无"
        group_text = ""
        if result.group_counts:
            groups = "，".join(
                f"{name} {count} 人→{result.target_sheets[name][0]}/{result.target_sheets[name][1]}"
                for name, count in result.group_counts.items()
            )
            group_text = f"考勤组：{groups}；"
        self.ui.lbl_preview.setText(
            f"员工 {result.employee_count} 人；本月 {result.day_count} 天；"
            f"{direction}日期列 {abs(result.date_column_delta)}；"
            f"新增员工行 {result.extra_employee_rows}；判定：{counts}；"
            f"{group_text}未匹配 {len(result.unmatched)} 条。"
        )
        unmatched_by_employee: dict[tuple[str, str], list[str]] = {}
        for item in result.unmatched:
            source_group = item.source_group or item.attendance_group
            key = (item.employee.strip().casefold(), source_group.strip().casefold())
            unmatched_by_employee.setdefault(key, []).append(f"{item.day}日: {item.raw}")

        self._loading = True
        try:
            self.ui.table_group_preview.setRowCount(len(result.group_counts))
            for row, (group_name, count) in enumerate(result.group_counts.items()):
                detail_sheet, summary_sheet = result.target_sheets[group_name]
                self.ui.table_group_preview.setItem(row, 0, self._readonly_item(group_name))
                self.ui.table_group_preview.setItem(row, 1, self._readonly_item(str(count)))
                self.ui.table_group_preview.setItem(row, 2, QTableWidgetItem(detail_sheet))
                self.ui.table_group_preview.setItem(row, 3, QTableWidgetItem(summary_sheet))

            self.ui.table_employee_preview.setRowCount(len(result.employees))
            for row, employee in enumerate(result.employees):
                key = (
                    employee.employee_name.strip().casefold(),
                    employee.source_group.strip().casefold(),
                )
                unmatched_items = unmatched_by_employee.get(key, [])
                unmatched_text = "；".join(unmatched_items[:3])
                if len(unmatched_items) > 3:
                    unmatched_text += f"；另 {len(unmatched_items) - 3} 条"
                self.ui.table_employee_preview.setItem(
                    row, 0, self._readonly_item(employee.employee_name)
                )
                self.ui.table_employee_preview.setItem(
                    row, 1, self._readonly_item(employee.source_group)
                )
                target_item = (
                    QTableWidgetItem(employee.target_group)
                    if result.group_counts
                    else self._readonly_item(employee.target_group)
                )
                self.ui.table_employee_preview.setItem(row, 2, target_item)
                self.ui.table_employee_preview.setItem(row, 3, self._readonly_item(unmatched_text))
        finally:
            self._loading = False
        self.ui.btn_apply_adjustments.setEnabled(bool(result.group_counts))

    def _on_generate_ok(self, result: object) -> None:
        if not isinstance(result, AttendanceResult):
            self._on_failed("生成返回了无效结果")
            return
        self._preview_request = None
        self._set_busy(False, "生成完成")
        self.ui.btn_generate.setEnabled(False)
        warning_text = ""
        if result.warnings:
            warning_text = "\n\n注意：" + "；".join(result.warnings)
        QMessageBox.information(
            self,
            "生成完成",
            f"已另存结果：\n{result.output_path}\n\n员工 {result.employee_count} 人，"
            f"{result.day_count} 天。{warning_text}",
        )

    def _on_failed(self, message: str) -> None:
        self._preview_request = None
        self._set_busy(False, "操作失败")
        self.ui.btn_generate.setEnabled(False)
        self.ui.btn_apply_adjustments.setEnabled(
            self.ui.chk_split_groups.isChecked() and self.ui.table_employee_preview.rowCount() > 0
        )
        QMessageBox.critical(self, "考勤处理失败", message)

    def _on_worker_finished(self) -> None:
        """bound slot 固定在 GUI 线程处理 worker 最终释放与延迟关闭。"""
        worker = self._worker
        if worker is None:
            return
        self._worker = None
        worker.deleteLater()
        if self._close_pending:
            self._close_pending = False
            QTimer.singleShot(0, self.window().close)

    def closeEvent(self, event: QCloseEvent) -> None:
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.quit()
            if not worker.wait(_WORKER_CLOSE_WAIT_MS):
                self._close_pending = True
                self.ui.lbl_status.setText("正在等待 Excel 安全退出，完成后将自动关闭…")
                event.ignore()
                return
        super().closeEvent(event)
