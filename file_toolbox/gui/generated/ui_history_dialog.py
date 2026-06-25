################################################################################
## Form generated from reading UI file 'history_dialog.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QMetaObject,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class Ui_HistoryDialog:
    def setupUi(self, HistoryDialog):
        if not HistoryDialog.objectName():
            HistoryDialog.setObjectName("HistoryDialog")
        HistoryDialog.resize(700, 500)
        self.verticalLayout = QVBoxLayout(HistoryDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label = QLabel(HistoryDialog)
        self.label.setObjectName("label")

        self.verticalLayout.addWidget(self.label)

        self.table_history = QTableWidget(HistoryDialog)
        if self.table_history.columnCount() < 4:
            self.table_history.setColumnCount(4)
        __qtablewidgetitem = QTableWidgetItem()
        self.table_history.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.table_history.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.table_history.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.table_history.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        self.table_history.setObjectName("table_history")
        self.table_history.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_history.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_history.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.verticalLayout.addWidget(self.table_history)

        self.line = QFrame(HistoryDialog)
        self.line.setObjectName("line")
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout.addWidget(self.line)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.btn_clear_history = QPushButton(HistoryDialog)
        self.btn_clear_history.setObjectName("btn_clear_history")

        self.horizontalLayout.addWidget(self.btn_clear_history)

        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btn_undo = QPushButton(HistoryDialog)
        self.btn_undo.setObjectName("btn_undo")

        self.horizontalLayout.addWidget(self.btn_undo)

        self.btn_close = QPushButton(HistoryDialog)
        self.btn_close.setObjectName("btn_close")

        self.horizontalLayout.addWidget(self.btn_close)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.retranslateUi(HistoryDialog)

        QMetaObject.connectSlotsByName(HistoryDialog)

    # setupUi

    def retranslateUi(self, HistoryDialog):
        HistoryDialog.setWindowTitle(
            QCoreApplication.translate(
                "HistoryDialog", "\u91cd\u547d\u540d\u5386\u53f2\u8bb0\u5f55", None
            )
        )
        self.label.setText(
            QCoreApplication.translate(
                "HistoryDialog",
                "\u5386\u53f2\u8bb0\u5f55\u5217\u8868\uff08\u53cc\u51fb\u67e5\u770b\u8be6\u60c5\uff09\uff1a",
                None,
            )
        )
        ___qtablewidgetitem = self.table_history.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(
            QCoreApplication.translate("HistoryDialog", "\u65f6\u95f4", None)
        )
        ___qtablewidgetitem1 = self.table_history.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(
            QCoreApplication.translate("HistoryDialog", "\u6587\u4ef6\u6570\u91cf", None)
        )
        ___qtablewidgetitem2 = self.table_history.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(
            QCoreApplication.translate("HistoryDialog", "\u63cf\u8ff0", None)
        )
        ___qtablewidgetitem3 = self.table_history.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(
            QCoreApplication.translate("HistoryDialog", "\u72b6\u6001", None)
        )
        self.btn_clear_history.setText(
            QCoreApplication.translate("HistoryDialog", "\u6e05\u7a7a\u5386\u53f2", None)
        )
        self.btn_undo.setText(
            QCoreApplication.translate("HistoryDialog", "\u64a4\u9500\u9009\u4e2d", None)
        )
        self.btn_close.setText(QCoreApplication.translate("HistoryDialog", "\u5173\u95ed", None))

    # retranslateUi
