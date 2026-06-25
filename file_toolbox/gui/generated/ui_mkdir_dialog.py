################################################################################
## Form generated from reading UI file 'batch_folder_creator_dialog.ui'
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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTableWidget,
    QTreeWidget,
    QVBoxLayout,
)


class Ui_BatchFolderCreatorDialog:
    def setupUi(self, BatchFolderCreatorDialog):
        if not BatchFolderCreatorDialog.objectName():
            BatchFolderCreatorDialog.setObjectName("BatchFolderCreatorDialog")
        BatchFolderCreatorDialog.resize(1000, 700)
        self.verticalLayout_main = QVBoxLayout(BatchFolderCreatorDialog)
        self.verticalLayout_main.setObjectName("verticalLayout_main")
        self.horizontalLayout_root = QHBoxLayout()
        self.horizontalLayout_root.setObjectName("horizontalLayout_root")
        self.label_root = QLabel(BatchFolderCreatorDialog)
        self.label_root.setObjectName("label_root")

        self.horizontalLayout_root.addWidget(self.label_root)

        self.line_edit_root_path = QLineEdit(BatchFolderCreatorDialog)
        self.line_edit_root_path.setObjectName("line_edit_root_path")
        self.line_edit_root_path.setReadOnly(True)

        self.horizontalLayout_root.addWidget(self.line_edit_root_path)

        self.btn_browse_root = QPushButton(BatchFolderCreatorDialog)
        self.btn_browse_root.setObjectName("btn_browse_root")
        self.btn_browse_root.setMinimumSize(QSize(100, 0))

        self.horizontalLayout_root.addWidget(self.btn_browse_root)

        self.verticalLayout_main.addLayout(self.horizontalLayout_root)

        self.label_error = QLabel(BatchFolderCreatorDialog)
        self.label_error.setObjectName("label_error")
        self.label_error.setWordWrap(True)
        self.label_error.setStyleSheet(
            "color: red; padding: 5px; background-color: #fff3f3; border: 1px solid red;"
        )

        self.verticalLayout_main.addWidget(self.label_error)

        self.btn_fix_special_chars = QPushButton(BatchFolderCreatorDialog)
        self.btn_fix_special_chars.setObjectName("btn_fix_special_chars")
        self.btn_fix_special_chars.setEnabled(False)

        self.verticalLayout_main.addWidget(self.btn_fix_special_chars)

        self.horizontalLayout_content = QHBoxLayout()
        self.horizontalLayout_content.setObjectName("horizontalLayout_content")
        self.verticalLayout_left = QVBoxLayout()
        self.verticalLayout_left.setObjectName("verticalLayout_left")
        self.label_paste = QLabel(BatchFolderCreatorDialog)
        self.label_paste.setObjectName("label_paste")

        self.verticalLayout_left.addWidget(self.label_paste)

        self.table_paste = QTableWidget(BatchFolderCreatorDialog)
        self.table_paste.setObjectName("table_paste")
        self.table_paste.setAlternatingRowColors(True)
        self.table_paste.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self.table_paste.setColumnCount(3)
        self.table_paste.setRowCount(0)
        self.table_paste.setHorizontalHeaderLabels(["一级文件夹", "二级文件夹", "三级文件夹"])

        self.verticalLayout_left.addWidget(self.table_paste)

        self.horizontalLayout_content.addLayout(self.verticalLayout_left)

        self.verticalLayout_right = QVBoxLayout()
        self.verticalLayout_right.setObjectName("verticalLayout_right")
        self.label_preview = QLabel(BatchFolderCreatorDialog)
        self.label_preview.setObjectName("label_preview")

        self.verticalLayout_right.addWidget(self.label_preview)

        self.tree_preview = QTreeWidget(BatchFolderCreatorDialog)
        self.tree_preview.setObjectName("tree_preview")
        self.tree_preview.setAlternatingRowColors(True)
        self.tree_preview.setSelectionMode(QAbstractItemView.NoSelection)

        self.verticalLayout_right.addWidget(self.tree_preview)

        self.horizontalLayout_content.addLayout(self.verticalLayout_right)

        self.verticalLayout_main.addLayout(self.horizontalLayout_content)

        self.horizontalLayout_buttons = QHBoxLayout()
        self.horizontalLayout_buttons.setObjectName("horizontalLayout_buttons")
        self.btn_create_folders = QPushButton(BatchFolderCreatorDialog)
        self.btn_create_folders.setObjectName("btn_create_folders")
        self.btn_create_folders.setEnabled(False)

        self.horizontalLayout_buttons.addWidget(self.btn_create_folders)

        self.btn_open_root = QPushButton(BatchFolderCreatorDialog)
        self.btn_open_root.setObjectName("btn_open_root")
        self.btn_open_root.setEnabled(False)

        self.horizontalLayout_buttons.addWidget(self.btn_open_root)

        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_buttons.addItem(self.horizontalSpacer)

        self.btn_clear = QPushButton(BatchFolderCreatorDialog)
        self.btn_clear.setObjectName("btn_clear")

        self.horizontalLayout_buttons.addWidget(self.btn_clear)

        self.btn_cancel = QPushButton(BatchFolderCreatorDialog)
        self.btn_cancel.setObjectName("btn_cancel")

        self.horizontalLayout_buttons.addWidget(self.btn_cancel)

        self.verticalLayout_main.addLayout(self.horizontalLayout_buttons)

        self.retranslateUi(BatchFolderCreatorDialog)

        QMetaObject.connectSlotsByName(BatchFolderCreatorDialog)

    # setupUi

    def retranslateUi(self, BatchFolderCreatorDialog):
        BatchFolderCreatorDialog.setWindowTitle(
            QCoreApplication.translate(
                "BatchFolderCreatorDialog", "\u6279\u91cf\u521b\u5efa\u6587\u4ef6\u5939", None
            )
        )
        self.label_root.setText(
            QCoreApplication.translate("BatchFolderCreatorDialog", "\u6839\u76ee\u5f55\uff1a", None)
        )
        self.line_edit_root_path.setPlaceholderText(
            QCoreApplication.translate(
                "BatchFolderCreatorDialog", "\u8bf7\u9009\u62e9\u6839\u76ee\u5f55", None
            )
        )
        self.btn_browse_root.setText(
            QCoreApplication.translate("BatchFolderCreatorDialog", "\u6d4f\u89c8...", None)
        )
        self.label_error.setText("")
        self.btn_fix_special_chars.setText(
            QCoreApplication.translate(
                "BatchFolderCreatorDialog", "\u5904\u7406\u7279\u6b8a\u5b57\u7b26", None
            )
        )
        self.label_paste.setText(
            QCoreApplication.translate(
                "BatchFolderCreatorDialog",
                "\u4eceExcel\u7c98\u8d34\u6587\u4ef6\u5939\u7ed3\u6784\uff08\u5217\u4ee3\u8868\u5c42\u7ea7\uff09\uff1a",
                None,
            )
        )
        self.label_preview.setText(
            QCoreApplication.translate("BatchFolderCreatorDialog", "\u9884\u89c8\uff1a", None)
        )
        ___qtreewidgetitem = self.tree_preview.headerItem()
        ___qtreewidgetitem.setText(
            0,
            QCoreApplication.translate(
                "BatchFolderCreatorDialog", "\u6587\u4ef6\u5939\u7ed3\u6784", None
            ),
        )
        self.btn_create_folders.setText(
            QCoreApplication.translate(
                "BatchFolderCreatorDialog", "\u751f\u6210\u6587\u4ef6\u5939", None
            )
        )
        self.btn_open_root.setText(
            QCoreApplication.translate(
                "BatchFolderCreatorDialog", "\u6253\u5f00\u6839\u76ee\u5f55", None
            )
        )
        self.btn_clear.setText(
            QCoreApplication.translate("BatchFolderCreatorDialog", "\u6e05\u7a7a", None)
        )
        self.btn_cancel.setText(
            QCoreApplication.translate("BatchFolderCreatorDialog", "\u53d6\u6d88", None)
        )

    # retranslateUi
