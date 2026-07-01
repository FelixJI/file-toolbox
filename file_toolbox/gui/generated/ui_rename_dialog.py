################################################################################
## Form generated from reading UI file 'file_renamer_dialog.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QMetaObject,
    QSize,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class Ui_FileRenamerDialog:
    def setupUi(self, FileRenamerDialog):
        if not FileRenamerDialog.objectName():
            FileRenamerDialog.setObjectName("FileRenamerDialog")
        FileRenamerDialog.resize(900, 700)
        self.verticalLayout = QVBoxLayout(FileRenamerDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.btn_select_files = QPushButton(FileRenamerDialog)
        self.btn_select_files.setObjectName("btn_select_files")

        self.horizontalLayout.addWidget(self.btn_select_files)

        self.btn_select_folder = QPushButton(FileRenamerDialog)
        self.btn_select_folder.setObjectName("btn_select_folder")

        self.horizontalLayout.addWidget(self.btn_select_folder)

        self.btn_clear_files = QPushButton(FileRenamerDialog)
        self.btn_clear_files.setObjectName("btn_clear_files")

        self.horizontalLayout.addWidget(self.btn_clear_files)

        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btn_load_template = QPushButton(FileRenamerDialog)
        self.btn_load_template.setObjectName("btn_load_template")

        self.horizontalLayout.addWidget(self.btn_load_template)

        self.btn_save_template = QPushButton(FileRenamerDialog)
        self.btn_save_template.setObjectName("btn_save_template")

        self.horizontalLayout.addWidget(self.btn_save_template)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.label_files = QLabel(FileRenamerDialog)
        self.label_files.setObjectName("label_files")

        self.verticalLayout.addWidget(self.label_files)

        self.list_files = QListWidget(FileRenamerDialog)
        self.list_files.setObjectName("list_files")
        self.list_files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_files.setMaximumSize(QSize(16777215, 150))

        self.verticalLayout.addWidget(self.list_files)

        self.line = QFrame(FileRenamerDialog)
        self.line.setObjectName("line")
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout.addWidget(self.line)

        self.label_operations = QLabel(FileRenamerDialog)
        self.label_operations.setObjectName("label_operations")

        self.verticalLayout.addWidget(self.label_operations)

        self.list_operations = QListWidget(FileRenamerDialog)
        self.list_operations.setObjectName("list_operations")
        self.list_operations.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_operations.setMaximumSize(QSize(16777215, 150))

        self.verticalLayout.addWidget(self.list_operations)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.btn_add_prefix = QPushButton(FileRenamerDialog)
        self.btn_add_prefix.setObjectName("btn_add_prefix")

        self.horizontalLayout_2.addWidget(self.btn_add_prefix)

        self.btn_add_suffix = QPushButton(FileRenamerDialog)
        self.btn_add_suffix.setObjectName("btn_add_suffix")

        self.horizontalLayout_2.addWidget(self.btn_add_suffix)

        self.btn_replace_text = QPushButton(FileRenamerDialog)
        self.btn_replace_text.setObjectName("btn_replace_text")

        self.horizontalLayout_2.addWidget(self.btn_replace_text)

        self.btn_regex_replace = QPushButton(FileRenamerDialog)
        self.btn_regex_replace.setObjectName("btn_regex_replace")

        self.horizontalLayout_2.addWidget(self.btn_regex_replace)

        self.btn_add_number = QPushButton(FileRenamerDialog)
        self.btn_add_number.setObjectName("btn_add_number")

        self.horizontalLayout_2.addWidget(self.btn_add_number)

        self.btn_delete_chars = QPushButton(FileRenamerDialog)
        self.btn_delete_chars.setObjectName("btn_delete_chars")

        self.horizontalLayout_2.addWidget(self.btn_delete_chars)

        self.btn_add_date = QPushButton(FileRenamerDialog)
        self.btn_add_date.setObjectName("btn_add_date")

        self.horizontalLayout_2.addWidget(self.btn_add_date)

        self.btn_edit_operation = QPushButton(FileRenamerDialog)
        self.btn_edit_operation.setObjectName("btn_edit_operation")

        self.horizontalLayout_2.addWidget(self.btn_edit_operation)

        self.btn_remove_operation = QPushButton(FileRenamerDialog)
        self.btn_remove_operation.setObjectName("btn_remove_operation")

        self.horizontalLayout_2.addWidget(self.btn_remove_operation)

        self.verticalLayout.addLayout(self.horizontalLayout_2)

        self.line_2 = QFrame(FileRenamerDialog)
        self.line_2.setObjectName("line_2")
        self.line_2.setFrameShape(QFrame.Shape.HLine)
        self.line_2.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout.addWidget(self.line_2)

        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.label_preview = QLabel(FileRenamerDialog)
        self.label_preview.setObjectName("label_preview")

        self.horizontalLayout_3.addWidget(self.label_preview)

        self.horizontalSpacer_2 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_3.addItem(self.horizontalSpacer_2)

        self.btn_refresh_preview = QPushButton(FileRenamerDialog)
        self.btn_refresh_preview.setObjectName("btn_refresh_preview")

        self.horizontalLayout_3.addWidget(self.btn_refresh_preview)

        self.verticalLayout.addLayout(self.horizontalLayout_3)

        self.table_preview = QTableWidget(FileRenamerDialog)
        if self.table_preview.columnCount() < 5:
            self.table_preview.setColumnCount(5)
        __qtablewidgetitem = QTableWidgetItem()
        self.table_preview.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.table_preview.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.table_preview.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.table_preview.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.table_preview.setHorizontalHeaderItem(4, __qtablewidgetitem4)
        self.table_preview.setObjectName("table_preview")
        self.table_preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_preview.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_preview.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.verticalLayout.addWidget(self.table_preview)

        self.line_3 = QFrame(FileRenamerDialog)
        self.line_3.setObjectName("line_3")
        self.line_3.setFrameShape(QFrame.Shape.HLine)
        self.line_3.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout.addWidget(self.line_3)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.label_status = QLabel(FileRenamerDialog)
        self.label_status.setObjectName("label_status")

        self.horizontalLayout_4.addWidget(self.label_status)

        self.horizontalSpacer_3 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_4.addItem(self.horizontalSpacer_3)

        self.btn_show_history = QPushButton(FileRenamerDialog)
        self.btn_show_history.setObjectName("btn_show_history")

        self.horizontalLayout_4.addWidget(self.btn_show_history)

        self.btn_cancel = QPushButton(FileRenamerDialog)
        self.btn_cancel.setObjectName("btn_cancel")

        self.horizontalLayout_4.addWidget(self.btn_cancel)

        self.btn_execute = QPushButton(FileRenamerDialog)
        self.btn_execute.setObjectName("btn_execute")

        self.horizontalLayout_4.addWidget(self.btn_execute)

        self.verticalLayout.addLayout(self.horizontalLayout_4)

        self.retranslateUi(FileRenamerDialog)

        QMetaObject.connectSlotsByName(FileRenamerDialog)

    # setupUi

    def retranslateUi(self, FileRenamerDialog):
        FileRenamerDialog.setWindowTitle(
            QCoreApplication.translate(
                "FileRenamerDialog",
                "\u6279\u91cf\u91cd\u547d\u540d\u6587\u4ef6/\u6587\u4ef6\u5939",
                None,
            )
        )
        self.btn_select_files.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u9009\u62e9\u6587\u4ef6", None)
        )
        self.btn_select_folder.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u9009\u62e9\u6587\u4ef6\u5939", None)
        )
        self.btn_clear_files.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u6e05\u7a7a\u5217\u8868", None)
        )
        self.btn_load_template.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u52a0\u8f7d\u6a21\u677f", None)
        )
        self.btn_save_template.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u4fdd\u5b58\u6a21\u677f", None)
        )
        self.label_files.setText(
            QCoreApplication.translate(
                "FileRenamerDialog", "\u539f\u59cb\u6587\u4ef6\u5217\u8868\uff1a", None
            )
        )
        self.label_operations.setText(
            QCoreApplication.translate(
                "FileRenamerDialog",
                "\u91cd\u547d\u540d\u64cd\u4f5c\uff08\u53ef\u62d6\u62fd\u8c03\u6574\u987a\u5e8f\uff09\uff1a",
                None,
            )
        )
        self.btn_add_prefix.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u6dfb\u52a0\u524d\u7f00", None)
        )
        self.btn_add_suffix.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u6dfb\u52a0\u540e\u7f00", None)
        )
        self.btn_replace_text.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u66ff\u6362\u5b57\u7b26", None)
        )
        self.btn_regex_replace.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u6b63\u5219\u66ff\u6362", None)
        )
        self.btn_add_number.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u6dfb\u52a0\u5e8f\u53f7", None)
        )
        self.btn_delete_chars.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u5220\u9664\u5b57\u7b26", None)
        )
        self.btn_add_date.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u6dfb\u52a0\u65e5\u671f", None)
        )
        self.btn_edit_operation.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u7f16\u8f91\u64cd\u4f5c", None)
        )
        self.btn_remove_operation.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u5220\u9664\u64cd\u4f5c", None)
        )
        self.label_preview.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u9884\u89c8\u7ed3\u679c\uff1a", None)
        )
        self.btn_refresh_preview.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u5237\u65b0\u9884\u89c8", None)
        )
        ___qtablewidgetitem = self.table_preview.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u539f\u6587\u4ef6\u540d", None)
        )
        ___qtablewidgetitem1 = self.table_preview.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u65b0\u6587\u4ef6\u540d", None)
        )
        ___qtablewidgetitem2 = self.table_preview.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u5927\u5c0f", None)
        )
        ___qtablewidgetitem3 = self.table_preview.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u4fee\u6539\u65f6\u95f4", None)
        )
        ___qtablewidgetitem4 = self.table_preview.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u72b6\u6001", None)
        )
        self.label_status.setText(
            QCoreApplication.translate(
                "FileRenamerDialog",
                "\u5df2\u9009\u62e9 0 \u4e2a\u6587\u4ef6\uff0c0 \u4e2a\u6587\u4ef6\u5939",
                None,
            )
        )
        self.btn_show_history.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u5386\u53f2\u8bb0\u5f55", None)
        )
        self.btn_cancel.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u53d6\u6d88", None)
        )
        self.btn_execute.setText(
            QCoreApplication.translate("FileRenamerDialog", "\u6267\u884c\u91cd\u547d\u540d", None)
        )

    # retranslateUi
