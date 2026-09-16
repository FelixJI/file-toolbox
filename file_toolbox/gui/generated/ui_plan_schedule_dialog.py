# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'plan_schedule_dialog.ui'
##
## Created by: Qt User Interface Compiler version 6.11.2
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
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSpacerItem, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

class Ui_PlanScheduleDialog(object):
    def setupUi(self, PlanScheduleDialog):
        if not PlanScheduleDialog.objectName():
            PlanScheduleDialog.setObjectName(u"PlanScheduleDialog")
        self.verticalLayout_main = QVBoxLayout(PlanScheduleDialog)
        self.verticalLayout_main.setObjectName(u"verticalLayout_main")
        self.horizontalLayout_input = QHBoxLayout()
        self.horizontalLayout_input.setObjectName(u"horizontalLayout_input")
        self.label_input = QLabel(PlanScheduleDialog)
        self.label_input.setObjectName(u"label_input")

        self.horizontalLayout_input.addWidget(self.label_input)

        self.edit_input = QLineEdit(PlanScheduleDialog)
        self.edit_input.setObjectName(u"edit_input")

        self.horizontalLayout_input.addWidget(self.edit_input)

        self.btn_browse_input = QPushButton(PlanScheduleDialog)
        self.btn_browse_input.setObjectName(u"btn_browse_input")

        self.horizontalLayout_input.addWidget(self.btn_browse_input)

        self.btn_template = QPushButton(PlanScheduleDialog)
        self.btn_template.setObjectName(u"btn_template")

        self.horizontalLayout_input.addWidget(self.btn_template)


        self.verticalLayout_main.addLayout(self.horizontalLayout_input)

        self.horizontalLayout_output = QHBoxLayout()
        self.horizontalLayout_output.setObjectName(u"horizontalLayout_output")
        self.label_outdir = QLabel(PlanScheduleDialog)
        self.label_outdir.setObjectName(u"label_outdir")

        self.horizontalLayout_output.addWidget(self.label_outdir)

        self.edit_outdir = QLineEdit(PlanScheduleDialog)
        self.edit_outdir.setObjectName(u"edit_outdir")

        self.horizontalLayout_output.addWidget(self.edit_outdir)

        self.btn_browse = QPushButton(PlanScheduleDialog)
        self.btn_browse.setObjectName(u"btn_browse")

        self.horizontalLayout_output.addWidget(self.btn_browse)

        self.label_year = QLabel(PlanScheduleDialog)
        self.label_year.setObjectName(u"label_year")

        self.horizontalLayout_output.addWidget(self.label_year)

        self.spin_year = QSpinBox(PlanScheduleDialog)
        self.spin_year.setObjectName(u"spin_year")
        self.spin_year.setMinimum(2000)
        self.spin_year.setMaximum(2100)

        self.horizontalLayout_output.addWidget(self.spin_year)

        self.label_cell = QLabel(PlanScheduleDialog)
        self.label_cell.setObjectName(u"label_cell")

        self.horizontalLayout_output.addWidget(self.label_cell)

        self.cmb_cell = QComboBox(PlanScheduleDialog)
        self.cmb_cell.addItem("")
        self.cmb_cell.addItem("")
        self.cmb_cell.setObjectName(u"cmb_cell")

        self.horizontalLayout_output.addWidget(self.cmb_cell)


        self.verticalLayout_main.addLayout(self.horizontalLayout_output)

        self.horizontalLayout_buttons = QHBoxLayout()
        self.horizontalLayout_buttons.setObjectName(u"horizontalLayout_buttons")
        self.btn_generate = QPushButton(PlanScheduleDialog)
        self.btn_generate.setObjectName(u"btn_generate")

        self.horizontalLayout_buttons.addWidget(self.btn_generate)

        self.horizontalSpacer_status = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_buttons.addItem(self.horizontalSpacer_status)

        self.lbl_status = QLabel(PlanScheduleDialog)
        self.lbl_status.setObjectName(u"lbl_status")

        self.horizontalLayout_buttons.addWidget(self.lbl_status)


        self.verticalLayout_main.addLayout(self.horizontalLayout_buttons)

        self.table = QTableWidget(PlanScheduleDialog)
        if (self.table.columnCount() < 5):
            self.table.setColumnCount(5)
        __qtablewidgetitem = QTableWidgetItem()
        self.table.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.table.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.table.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.table.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.table.setHorizontalHeaderItem(4, __qtablewidgetitem4)
        self.table.setObjectName(u"table")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.table.sizePolicy().hasHeightForWidth())
        self.table.setSizePolicy(sizePolicy)
        self.table.setColumnCount(5)
        self.table.setRowCount(0)

        self.verticalLayout_main.addWidget(self.table)


        self.retranslateUi(PlanScheduleDialog)

        self.cmb_cell.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(PlanScheduleDialog)
    # setupUi

    def retranslateUi(self, PlanScheduleDialog):
        self.label_input.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u9879\u70b9\u6e05\u5355:", None))
        self.edit_input.setPlaceholderText(QCoreApplication.translate("PlanScheduleDialog", u"\u9009\u62e9\u6e05\u5355 Excel:\u9879\u70b9\u540d\u79f0 / \u8d77\u59cb\u65e5\u671f / \u7ec8\u6b62\u65e5\u671f", None))
        self.btn_browse_input.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u9009\u62e9", None))
        self.btn_template.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u5bfc\u51fa\u6a21\u677f", None))
        self.label_outdir.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u8f93\u51fa\u76ee\u5f55:", None))
        self.edit_outdir.setPlaceholderText(QCoreApplication.translate("PlanScheduleDialog", u"\u9009\u62e9\u6216\u8f93\u5165\u8f93\u51fa\u76ee\u5f55(\u9ed8\u8ba4\u8ddf\u968f\u4e0a\u6b21\u6216\u6e05\u5355\u6240\u5728\u76ee\u5f55)", None))
        self.btn_browse.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u6d4f\u89c8", None))
        self.label_year.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u7f3a\u7701\u5e74\u4efd:", None))
        self.label_cell.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u683c\u5b50\u5185\u5bb9:", None))
        self.cmb_cell.setItemText(0, QCoreApplication.translate("PlanScheduleDialog", u"\u7b2c\u51e0\u5929(1,2,3\u2026)", None))
        self.cmb_cell.setItemText(1, QCoreApplication.translate("PlanScheduleDialog", u"\u9879\u70b9\u540d\u79f0(\u7b2cx\u5217/\u6279\u6b21)", None))

        self.btn_generate.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u751f\u6210\u8ba1\u5212\u6392\u5e03", None))
        self.lbl_status.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u5c31\u7eea", None))
        ___qtablewidgetitem = self.table.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u9879\u70b9", None))
        ___qtablewidgetitem1 = self.table.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u5f00\u59cb", None))
        ___qtablewidgetitem2 = self.table.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u7ed3\u675f", None))
        ___qtablewidgetitem3 = self.table.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u5929\u6570", None))
        ___qtablewidgetitem4 = self.table.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("PlanScheduleDialog", u"\u72b6\u6001", None))
        pass
    # retranslateUi
