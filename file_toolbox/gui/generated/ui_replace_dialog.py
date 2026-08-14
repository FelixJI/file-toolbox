################################################################################
## 手维护的 UI 构建代码(无 .ui 源文件)。
##
## 本文件由人工维护,PySide6 控件树在 Ui_ContentReplaceDialog.setupUi 里手写构建。
## 仓库内目前没有对应的 content_replace_dialog.ui;日后若用 Qt Designer 产出
## .ui 并接入 scripts/regen_ui.py 的再生链路,本文件会被 pyside6-uic 覆盖。
##
## 详见 scripts/regen_ui.py(HANDMADE 清单)与 .superpowers/sdd/task-6-report.md。
################################################################################


from PySide6.QtCore import (
    QCoreApplication,
    QMetaObject,
    QSize,
    Qt,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class Ui_ContentReplaceDialog:
    def setupUi(self, ContentReplaceDialog):

        if not ContentReplaceDialog.objectName():
            ContentReplaceDialog.setObjectName("ContentReplaceDialog")

        ContentReplaceDialog.resize(900, 700)

        self.verticalLayout = QVBoxLayout(ContentReplaceDialog)

        self.verticalLayout.setObjectName("verticalLayout")

        self.splitter = QSplitter(ContentReplaceDialog)

        self.splitter.setObjectName("splitter")

        self.splitter.setOrientation(Qt.Orientation.Horizontal)

        self.groupBox_files = QGroupBox(self.splitter)

        self.groupBox_files.setObjectName("groupBox_files")

        self.groupBox_files.setMinimumSize(QSize(300, 0))

        self.verticalLayout_2 = QVBoxLayout(self.groupBox_files)

        self.verticalLayout_2.setObjectName("verticalLayout_2")

        self.list_files = QListWidget(self.groupBox_files)

        self.list_files.setObjectName("list_files")

        self.list_files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        self.verticalLayout_2.addWidget(self.list_files)

        self.horizontalLayout_files = QHBoxLayout()

        self.horizontalLayout_files.setObjectName("horizontalLayout_files")

        self.btn_select_files = QPushButton(self.groupBox_files)

        self.btn_select_files.setObjectName("btn_select_files")

        self.horizontalLayout_files.addWidget(self.btn_select_files)

        self.btn_select_folder = QPushButton(self.groupBox_files)

        self.btn_select_folder.setObjectName("btn_select_folder")

        self.horizontalLayout_files.addWidget(self.btn_select_folder)

        self.btn_clear_files = QPushButton(self.groupBox_files)

        self.btn_clear_files.setObjectName("btn_clear_files")

        self.horizontalLayout_files.addWidget(self.btn_clear_files)

        self.verticalLayout_2.addLayout(self.horizontalLayout_files)

        self.label_file_filter = QLabel(self.groupBox_files)

        self.label_file_filter.setObjectName("label_file_filter")

        self.verticalLayout_2.addWidget(self.label_file_filter)

        self.splitter.addWidget(self.groupBox_files)

        self.groupBox_operations = QGroupBox(self.splitter)

        self.groupBox_operations.setObjectName("groupBox_operations")

        self.groupBox_operations.setMinimumSize(QSize(280, 0))

        self.verticalLayout_3 = QVBoxLayout(self.groupBox_operations)

        self.verticalLayout_3.setObjectName("verticalLayout_3")

        self.list_operations = QListWidget(self.groupBox_operations)

        self.list_operations.setObjectName("list_operations")

        self.list_operations.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        self.verticalLayout_3.addWidget(self.list_operations)

        self.horizontalLayout_ops = QHBoxLayout()

        self.horizontalLayout_ops.setObjectName("horizontalLayout_ops")

        self.btn_simple_replace = QPushButton(self.groupBox_operations)

        self.btn_simple_replace.setObjectName("btn_simple_replace")

        self.horizontalLayout_ops.addWidget(self.btn_simple_replace)

        self.btn_regex_replace = QPushButton(self.groupBox_operations)

        self.btn_regex_replace.setObjectName("btn_regex_replace")

        self.horizontalLayout_ops.addWidget(self.btn_regex_replace)

        self.verticalLayout_3.addLayout(self.horizontalLayout_ops)

        self.horizontalLayout_ops2 = QHBoxLayout()

        self.horizontalLayout_ops2.setObjectName("horizontalLayout_ops2")

        self.btn_edit_operation = QPushButton(self.groupBox_operations)

        self.btn_edit_operation.setObjectName("btn_edit_operation")

        self.horizontalLayout_ops2.addWidget(self.btn_edit_operation)

        self.btn_remove_operation = QPushButton(self.groupBox_operations)

        self.btn_remove_operation.setObjectName("btn_remove_operation")

        self.horizontalLayout_ops2.addWidget(self.btn_remove_operation)

        self.verticalLayout_3.addLayout(self.horizontalLayout_ops2)

        self.chk_keep_new_format = QCheckBox(self.groupBox_operations)

        self.chk_keep_new_format.setObjectName("chk_keep_new_format")

        self.chk_keep_new_format.setChecked(False)

        self.verticalLayout_3.addWidget(self.chk_keep_new_format)

        self.splitter.addWidget(self.groupBox_operations)

        self.verticalLayout.addWidget(self.splitter)

        self.groupBox_preview = QGroupBox(ContentReplaceDialog)

        self.groupBox_preview.setObjectName("groupBox_preview")

        self.verticalLayout_4 = QVBoxLayout(self.groupBox_preview)

        self.verticalLayout_4.setObjectName("verticalLayout_4")

        self.table_preview = QTableWidget(self.groupBox_preview)

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

        self.table_preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.table_preview.setAlternatingRowColors(True)

        self.table_preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.verticalLayout_4.addWidget(self.table_preview)

        self.verticalLayout.addWidget(self.groupBox_preview)

        self.frame_status = QFrame(ContentReplaceDialog)

        self.frame_status.setObjectName("frame_status")

        self.frame_status.setFrameShape(QFrame.Shape.StyledPanel)

        self.horizontalLayout_status = QHBoxLayout(self.frame_status)

        self.horizontalLayout_status.setObjectName("horizontalLayout_status")

        self.label_status = QLabel(self.frame_status)

        self.label_status.setObjectName("label_status")

        self.horizontalLayout_status.addWidget(self.label_status)

        self.progress_bar = QProgressBar(self.frame_status)

        self.progress_bar.setObjectName("progress_bar")

        self.progress_bar.setValue(0)

        self.progress_bar.setVisible(False)

        self.horizontalLayout_status.addWidget(self.progress_bar)

        self.verticalLayout.addWidget(self.frame_status)

        self.line = QFrame(ContentReplaceDialog)

        self.line.setObjectName("line")

        self.line.setFrameShape(QFrame.Shape.HLine)

        self.line.setFrameShadow(QFrame.Shadow.Sunken)

        self.verticalLayout.addWidget(self.line)

        self.horizontalLayout_buttons = QHBoxLayout()

        self.horizontalLayout_buttons.setObjectName("horizontalLayout_buttons")

        self.btn_refresh_preview = QPushButton(ContentReplaceDialog)

        self.btn_refresh_preview.setObjectName("btn_refresh_preview")

        self.horizontalLayout_buttons.addWidget(self.btn_refresh_preview)

        self.btn_show_history = QPushButton(ContentReplaceDialog)

        self.btn_show_history.setObjectName("btn_show_history")

        self.horizontalLayout_buttons.addWidget(self.btn_show_history)

        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_buttons.addItem(self.horizontalSpacer)

        self.btn_cancel = QPushButton(ContentReplaceDialog)

        self.btn_cancel.setObjectName("btn_cancel")

        self.horizontalLayout_buttons.addWidget(self.btn_cancel)

        self.btn_execute = QPushButton(ContentReplaceDialog)

        self.btn_execute.setObjectName("btn_execute")

        self.horizontalLayout_buttons.addWidget(self.btn_execute)

        self.verticalLayout.addLayout(self.horizontalLayout_buttons)

        self.retranslateUi(ContentReplaceDialog)

        QMetaObject.connectSlotsByName(ContentReplaceDialog)

    # setupUi

    def retranslateUi(self, ContentReplaceDialog):

        ContentReplaceDialog.setWindowTitle(
            QCoreApplication.translate(
                "ContentReplaceDialog", "\u6279\u91cf\u6587\u6863\u5185\u5bb9\u66ff\u6362", None
            )
        )

        self.groupBox_files.setTitle(
            QCoreApplication.translate("ContentReplaceDialog", "\u6587\u4ef6\u5217\u8868", None)
        )

        self.btn_select_files.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u9009\u62e9\u6587\u4ef6", None)
        )

        self.btn_select_folder.setText(
            QCoreApplication.translate(
                "ContentReplaceDialog", "\u9009\u62e9\u6587\u4ef6\u5939", None
            )
        )

        self.btn_clear_files.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u6e05\u7a7a", None)
        )

        self.label_file_filter.setText(
            QCoreApplication.translate(
                "ContentReplaceDialog",
                "\u652f\u6301\u683c\u5f0f: docx, doc, xlsx, xls, txt, md",
                None,
            )
        )

        self.label_file_filter.setStyleSheet(
            QCoreApplication.translate(
                "ContentReplaceDialog", "color: gray; font-size: 11px;", None
            )
        )

        self.groupBox_operations.setTitle(
            QCoreApplication.translate("ContentReplaceDialog", "\u66ff\u6362\u64cd\u4f5c", None)
        )

        self.btn_simple_replace.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u7b80\u5355\u66ff\u6362", None)
        )

        self.btn_regex_replace.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u6b63\u5219\u66ff\u6362", None)
        )

        self.btn_edit_operation.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u7f16\u8f91", None)
        )

        self.btn_remove_operation.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u5220\u9664", None)
        )

        self.groupBox_preview.setTitle(
            QCoreApplication.translate("ContentReplaceDialog", "\u9884\u89c8", None)
        )

        ___qtablewidgetitem = self.table_preview.horizontalHeaderItem(0)

        ___qtablewidgetitem.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u6587\u4ef6\u540d", None)
        )

        ___qtablewidgetitem1 = self.table_preview.horizontalHeaderItem(1)

        ___qtablewidgetitem1.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u5339\u914d\u6570", None)
        )

        ___qtablewidgetitem2 = self.table_preview.horizontalHeaderItem(2)

        ___qtablewidgetitem2.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u6587\u4ef6\u5927\u5c0f", None)
        )

        ___qtablewidgetitem3 = self.table_preview.horizontalHeaderItem(3)

        ___qtablewidgetitem3.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u683c\u5f0f\u8f6c\u6362", None)
        )

        ___qtablewidgetitem4 = self.table_preview.horizontalHeaderItem(4)

        ___qtablewidgetitem4.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u72b6\u6001", None)
        )

        self.chk_keep_new_format.setText(
            QCoreApplication.translate("ContentReplaceDialog", "转换后保留新格式", None)
        )
        self.chk_keep_new_format.setToolTip(
            QCoreApplication.translate(
                "ContentReplaceDialog", "doc→docx、xls→xlsx 等旧格式转换后保留为新格式", None
            )
        )

        self.label_status.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u5c31\u7eea", None)
        )

        self.btn_refresh_preview.setText(
            QCoreApplication.translate("ContentReplaceDialog", "刷新预览", None)
        )

        self.btn_show_history.setText(
            QCoreApplication.translate("ContentReplaceDialog", "历史记录", None)
        )

        self.btn_cancel.setText(
            QCoreApplication.translate("ContentReplaceDialog", "\u53d6\u6d88", None)
        )

        self.btn_execute.setText(
            QCoreApplication.translate("ContentReplaceDialog", "执行替换", None)
        )

        self.btn_execute.setStyleSheet(
            QCoreApplication.translate(
                "ContentReplaceDialog",
                "background-color: #4CAF50; color: white; font-weight: bold;",
                None,
            )
        )

    # retranslateUi
