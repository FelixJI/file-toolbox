################################################################################
## Form generated from reading UI file 'operation_config_dialog.ui'
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
from PySide6.QtGui import (
    QFont,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


class Ui_OperationConfigDialog:
    def setupUi(self, OperationConfigDialog):
        if not OperationConfigDialog.objectName():
            OperationConfigDialog.setObjectName("OperationConfigDialog")
        OperationConfigDialog.resize(450, 400)
        self.verticalLayout = QVBoxLayout(OperationConfigDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label_title = QLabel(OperationConfigDialog)
        self.label_title.setObjectName("label_title")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.label_title.setFont(font)

        self.verticalLayout.addWidget(self.label_title)

        self.line = QFrame(OperationConfigDialog)
        self.line.setObjectName("line")
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout.addWidget(self.line)

        self.widget_config_container = QWidget(OperationConfigDialog)
        self.widget_config_container.setObjectName("widget_config_container")
        self.widget_config_container.setMinimumSize(QSize(0, 250))
        self.verticalLayout_container = QVBoxLayout(self.widget_config_container)
        self.verticalLayout_container.setObjectName("verticalLayout_container")
        self.verticalSpacer = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )

        self.verticalLayout_container.addItem(self.verticalSpacer)

        self.verticalLayout.addWidget(self.widget_config_container)

        self.line_2 = QFrame(OperationConfigDialog)
        self.line_2.setObjectName("line_2")
        self.line_2.setFrameShape(QFrame.Shape.HLine)
        self.line_2.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout.addWidget(self.line_2)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btn_cancel = QPushButton(OperationConfigDialog)
        self.btn_cancel.setObjectName("btn_cancel")

        self.horizontalLayout.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton(OperationConfigDialog)
        self.btn_ok.setObjectName("btn_ok")

        self.horizontalLayout.addWidget(self.btn_ok)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.retranslateUi(OperationConfigDialog)

        QMetaObject.connectSlotsByName(OperationConfigDialog)

    # setupUi

    def retranslateUi(self, OperationConfigDialog):
        OperationConfigDialog.setWindowTitle(
            QCoreApplication.translate("OperationConfigDialog", "\u64cd\u4f5c\u914d\u7f6e", None)
        )
        self.label_title.setText(
            QCoreApplication.translate("OperationConfigDialog", "\u914d\u7f6e\u64cd\u4f5c", None)
        )
        self.btn_cancel.setText(
            QCoreApplication.translate("OperationConfigDialog", "\u53d6\u6d88", None)
        )
        self.btn_ok.setText(
            QCoreApplication.translate("OperationConfigDialog", "\u786e\u5b9a", None)
        )

    # retranslateUi
