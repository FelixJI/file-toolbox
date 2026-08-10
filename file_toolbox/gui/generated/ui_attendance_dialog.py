# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'attendance_dialog.ui'
##
## Created by: Qt User Interface Compiler version 6.11.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSpacerItem, QSpinBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)

class Ui_AttendanceDialog(object):
    def setupUi(self, AttendanceDialog):
        if not AttendanceDialog.objectName():
            AttendanceDialog.setObjectName(u"AttendanceDialog")
        self.verticalLayout = QVBoxLayout(AttendanceDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(10, 8, 10, 8)
        self.group_files = QGroupBox(AttendanceDialog)
        self.group_files.setObjectName(u"group_files")
        self.grid_files = QGridLayout(self.group_files)
        self.grid_files.setObjectName(u"grid_files")
        self.label_source = QLabel(self.group_files)
        self.label_source.setObjectName(u"label_source")

        self.grid_files.addWidget(self.label_source, 0, 0, 1, 1)

        self.edit_source = QLineEdit(self.group_files)
        self.edit_source.setObjectName(u"edit_source")

        self.grid_files.addWidget(self.edit_source, 0, 1, 1, 1)

        self.btn_source = QPushButton(self.group_files)
        self.btn_source.setObjectName(u"btn_source")

        self.grid_files.addWidget(self.btn_source, 0, 2, 1, 1)

        self.label_year = QLabel(self.group_files)
        self.label_year.setObjectName(u"label_year")

        self.grid_files.addWidget(self.label_year, 0, 3, 1, 1)

        self.spin_year = QSpinBox(self.group_files)
        self.spin_year.setObjectName(u"spin_year")
        self.spin_year.setMinimum(2000)
        self.spin_year.setMaximum(2100)

        self.grid_files.addWidget(self.spin_year, 0, 4, 1, 1)

        self.label_month = QLabel(self.group_files)
        self.label_month.setObjectName(u"label_month")

        self.grid_files.addWidget(self.label_month, 0, 5, 1, 1)

        self.spin_month = QSpinBox(self.group_files)
        self.spin_month.setObjectName(u"spin_month")
        self.spin_month.setMinimum(1)
        self.spin_month.setMaximum(12)

        self.grid_files.addWidget(self.spin_month, 0, 6, 1, 1)

        self.label_template = QLabel(self.group_files)
        self.label_template.setObjectName(u"label_template")

        self.grid_files.addWidget(self.label_template, 1, 0, 1, 1)

        self.edit_template = QLineEdit(self.group_files)
        self.edit_template.setObjectName(u"edit_template")

        self.grid_files.addWidget(self.edit_template, 1, 1, 1, 5)

        self.btn_template = QPushButton(self.group_files)
        self.btn_template.setObjectName(u"btn_template")

        self.grid_files.addWidget(self.btn_template, 1, 6, 1, 1)

        self.label_output = QLabel(self.group_files)
        self.label_output.setObjectName(u"label_output")

        self.grid_files.addWidget(self.label_output, 2, 0, 1, 1)

        self.edit_output = QLineEdit(self.group_files)
        self.edit_output.setObjectName(u"edit_output")

        self.grid_files.addWidget(self.edit_output, 2, 1, 1, 5)

        self.btn_output = QPushButton(self.group_files)
        self.btn_output.setObjectName(u"btn_output")

        self.grid_files.addWidget(self.btn_output, 2, 6, 1, 1)


        self.verticalLayout.addWidget(self.group_files)

        self.group_plan = QGroupBox(AttendanceDialog)
        self.group_plan.setObjectName(u"group_plan")
        self.layout_plan = QHBoxLayout(self.group_plan)
        self.layout_plan.setObjectName(u"layout_plan")
        self.cmb_plan = QComboBox(self.group_plan)
        self.cmb_plan.setObjectName(u"cmb_plan")
        self.cmb_plan.setMinimumSize(QSize(180, 0))

        self.layout_plan.addWidget(self.cmb_plan)

        self.edit_plan_name = QLineEdit(self.group_plan)
        self.edit_plan_name.setObjectName(u"edit_plan_name")

        self.layout_plan.addWidget(self.edit_plan_name)

        self.btn_load_plan = QPushButton(self.group_plan)
        self.btn_load_plan.setObjectName(u"btn_load_plan")

        self.layout_plan.addWidget(self.btn_load_plan)

        self.btn_save_plan = QPushButton(self.group_plan)
        self.btn_save_plan.setObjectName(u"btn_save_plan")

        self.layout_plan.addWidget(self.btn_save_plan)

        self.btn_delete_plan = QPushButton(self.group_plan)
        self.btn_delete_plan.setObjectName(u"btn_delete_plan")

        self.layout_plan.addWidget(self.btn_delete_plan)


        self.verticalLayout.addWidget(self.group_plan)

        self.config_tabs = QTabWidget(AttendanceDialog)
        self.config_tabs.setObjectName(u"config_tabs")
        self.tab_layout = QWidget()
        self.tab_layout.setObjectName(u"tab_layout")
        self.layout_coordinates = QHBoxLayout(self.tab_layout)
        self.layout_coordinates.setObjectName(u"layout_coordinates")
        self.group_source_layout = QGroupBox(self.tab_layout)
        self.group_source_layout.setObjectName(u"group_source_layout")
        self.form_source = QFormLayout(self.group_source_layout)
        self.form_source.setObjectName(u"form_source")
        self.label_source_sheet = QLabel(self.group_source_layout)
        self.label_source_sheet.setObjectName(u"label_source_sheet")

        self.form_source.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_source_sheet)

        self.edit_source_sheet = QLineEdit(self.group_source_layout)
        self.edit_source_sheet.setObjectName(u"edit_source_sheet")

        self.form_source.setWidget(0, QFormLayout.ItemRole.FieldRole, self.edit_source_sheet)

        self.label_source_name = QLabel(self.group_source_layout)
        self.label_source_name.setObjectName(u"label_source_name")

        self.form_source.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_source_name)

        self.edit_source_name = QLineEdit(self.group_source_layout)
        self.edit_source_name.setObjectName(u"edit_source_name")

        self.form_source.setWidget(1, QFormLayout.ItemRole.FieldRole, self.edit_source_name)

        self.label_source_department = QLabel(self.group_source_layout)
        self.label_source_department.setObjectName(u"label_source_department")

        self.form_source.setWidget(2, QFormLayout.ItemRole.LabelRole, self.label_source_department)

        self.edit_source_department = QLineEdit(self.group_source_layout)
        self.edit_source_department.setObjectName(u"edit_source_department")

        self.form_source.setWidget(2, QFormLayout.ItemRole.FieldRole, self.edit_source_department)

        self.label_source_group = QLabel(self.group_source_layout)
        self.label_source_group.setObjectName(u"label_source_group")

        self.form_source.setWidget(3, QFormLayout.ItemRole.LabelRole, self.label_source_group)

        self.edit_source_group = QLineEdit(self.group_source_layout)
        self.edit_source_group.setObjectName(u"edit_source_group")

        self.form_source.setWidget(3, QFormLayout.ItemRole.FieldRole, self.edit_source_group)

        self.label_source_detail = QLabel(self.group_source_layout)
        self.label_source_detail.setObjectName(u"label_source_detail")

        self.form_source.setWidget(4, QFormLayout.ItemRole.LabelRole, self.label_source_detail)

        self.edit_source_detail = QLineEdit(self.group_source_layout)
        self.edit_source_detail.setObjectName(u"edit_source_detail")

        self.form_source.setWidget(4, QFormLayout.ItemRole.FieldRole, self.edit_source_detail)


        self.layout_coordinates.addWidget(self.group_source_layout)

        self.group_target_layout = QGroupBox(self.tab_layout)
        self.group_target_layout.setObjectName(u"group_target_layout")
        self.form_target = QFormLayout(self.group_target_layout)
        self.form_target.setObjectName(u"form_target")
        self.label_detail_sheet = QLabel(self.group_target_layout)
        self.label_detail_sheet.setObjectName(u"label_detail_sheet")

        self.form_target.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_detail_sheet)

        self.edit_detail_sheet = QLineEdit(self.group_target_layout)
        self.edit_detail_sheet.setObjectName(u"edit_detail_sheet")

        self.form_target.setWidget(0, QFormLayout.ItemRole.FieldRole, self.edit_detail_sheet)

        self.label_detail_name = QLabel(self.group_target_layout)
        self.label_detail_name.setObjectName(u"label_detail_name")

        self.form_target.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_detail_name)

        self.edit_detail_name = QLineEdit(self.group_target_layout)
        self.edit_detail_name.setObjectName(u"edit_detail_name")

        self.form_target.setWidget(1, QFormLayout.ItemRole.FieldRole, self.edit_detail_name)

        self.label_detail_matrix = QLabel(self.group_target_layout)
        self.label_detail_matrix.setObjectName(u"label_detail_matrix")

        self.form_target.setWidget(2, QFormLayout.ItemRole.LabelRole, self.label_detail_matrix)

        self.edit_detail_matrix = QLineEdit(self.group_target_layout)
        self.edit_detail_matrix.setObjectName(u"edit_detail_matrix")

        self.form_target.setWidget(2, QFormLayout.ItemRole.FieldRole, self.edit_detail_matrix)

        self.label_summary_sheet = QLabel(self.group_target_layout)
        self.label_summary_sheet.setObjectName(u"label_summary_sheet")

        self.form_target.setWidget(3, QFormLayout.ItemRole.LabelRole, self.label_summary_sheet)

        self.edit_summary_sheet = QLineEdit(self.group_target_layout)
        self.edit_summary_sheet.setObjectName(u"edit_summary_sheet")

        self.form_target.setWidget(3, QFormLayout.ItemRole.FieldRole, self.edit_summary_sheet)

        self.label_summary_name = QLabel(self.group_target_layout)
        self.label_summary_name.setObjectName(u"label_summary_name")

        self.form_target.setWidget(4, QFormLayout.ItemRole.LabelRole, self.label_summary_name)

        self.edit_summary_name = QLineEdit(self.group_target_layout)
        self.edit_summary_name.setObjectName(u"edit_summary_name")

        self.form_target.setWidget(4, QFormLayout.ItemRole.FieldRole, self.edit_summary_name)

        self.chk_split_groups = QCheckBox(self.group_target_layout)
        self.chk_split_groups.setObjectName(u"chk_split_groups")

        self.form_target.setWidget(5, QFormLayout.ItemRole.SpanningRole, self.chk_split_groups)


        self.layout_coordinates.addWidget(self.group_target_layout)

        self.config_tabs.addTab(self.tab_layout, "")
        self.tab_mappings = QWidget()
        self.tab_mappings.setObjectName(u"tab_mappings")
        self.layout_mappings = QVBoxLayout(self.tab_mappings)
        self.layout_mappings.setObjectName(u"layout_mappings")
        self.label_mapping_help = QLabel(self.tab_mappings)
        self.label_mapping_help.setObjectName(u"label_mapping_help")

        self.layout_mappings.addWidget(self.label_mapping_help)

        self.table_mappings = QTableWidget(self.tab_mappings)
        if (self.table_mappings.columnCount() < 3):
            self.table_mappings.setColumnCount(3)
        __qtablewidgetitem = QTableWidgetItem()
        self.table_mappings.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.table_mappings.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.table_mappings.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        self.table_mappings.setObjectName(u"table_mappings")
        self.table_mappings.setColumnCount(3)
        self.table_mappings.setRowCount(0)

        self.layout_mappings.addWidget(self.table_mappings)

        self.layout_mapping_buttons = QHBoxLayout()
        self.layout_mapping_buttons.setObjectName(u"layout_mapping_buttons")
        self.btn_add_mapping = QPushButton(self.tab_mappings)
        self.btn_add_mapping.setObjectName(u"btn_add_mapping")

        self.layout_mapping_buttons.addWidget(self.btn_add_mapping)

        self.btn_remove_mapping = QPushButton(self.tab_mappings)
        self.btn_remove_mapping.setObjectName(u"btn_remove_mapping")

        self.layout_mapping_buttons.addWidget(self.btn_remove_mapping)

        self.mapping_spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_mapping_buttons.addItem(self.mapping_spacer)


        self.layout_mappings.addLayout(self.layout_mapping_buttons)

        self.config_tabs.addTab(self.tab_mappings, "")
        self.tab_rules = QWidget()
        self.tab_rules.setObjectName(u"tab_rules")
        self.layout_rules = QVBoxLayout(self.tab_rules)
        self.layout_rules.setObjectName(u"layout_rules")
        self.label_rule_help = QLabel(self.tab_rules)
        self.label_rule_help.setObjectName(u"label_rule_help")

        self.layout_rules.addWidget(self.label_rule_help)

        self.table_rules = QTableWidget(self.tab_rules)
        if (self.table_rules.columnCount() < 3):
            self.table_rules.setColumnCount(3)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.table_rules.setHorizontalHeaderItem(0, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.table_rules.setHorizontalHeaderItem(1, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.table_rules.setHorizontalHeaderItem(2, __qtablewidgetitem5)
        self.table_rules.setObjectName(u"table_rules")
        self.table_rules.setColumnCount(3)
        self.table_rules.setRowCount(0)

        self.layout_rules.addWidget(self.table_rules)

        self.layout_rule_buttons = QHBoxLayout()
        self.layout_rule_buttons.setObjectName(u"layout_rule_buttons")
        self.btn_add_rule = QPushButton(self.tab_rules)
        self.btn_add_rule.setObjectName(u"btn_add_rule")

        self.layout_rule_buttons.addWidget(self.btn_add_rule)

        self.btn_remove_rule = QPushButton(self.tab_rules)
        self.btn_remove_rule.setObjectName(u"btn_remove_rule")

        self.layout_rule_buttons.addWidget(self.btn_remove_rule)

        self.btn_rule_up = QPushButton(self.tab_rules)
        self.btn_rule_up.setObjectName(u"btn_rule_up")

        self.layout_rule_buttons.addWidget(self.btn_rule_up)

        self.btn_rule_down = QPushButton(self.tab_rules)
        self.btn_rule_down.setObjectName(u"btn_rule_down")

        self.layout_rule_buttons.addWidget(self.btn_rule_down)

        self.rule_spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_rule_buttons.addItem(self.rule_spacer)


        self.layout_rules.addLayout(self.layout_rule_buttons)

        self.config_tabs.addTab(self.tab_rules, "")
        self.tab_preview = QWidget()
        self.tab_preview.setObjectName(u"tab_preview")
        self.layout_preview = QVBoxLayout(self.tab_preview)
        self.layout_preview.setObjectName(u"layout_preview")
        self.lbl_preview = QLabel(self.tab_preview)
        self.lbl_preview.setObjectName(u"lbl_preview")
        self.lbl_preview.setWordWrap(True)

        self.layout_preview.addWidget(self.lbl_preview)

        self.label_group_preview = QLabel(self.tab_preview)
        self.label_group_preview.setObjectName(u"label_group_preview")

        self.layout_preview.addWidget(self.label_group_preview)

        self.table_group_preview = QTableWidget(self.tab_preview)
        if (self.table_group_preview.columnCount() < 4):
            self.table_group_preview.setColumnCount(4)
        __qtablewidgetitem6 = QTableWidgetItem()
        self.table_group_preview.setHorizontalHeaderItem(0, __qtablewidgetitem6)
        __qtablewidgetitem7 = QTableWidgetItem()
        self.table_group_preview.setHorizontalHeaderItem(1, __qtablewidgetitem7)
        __qtablewidgetitem8 = QTableWidgetItem()
        self.table_group_preview.setHorizontalHeaderItem(2, __qtablewidgetitem8)
        __qtablewidgetitem9 = QTableWidgetItem()
        self.table_group_preview.setHorizontalHeaderItem(3, __qtablewidgetitem9)
        self.table_group_preview.setObjectName(u"table_group_preview")
        self.table_group_preview.setColumnCount(4)
        self.table_group_preview.setRowCount(0)

        self.layout_preview.addWidget(self.table_group_preview)

        self.label_employee_preview = QLabel(self.tab_preview)
        self.label_employee_preview.setObjectName(u"label_employee_preview")

        self.layout_preview.addWidget(self.label_employee_preview)

        self.table_employee_preview = QTableWidget(self.tab_preview)
        if (self.table_employee_preview.columnCount() < 4):
            self.table_employee_preview.setColumnCount(4)
        __qtablewidgetitem10 = QTableWidgetItem()
        self.table_employee_preview.setHorizontalHeaderItem(0, __qtablewidgetitem10)
        __qtablewidgetitem11 = QTableWidgetItem()
        self.table_employee_preview.setHorizontalHeaderItem(1, __qtablewidgetitem11)
        __qtablewidgetitem12 = QTableWidgetItem()
        self.table_employee_preview.setHorizontalHeaderItem(2, __qtablewidgetitem12)
        __qtablewidgetitem13 = QTableWidgetItem()
        self.table_employee_preview.setHorizontalHeaderItem(3, __qtablewidgetitem13)
        self.table_employee_preview.setObjectName(u"table_employee_preview")
        self.table_employee_preview.setColumnCount(4)
        self.table_employee_preview.setRowCount(0)

        self.layout_preview.addWidget(self.table_employee_preview)

        self.layout_preview_adjustments = QHBoxLayout()
        self.layout_preview_adjustments.setObjectName(u"layout_preview_adjustments")
        self.preview_adjustment_spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_preview_adjustments.addItem(self.preview_adjustment_spacer)

        self.btn_apply_adjustments = QPushButton(self.tab_preview)
        self.btn_apply_adjustments.setObjectName(u"btn_apply_adjustments")
        self.btn_apply_adjustments.setEnabled(False)

        self.layout_preview_adjustments.addWidget(self.btn_apply_adjustments)


        self.layout_preview.addLayout(self.layout_preview_adjustments)

        self.config_tabs.addTab(self.tab_preview, "")

        self.verticalLayout.addWidget(self.config_tabs)

        self.layout_actions = QHBoxLayout()
        self.layout_actions.setObjectName(u"layout_actions")
        self.lbl_status = QLabel(AttendanceDialog)
        self.lbl_status.setObjectName(u"lbl_status")

        self.layout_actions.addWidget(self.lbl_status)

        self.action_spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_actions.addItem(self.action_spacer)

        self.btn_preview = QPushButton(AttendanceDialog)
        self.btn_preview.setObjectName(u"btn_preview")

        self.layout_actions.addWidget(self.btn_preview)

        self.btn_generate = QPushButton(AttendanceDialog)
        self.btn_generate.setObjectName(u"btn_generate")
        self.btn_generate.setEnabled(False)

        self.layout_actions.addWidget(self.btn_generate)


        self.verticalLayout.addLayout(self.layout_actions)


        self.retranslateUi(AttendanceDialog)

        QMetaObject.connectSlotsByName(AttendanceDialog)
    # setupUi

    def retranslateUi(self, AttendanceDialog):
        AttendanceDialog.setWindowTitle(QCoreApplication.translate("AttendanceDialog", u"\u8003\u52e4\u6c47\u603b", None))
        self.group_files.setTitle(QCoreApplication.translate("AttendanceDialog", u"\u6587\u4ef6\u4e0e\u6708\u4efd", None))
        self.label_source.setText(QCoreApplication.translate("AttendanceDialog", u"\u539f\u59cb\u8003\u52e4", None))
        self.edit_source.setPlaceholderText(QCoreApplication.translate("AttendanceDialog", u"\u9009\u62e9\u539f\u59cb\u8003\u52e4 .xlsx", None))
        self.btn_source.setText(QCoreApplication.translate("AttendanceDialog", u"\u6d4f\u89c8\u2026", None))
        self.label_year.setText(QCoreApplication.translate("AttendanceDialog", u"\u5e74\u4efd", None))
        self.label_month.setText(QCoreApplication.translate("AttendanceDialog", u"\u6708\u4efd", None))
        self.label_template.setText(QCoreApplication.translate("AttendanceDialog", u"\u6c47\u603b\u6a21\u677f", None))
        self.edit_template.setPlaceholderText(QCoreApplication.translate("AttendanceDialog", u"\u9009\u62e9\u4e0d\u4f1a\u88ab\u4fee\u6539\u7684\u6a21\u677f .xlsx", None))
        self.btn_template.setText(QCoreApplication.translate("AttendanceDialog", u"\u6d4f\u89c8\u2026", None))
        self.label_output.setText(QCoreApplication.translate("AttendanceDialog", u"\u53e6\u5b58\u7ed3\u679c", None))
        self.edit_output.setPlaceholderText(QCoreApplication.translate("AttendanceDialog", u"\u6307\u5b9a\u65b0\u7684\u8f93\u51fa .xlsx\uff0c\u4e0d\u80fd\u4e0e\u6e90\u6587\u4ef6\u6216\u6a21\u677f\u76f8\u540c", None))
        self.btn_output.setText(QCoreApplication.translate("AttendanceDialog", u"\u6d4f\u89c8\u2026", None))
        self.group_plan.setTitle(QCoreApplication.translate("AttendanceDialog", u"\u65b9\u6848", None))
        self.edit_plan_name.setPlaceholderText(QCoreApplication.translate("AttendanceDialog", u"\u65b9\u6848\u540d\u79f0", None))
        self.btn_load_plan.setText(QCoreApplication.translate("AttendanceDialog", u"\u52a0\u8f7d", None))
        self.btn_save_plan.setText(QCoreApplication.translate("AttendanceDialog", u"\u4fdd\u5b58", None))
        self.btn_delete_plan.setText(QCoreApplication.translate("AttendanceDialog", u"\u5220\u9664", None))
        self.group_source_layout.setTitle(QCoreApplication.translate("AttendanceDialog", u"\u539f\u59cb\u8003\u52e4\uff08\u5458\u5de5\u5411\u4e0b\u3001\u65e5\u671f\u5411\u53f3\uff09", None))
        self.label_source_sheet.setText(QCoreApplication.translate("AttendanceDialog", u"Sheet \u540d", None))
        self.label_source_name.setText(QCoreApplication.translate("AttendanceDialog", u"\u59d3\u540d\u8d77\u59cb", None))
        self.label_source_department.setText(QCoreApplication.translate("AttendanceDialog", u"\u90e8\u95e8\u8d77\u59cb", None))
        self.label_source_group.setText(QCoreApplication.translate("AttendanceDialog", u"\u8003\u52e4\u7ec4\u8d77\u59cb", None))
        self.label_source_detail.setText(QCoreApplication.translate("AttendanceDialog", u"\u660e\u7ec6\u5de6\u4e0a\u89d2", None))
        self.group_target_layout.setTitle(QCoreApplication.translate("AttendanceDialog", u"\u6c47\u603b\u6a21\u677f", None))
        self.label_detail_sheet.setText(QCoreApplication.translate("AttendanceDialog", u"\u660e\u7ec6 Sheet", None))
        self.label_detail_name.setText(QCoreApplication.translate("AttendanceDialog", u"\u660e\u7ec6\u59d3\u540d\u8d77\u59cb", None))
        self.label_detail_matrix.setText(QCoreApplication.translate("AttendanceDialog", u"\u660e\u7ec6\u77e9\u9635\u5de6\u4e0a\u89d2", None))
        self.label_summary_sheet.setText(QCoreApplication.translate("AttendanceDialog", u"\u6c47\u603b Sheet", None))
        self.label_summary_name.setText(QCoreApplication.translate("AttendanceDialog", u"\u6c47\u603b\u59d3\u540d\u8d77\u59cb", None))
        self.chk_split_groups.setText(QCoreApplication.translate("AttendanceDialog", u"\u6309\u8003\u52e4\u7ec4\u62c6\u5206\uff08\u6bcf\u7ec4\u81ea\u52a8\u751f\u6210\u660e\u7ec6/\u6c47\u603b Sheet\uff09", None))
        self.config_tabs.setTabText(self.config_tabs.indexOf(self.tab_layout), QCoreApplication.translate("AttendanceDialog", u"\u5de5\u4f5c\u8868\u4e0e\u5750\u6807", None))
        self.label_mapping_help.setText(QCoreApplication.translate("AttendanceDialog", u"\u5185\u5bb9\u652f\u6301 {{year}}\u3001{{month}}\u3001{{month_start}}\u3001{{month_end}}\u3001{{department}}\uff1b\u5206\u7ec4\u660e\u7ec6/\u6c47\u603b\u8fd8\u652f\u6301 {{attendance_group}}", None))
        ___qtablewidgetitem = self.table_mappings.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("AttendanceDialog", u"Sheet \u540d", None))
        ___qtablewidgetitem1 = self.table_mappings.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("AttendanceDialog", u"\u5355\u5143\u683c", None))
        ___qtablewidgetitem2 = self.table_mappings.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("AttendanceDialog", u"\u5185\u5bb9", None))
        self.btn_add_mapping.setText(QCoreApplication.translate("AttendanceDialog", u"\u65b0\u589e\u6620\u5c04", None))
        self.btn_remove_mapping.setText(QCoreApplication.translate("AttendanceDialog", u"\u5220\u9664\u9009\u4e2d", None))
        self.config_tabs.setTabText(self.config_tabs.indexOf(self.tab_mappings), QCoreApplication.translate("AttendanceDialog", u"\u56fa\u5b9a\u5355\u5143\u683c", None))
        self.label_rule_help.setText(QCoreApplication.translate("AttendanceDialog", u"\u4ece\u4e0a\u5230\u4e0b\u9996\u4e2a\u6b63\u5219\u5339\u914d\u751f\u6548\uff1b\u975e\u7a7a\u4e14\u672a\u5339\u914d\u7684\u8bb0\u5f55\u4f1a\u963b\u6b62\u751f\u6210\u3002", None))
        ___qtablewidgetitem3 = self.table_rules.horizontalHeaderItem(0)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("AttendanceDialog", u"\u542f\u7528", None))
        ___qtablewidgetitem4 = self.table_rules.horizontalHeaderItem(1)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("AttendanceDialog", u"\u6b63\u5219", None))
        ___qtablewidgetitem5 = self.table_rules.horizontalHeaderItem(2)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("AttendanceDialog", u"\u8f93\u51fa", None))
        self.btn_add_rule.setText(QCoreApplication.translate("AttendanceDialog", u"\u65b0\u589e\u89c4\u5219", None))
        self.btn_remove_rule.setText(QCoreApplication.translate("AttendanceDialog", u"\u5220\u9664\u9009\u4e2d", None))
        self.btn_rule_up.setText(QCoreApplication.translate("AttendanceDialog", u"\u4e0a\u79fb", None))
        self.btn_rule_down.setText(QCoreApplication.translate("AttendanceDialog", u"\u4e0b\u79fb", None))
        self.config_tabs.setTabText(self.config_tabs.indexOf(self.tab_rules), QCoreApplication.translate("AttendanceDialog", u"\u5224\u5b9a\u89c4\u5219", None))
        self.lbl_preview.setText(QCoreApplication.translate("AttendanceDialog", u"\u5c1a\u672a\u9884\u89c8", None))
        self.label_group_preview.setText(QCoreApplication.translate("AttendanceDialog", u"\u5206\u7ec4\u8f93\u51fa\uff08\u53ef\u7f16\u8f91\u660e\u7ec6/\u6c47\u603b Sheet \u540d\uff09", None))
        ___qtablewidgetitem6 = self.table_group_preview.horizontalHeaderItem(0)
        ___qtablewidgetitem6.setText(QCoreApplication.translate("AttendanceDialog", u"\u8f93\u51fa\u8003\u52e4\u7ec4", None))
        ___qtablewidgetitem7 = self.table_group_preview.horizontalHeaderItem(1)
        ___qtablewidgetitem7.setText(QCoreApplication.translate("AttendanceDialog", u"\u4eba\u6570", None))
        ___qtablewidgetitem8 = self.table_group_preview.horizontalHeaderItem(2)
        ___qtablewidgetitem8.setText(QCoreApplication.translate("AttendanceDialog", u"\u660e\u7ec6 Sheet", None))
        ___qtablewidgetitem9 = self.table_group_preview.horizontalHeaderItem(3)
        ___qtablewidgetitem9.setText(QCoreApplication.translate("AttendanceDialog", u"\u6c47\u603b Sheet", None))
        self.label_employee_preview.setText(QCoreApplication.translate("AttendanceDialog", u"\u4eba\u5458\u5206\u7ec4\uff08\u53ef\u7f16\u8f91\u8f93\u51fa\u8003\u52e4\u7ec4\uff1b\u672a\u5339\u914d\u8bb0\u5f55\u4ecd\u4f1a\u963b\u6b62\u751f\u6210\uff09", None))
        ___qtablewidgetitem10 = self.table_employee_preview.horizontalHeaderItem(0)
        ___qtablewidgetitem10.setText(QCoreApplication.translate("AttendanceDialog", u"\u59d3\u540d", None))
        ___qtablewidgetitem11 = self.table_employee_preview.horizontalHeaderItem(1)
        ___qtablewidgetitem11.setText(QCoreApplication.translate("AttendanceDialog", u"\u539f\u8003\u52e4\u7ec4", None))
        ___qtablewidgetitem12 = self.table_employee_preview.horizontalHeaderItem(2)
        ___qtablewidgetitem12.setText(QCoreApplication.translate("AttendanceDialog", u"\u8f93\u51fa\u8003\u52e4\u7ec4", None))
        ___qtablewidgetitem13 = self.table_employee_preview.horizontalHeaderItem(3)
        ___qtablewidgetitem13.setText(QCoreApplication.translate("AttendanceDialog", u"\u672a\u5339\u914d", None))
        self.btn_apply_adjustments.setText(QCoreApplication.translate("AttendanceDialog", u"\u5e94\u7528\u8c03\u6574\u5e76\u91cd\u65b0\u9884\u89c8", None))
        self.config_tabs.setTabText(self.config_tabs.indexOf(self.tab_preview), QCoreApplication.translate("AttendanceDialog", u"\u9884\u89c8\u7ed3\u679c", None))
        self.lbl_status.setText(QCoreApplication.translate("AttendanceDialog", u"\u5c31\u7eea", None))
        self.btn_preview.setText(QCoreApplication.translate("AttendanceDialog", u"\u9884\u89c8\u5e76\u6821\u9a8c", None))
        self.btn_generate.setText(QCoreApplication.translate("AttendanceDialog", u"\u751f\u6210\u5e76\u53e6\u5b58", None))
    # retranslateUi
