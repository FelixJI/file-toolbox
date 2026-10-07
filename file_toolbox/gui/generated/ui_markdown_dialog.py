# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'markdown_dialog.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QSpacerItem,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

class Ui_MarkdownConvertDialog(object):
    def setupUi(self, MarkdownConvertDialog):
        if not MarkdownConvertDialog.objectName():
            MarkdownConvertDialog.setObjectName(u"MarkdownConvertDialog")
        self.verticalLayout_main = QVBoxLayout(MarkdownConvertDialog)
        self.verticalLayout_main.setObjectName(u"verticalLayout_main")
        self.horizontalLayout_files = QHBoxLayout()
        self.horizontalLayout_files.setObjectName(u"horizontalLayout_files")
        self.btn_add_files = QPushButton(MarkdownConvertDialog)
        self.btn_add_files.setObjectName(u"btn_add_files")

        self.horizontalLayout_files.addWidget(self.btn_add_files)

        self.btn_add_folder = QPushButton(MarkdownConvertDialog)
        self.btn_add_folder.setObjectName(u"btn_add_folder")

        self.horizontalLayout_files.addWidget(self.btn_add_folder)

        self.btn_clear = QPushButton(MarkdownConvertDialog)
        self.btn_clear.setObjectName(u"btn_clear")

        self.horizontalLayout_files.addWidget(self.btn_clear)

        self.horizontalSpacer_files = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_files.addItem(self.horizontalSpacer_files)


        self.verticalLayout_main.addLayout(self.horizontalLayout_files)

        self.list_files = QListWidget(MarkdownConvertDialog)
        self.list_files.setObjectName(u"list_files")

        self.verticalLayout_main.addWidget(self.list_files)

        self.horizontalLayout_output = QHBoxLayout()
        self.horizontalLayout_output.setObjectName(u"horizontalLayout_output")
        self.label_outdir = QLabel(MarkdownConvertDialog)
        self.label_outdir.setObjectName(u"label_outdir")

        self.horizontalLayout_output.addWidget(self.label_outdir)

        self.edit_outdir = QLineEdit(MarkdownConvertDialog)
        self.edit_outdir.setObjectName(u"edit_outdir")

        self.horizontalLayout_output.addWidget(self.edit_outdir)

        self.btn_browse = QPushButton(MarkdownConvertDialog)
        self.btn_browse.setObjectName(u"btn_browse")

        self.horizontalLayout_output.addWidget(self.btn_browse)

        self.label_target = QLabel(MarkdownConvertDialog)
        self.label_target.setObjectName(u"label_target")

        self.horizontalLayout_output.addWidget(self.label_target)

        self.cmb_target = QComboBox(MarkdownConvertDialog)
        self.cmb_target.addItem("")
        self.cmb_target.addItem("")
        self.cmb_target.setObjectName(u"cmb_target")

        self.horizontalLayout_output.addWidget(self.cmb_target)

        self.label_excel_mode = QLabel(MarkdownConvertDialog)
        self.label_excel_mode.setObjectName(u"label_excel_mode")

        self.horizontalLayout_output.addWidget(self.label_excel_mode)

        self.cmb_excel_mode = QComboBox(MarkdownConvertDialog)
        self.cmb_excel_mode.addItem("")
        self.cmb_excel_mode.addItem("")
        self.cmb_excel_mode.setObjectName(u"cmb_excel_mode")

        self.horizontalLayout_output.addWidget(self.cmb_excel_mode)


        self.verticalLayout_main.addLayout(self.horizontalLayout_output)

        self.lbl_hint = QLabel(MarkdownConvertDialog)
        self.lbl_hint.setObjectName(u"lbl_hint")
        self.lbl_hint.setWordWrap(True)

        self.verticalLayout_main.addWidget(self.lbl_hint)

        self.horizontalLayout_actions = QHBoxLayout()
        self.horizontalLayout_actions.setObjectName(u"horizontalLayout_actions")
        self.btn_convert = QPushButton(MarkdownConvertDialog)
        self.btn_convert.setObjectName(u"btn_convert")

        self.horizontalLayout_actions.addWidget(self.btn_convert)

        self.btn_cancel = QPushButton(MarkdownConvertDialog)
        self.btn_cancel.setObjectName(u"btn_cancel")
        self.btn_cancel.setEnabled(False)

        self.horizontalLayout_actions.addWidget(self.btn_cancel)

        self.horizontalSpacer_status = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_actions.addItem(self.horizontalSpacer_status)

        self.lbl_status = QLabel(MarkdownConvertDialog)
        self.lbl_status.setObjectName(u"lbl_status")

        self.horizontalLayout_actions.addWidget(self.lbl_status)


        self.verticalLayout_main.addLayout(self.horizontalLayout_actions)

        self.table = QTableWidget(MarkdownConvertDialog)
        if (self.table.columnCount() < 4):
            self.table.setColumnCount(4)
        __qtablewidgetitem = QTableWidgetItem()
        self.table.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.table.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.table.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.table.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        self.table.setObjectName(u"table")
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.table.sizePolicy().hasHeightForWidth())
        self.table.setSizePolicy(sizePolicy)
        self.table.setColumnCount(4)
        self.table.setRowCount(0)

        self.verticalLayout_main.addWidget(self.table)


        self.retranslateUi(MarkdownConvertDialog)

        self.cmb_target.setCurrentIndex(0)
        self.cmb_excel_mode.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MarkdownConvertDialog)
    # setupUi

    def retranslateUi(self, MarkdownConvertDialog):
        self.btn_add_files.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u6dfb\u52a0\u6587\u4ef6", None))
        self.btn_add_folder.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u6dfb\u52a0\u6587\u4ef6\u5939", None))
        self.btn_clear.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u6e05\u7a7a", None))
        self.label_outdir.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u8f93\u51fa\u76ee\u5f55:", None))
        self.edit_outdir.setPlaceholderText(QCoreApplication.translate("MarkdownConvertDialog", u"\u7559\u7a7a\u5219\u8f93\u51fa\u5230\u5404\u6e90\u6587\u4ef6\u6240\u5728\u76ee\u5f55", None))
        self.btn_browse.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u6d4f\u89c8", None))
        self.label_target.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u76ee\u6807\u683c\u5f0f:", None))
        self.cmb_target.setItemText(0, QCoreApplication.translate("MarkdownConvertDialog", u"Word (.docx)", None))
        self.cmb_target.setItemText(1, QCoreApplication.translate("MarkdownConvertDialog", u"Excel (.xlsx)", None))

        self.label_excel_mode.setText(QCoreApplication.translate("MarkdownConvertDialog", u"Excel\u6a21\u5f0f:", None))
        self.cmb_excel_mode.setItemText(0, QCoreApplication.translate("MarkdownConvertDialog", u"\u4ec5\u8868\u683c", None))
        self.cmb_excel_mode.setItemText(1, QCoreApplication.translate("MarkdownConvertDialog", u"\u5305\u542b\u6b63\u6587", None))

        self.lbl_hint.setText(QCoreApplication.translate("MarkdownConvertDialog", u"Word \u8f93\u51fa\u7531 Pandoc \u8f6c\u6362:\u4fdd\u7559\u6807\u9898\u3001\u5217\u8868\u3001\u8868\u683c\u3001\u4ee3\u7801\u3001\u94fe\u63a5\u4e0e\u516c\u5f0f;\u4e0d\u52a0\u8f7d\u5916\u90e8\u56fe\u7247\uff0c\u542b\u56fe\u7247\u7684\u6587\u4ef6\u4f1a\u8f6c\u6362\u5931\u8d25\u5e76\u5728\u7ed3\u679c\u4e2d\u62a5\u544a\u3002", None))
        self.btn_convert.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u5f00\u59cb\u8f6c\u6362", None))
        self.btn_cancel.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u53d6\u6d88", None))
        self.lbl_status.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u5c31\u7eea", None))
        ___qtablewidgetitem = self.table.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u6587\u4ef6", None))
        ___qtablewidgetitem1 = self.table.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u7ed3\u679c", None))
        ___qtablewidgetitem2 = self.table.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u8f93\u51fa", None))
        ___qtablewidgetitem3 = self.table.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("MarkdownConvertDialog", u"\u8bf4\u660e", None))
        pass
    # retranslateUi
