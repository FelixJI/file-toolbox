################################################################################
## Form generated from reading UI file 'ui_pdf_generator_dialog.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QMetaObject,
    QSize,
    Qt,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpacerItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class Ui_PDFGeneratorDialog:
    def setupUi(self, PDFGeneratorDialog):
        if not PDFGeneratorDialog.objectName():
            PDFGeneratorDialog.setObjectName("PDFGeneratorDialog")
        PDFGeneratorDialog.resize(900, 700)
        PDFGeneratorDialog.setMinimumSize(QSize(800, 600))
        self.mainLayout = QVBoxLayout(PDFGeneratorDialog)
        self.mainLayout.setSpacing(10)
        self.mainLayout.setObjectName("mainLayout")
        self.mainLayout.setContentsMargins(15, 15, 15, 15)
        self.group_files = QGroupBox(PDFGeneratorDialog)
        self.group_files.setObjectName("group_files")
        self.group_files.setMinimumSize(QSize(0, 180))
        self.filesLayout = QVBoxLayout(self.group_files)
        self.filesLayout.setObjectName("filesLayout")
        self.btnFileLayout = QHBoxLayout()
        self.btnFileLayout.setObjectName("btnFileLayout")
        self.btn_select_files = QPushButton(self.group_files)
        self.btn_select_files.setObjectName("btn_select_files")
        self.btn_select_files.setMinimumSize(QSize(100, 30))

        self.btnFileLayout.addWidget(self.btn_select_files)

        self.btn_select_folder = QPushButton(self.group_files)
        self.btn_select_folder.setObjectName("btn_select_folder")
        self.btn_select_folder.setMinimumSize(QSize(100, 30))

        self.btnFileLayout.addWidget(self.btn_select_folder)

        self.btn_clear_files = QPushButton(self.group_files)
        self.btn_clear_files.setObjectName("btn_clear_files")
        self.btn_clear_files.setMinimumSize(QSize(80, 30))

        self.btnFileLayout.addWidget(self.btn_clear_files)

        self.horizontalSpacer_files = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.btnFileLayout.addItem(self.horizontalSpacer_files)

        self.label_status = QLabel(self.group_files)
        self.label_status.setObjectName("label_status")
        self.label_status.setStyleSheet("color: #666;")

        self.btnFileLayout.addWidget(self.label_status)

        self.filesLayout.addLayout(self.btnFileLayout)

        self.table_files = QTableWidget(self.group_files)
        self.table_files.setObjectName("table_files")
        if self.table_files.columnCount() < 4:
            self.table_files.setColumnCount(4)
        __qtablewidgetitem_files0 = QTableWidgetItem()
        self.table_files.setHorizontalHeaderItem(0, __qtablewidgetitem_files0)
        __qtablewidgetitem_files1 = QTableWidgetItem()
        self.table_files.setHorizontalHeaderItem(1, __qtablewidgetitem_files1)
        __qtablewidgetitem_files2 = QTableWidgetItem()
        self.table_files.setHorizontalHeaderItem(2, __qtablewidgetitem_files2)
        __qtablewidgetitem_files3 = QTableWidgetItem()
        self.table_files.setHorizontalHeaderItem(3, __qtablewidgetitem_files3)
        self.table_files.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_files.setAlternatingRowColors(True)
        self.table_files.setAcceptDrops(True)
        self.table_files.setDragDropMode(QAbstractItemView.DropOnly)

        self.filesLayout.addWidget(self.table_files)

        self.mainLayout.addWidget(self.group_files, 1)

        self.group_settings = QGroupBox(PDFGeneratorDialog)
        self.group_settings.setObjectName("group_settings")
        self.settingsLayout = QVBoxLayout(self.group_settings)
        self.settingsLayout.setSpacing(12)
        self.settingsLayout.setObjectName("settingsLayout")
        self.typeLayout = QHBoxLayout()
        self.typeLayout.setObjectName("typeLayout")
        self.label_pdf_type = QLabel(self.group_settings)
        self.label_pdf_type.setObjectName("label_pdf_type")
        self.label_pdf_type.setMinimumSize(QSize(80, 0))

        self.typeLayout.addWidget(self.label_pdf_type)

        self.radio_type_editable = QRadioButton(self.group_settings)
        self.radio_type_editable.setObjectName("radio_type_editable")
        self.radio_type_editable.setChecked(True)

        self.typeLayout.addWidget(self.radio_type_editable)

        self.radio_type_image = QRadioButton(self.group_settings)
        self.radio_type_image.setObjectName("radio_type_image")

        self.typeLayout.addWidget(self.radio_type_image)

        self.horizontalSpacer_type1 = QSpacerItem(
            30, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )

        self.typeLayout.addItem(self.horizontalSpacer_type1)

        self.label_dpi = QLabel(self.group_settings)
        self.label_dpi.setObjectName("label_dpi")
        self.label_dpi.setEnabled(False)

        self.typeLayout.addWidget(self.label_dpi)

        self.combo_dpi = QComboBox(self.group_settings)
        self.combo_dpi.setObjectName("combo_dpi")
        self.combo_dpi.setEnabled(False)
        self.combo_dpi.setMinimumSize(QSize(100, 28))

        self.typeLayout.addWidget(self.combo_dpi)

        self.horizontalSpacer_type2 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.typeLayout.addItem(self.horizontalSpacer_type2)

        self.settingsLayout.addLayout(self.typeLayout)

        self.engineLayout = QHBoxLayout()
        self.engineLayout.setObjectName("engineLayout")
        self.label_engine = QLabel(self.group_settings)
        self.label_engine.setObjectName("label_engine")
        self.label_engine.setMinimumSize(QSize(80, 0))

        self.engineLayout.addWidget(self.label_engine)

        self.radio_engine_auto = QRadioButton(self.group_settings)
        self.radio_engine_auto.setObjectName("radio_engine_auto")
        self.radio_engine_auto.setChecked(True)

        self.engineLayout.addWidget(self.radio_engine_auto)

        self.radio_engine_office = QRadioButton(self.group_settings)
        self.radio_engine_office.setObjectName("radio_engine_office")

        self.engineLayout.addWidget(self.radio_engine_office)

        self.radio_engine_wps = QRadioButton(self.group_settings)
        self.radio_engine_wps.setObjectName("radio_engine_wps")

        self.engineLayout.addWidget(self.radio_engine_wps)

        self.label_engine_info = QLabel(self.group_settings)
        self.label_engine_info.setObjectName("label_engine_info")
        self.label_engine_info.setStyleSheet("color: #666; font-size: 11px;")

        self.engineLayout.addWidget(self.label_engine_info)

        self.horizontalSpacer_engine = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.engineLayout.addItem(self.horizontalSpacer_engine)

        self.settingsLayout.addLayout(self.engineLayout)

        self.paperLayout = QHBoxLayout()
        self.paperLayout.setObjectName("paperLayout")
        self.label_paper_size = QLabel(self.group_settings)
        self.label_paper_size.setObjectName("label_paper_size")
        self.label_paper_size.setMinimumSize(QSize(80, 0))

        self.paperLayout.addWidget(self.label_paper_size)

        self.combo_paper_size = QComboBox(self.group_settings)
        self.combo_paper_size.setObjectName("combo_paper_size")
        self.combo_paper_size.setMinimumSize(QSize(120, 28))

        self.paperLayout.addWidget(self.combo_paper_size)

        self.horizontalSpacer_paper1 = QSpacerItem(
            30, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )

        self.paperLayout.addItem(self.horizontalSpacer_paper1)

        self.label_orientation = QLabel(self.group_settings)
        self.label_orientation.setObjectName("label_orientation")
        self.label_orientation.setMinimumSize(QSize(80, 0))

        self.paperLayout.addWidget(self.label_orientation)

        self.combo_orientation = QComboBox(self.group_settings)
        self.combo_orientation.setObjectName("combo_orientation")
        self.combo_orientation.setMinimumSize(QSize(120, 28))

        self.paperLayout.addWidget(self.combo_orientation)

        self.label_scale = QLabel(self.group_settings)
        self.label_scale.setObjectName("label_scale")
        self.label_scale.setMinimumSize(QSize(80, 0))
        self.label_scale.setEnabled(False)

        self.paperLayout.addWidget(self.label_scale)

        self.combo_scale = QComboBox(self.group_settings)
        self.combo_scale.setObjectName("combo_scale")
        self.combo_scale.setEnabled(False)
        self.combo_scale.setMinimumSize(QSize(120, 28))

        self.paperLayout.addWidget(self.combo_scale)

        self.horizontalSpacer_paper2 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.paperLayout.addItem(self.horizontalSpacer_paper2)

        self.settingsLayout.addLayout(self.paperLayout)

        self.line1 = QFrame(self.group_settings)
        self.line1.setObjectName("line1")
        self.line1.setFrameShape(QFrame.HLine)
        self.line1.setFrameShadow(QFrame.Sunken)

        self.settingsLayout.addWidget(self.line1)

        self.outputModeLayout = QHBoxLayout()
        self.outputModeLayout.setObjectName("outputModeLayout")
        self.label_output_mode = QLabel(self.group_settings)
        self.label_output_mode.setObjectName("label_output_mode")
        self.label_output_mode.setMinimumSize(QSize(80, 0))

        self.outputModeLayout.addWidget(self.label_output_mode)

        self.radio_separate = QRadioButton(self.group_settings)
        self.radio_separate.setObjectName("radio_separate")
        self.radio_separate.setChecked(True)

        self.outputModeLayout.addWidget(self.radio_separate)

        self.radio_merge = QRadioButton(self.group_settings)
        self.radio_merge.setObjectName("radio_merge")

        self.outputModeLayout.addWidget(self.radio_merge)

        self.horizontalSpacer_output1 = QSpacerItem(
            20, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )

        self.outputModeLayout.addItem(self.horizontalSpacer_output1)

        self.label_merge_name = QLabel(self.group_settings)
        self.label_merge_name.setObjectName("label_merge_name")
        self.label_merge_name.setEnabled(False)

        self.outputModeLayout.addWidget(self.label_merge_name)

        self.edit_merge_filename = QLineEdit(self.group_settings)
        self.edit_merge_filename.setObjectName("edit_merge_filename")
        self.edit_merge_filename.setEnabled(False)
        self.edit_merge_filename.setMinimumSize(QSize(200, 28))

        self.outputModeLayout.addWidget(self.edit_merge_filename)

        self.horizontalSpacer_output2 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.outputModeLayout.addItem(self.horizontalSpacer_output2)

        self.settingsLayout.addLayout(self.outputModeLayout)

        self.printModeLayout = QHBoxLayout()
        self.printModeLayout.setObjectName("printModeLayout")
        self.label_print_mode = QLabel(self.group_settings)
        self.label_print_mode.setObjectName("label_print_mode")
        self.label_print_mode.setEnabled(False)
        self.label_print_mode.setMinimumSize(QSize(80, 0))

        self.printModeLayout.addWidget(self.label_print_mode)

        self.radio_print_single = QRadioButton(self.group_settings)
        self.radio_print_single.setObjectName("radio_print_single")
        self.radio_print_single.setEnabled(False)
        self.radio_print_single.setChecked(True)

        self.printModeLayout.addWidget(self.radio_print_single)

        self.radio_print_duplex = QRadioButton(self.group_settings)
        self.radio_print_duplex.setObjectName("radio_print_duplex")
        self.radio_print_duplex.setEnabled(False)

        self.printModeLayout.addWidget(self.radio_print_duplex)

        self.label_print_hint = QLabel(self.group_settings)
        self.label_print_hint.setObjectName("label_print_hint")
        self.label_print_hint.setEnabled(False)
        self.label_print_hint.setStyleSheet("color: #888; font-size: 11px;")

        self.printModeLayout.addWidget(self.label_print_hint)

        self.horizontalSpacer_print = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.printModeLayout.addItem(self.horizontalSpacer_print)

        self.settingsLayout.addLayout(self.printModeLayout)

        self.outputDirLayout = QHBoxLayout()
        self.outputDirLayout.setObjectName("outputDirLayout")
        self.label_output_dir = QLabel(self.group_settings)
        self.label_output_dir.setObjectName("label_output_dir")
        self.label_output_dir.setMinimumSize(QSize(80, 0))

        self.outputDirLayout.addWidget(self.label_output_dir)

        self.radio_same_dir = QRadioButton(self.group_settings)
        self.radio_same_dir.setObjectName("radio_same_dir")
        self.radio_same_dir.setChecked(True)

        self.outputDirLayout.addWidget(self.radio_same_dir)

        self.radio_custom_dir = QRadioButton(self.group_settings)
        self.radio_custom_dir.setObjectName("radio_custom_dir")

        self.outputDirLayout.addWidget(self.radio_custom_dir)

        self.edit_output_dir = QLineEdit(self.group_settings)
        self.edit_output_dir.setObjectName("edit_output_dir")
        self.edit_output_dir.setEnabled(False)
        self.edit_output_dir.setMinimumSize(QSize(250, 28))
        self.edit_output_dir.setReadOnly(True)

        self.outputDirLayout.addWidget(self.edit_output_dir)

        self.btn_browse_dir = QPushButton(self.group_settings)
        self.btn_browse_dir.setObjectName("btn_browse_dir")
        self.btn_browse_dir.setEnabled(False)
        self.btn_browse_dir.setMinimumSize(QSize(60, 28))

        self.outputDirLayout.addWidget(self.btn_browse_dir)

        self.horizontalSpacer_dir = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.outputDirLayout.addItem(self.horizontalSpacer_dir)

        self.settingsLayout.addLayout(self.outputDirLayout)

        self.mainLayout.addWidget(self.group_settings)

        self.progressLayout = QHBoxLayout()
        self.progressLayout.setObjectName("progressLayout")
        self.progress_bar = QProgressBar(PDFGeneratorDialog)
        self.progress_bar.setObjectName("progress_bar")
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumSize(QSize(0, 25))

        self.progressLayout.addWidget(self.progress_bar)

        self.label_progress = QLabel(PDFGeneratorDialog)
        self.label_progress.setObjectName("label_progress")
        self.label_progress.setMinimumSize(QSize(80, 0))
        self.label_progress.setAlignment(Qt.AlignRight | Qt.AlignTrailing | Qt.AlignVCenter)

        self.progressLayout.addWidget(self.label_progress)

        self.mainLayout.addLayout(self.progressLayout)

        self.btnLayout = QHBoxLayout()
        self.btnLayout.setObjectName("btnLayout")
        self.horizontalSpacer_btn = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.btnLayout.addItem(self.horizontalSpacer_btn)

        self.btn_refresh = QPushButton(PDFGeneratorDialog)
        self.btn_refresh.setObjectName("btn_refresh")
        self.btn_refresh.setMinimumSize(QSize(100, 35))

        self.btnLayout.addWidget(self.btn_refresh)

        self.btn_generate = QPushButton(PDFGeneratorDialog)
        self.btn_generate.setObjectName("btn_generate")
        self.btn_generate.setMinimumSize(QSize(100, 35))
        self.btn_generate.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }\n"
            "QPushButton:hover { background-color: #45a049; }\n"
            "QPushButton:disabled { background-color: #cccccc; }"
        )

        self.btnLayout.addWidget(self.btn_generate)

        self.btn_cancel = QPushButton(PDFGeneratorDialog)
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setMinimumSize(QSize(80, 35))

        self.btnLayout.addWidget(self.btn_cancel)

        self.mainLayout.addLayout(self.btnLayout)

        self.retranslateUi(PDFGeneratorDialog)
        self.radio_type_image.toggled.connect(self.label_dpi.setEnabled)
        self.radio_type_image.toggled.connect(self.combo_dpi.setEnabled)
        self.radio_type_image.toggled.connect(self.label_scale.setEnabled)
        self.radio_type_image.toggled.connect(self.combo_scale.setEnabled)
        self.radio_merge.toggled.connect(self.label_merge_name.setEnabled)
        self.radio_merge.toggled.connect(self.edit_merge_filename.setEnabled)
        self.radio_merge.toggled.connect(self.label_print_mode.setEnabled)
        self.radio_merge.toggled.connect(self.radio_print_single.setEnabled)
        self.radio_merge.toggled.connect(self.radio_print_duplex.setEnabled)
        self.radio_merge.toggled.connect(self.label_print_hint.setEnabled)
        self.radio_custom_dir.toggled.connect(self.edit_output_dir.setEnabled)
        self.radio_custom_dir.toggled.connect(self.btn_browse_dir.setEnabled)

        QMetaObject.connectSlotsByName(PDFGeneratorDialog)

    # setupUi

    def retranslateUi(self, PDFGeneratorDialog):
        PDFGeneratorDialog.setWindowTitle(
            QCoreApplication.translate("PDFGeneratorDialog", "\u6279\u91cf\u751f\u6210PDF", None)
        )
        self.group_files.setTitle(
            QCoreApplication.translate("PDFGeneratorDialog", "\u6587\u4ef6\u9009\u62e9", None)
        )
        self.btn_select_files.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u9009\u62e9\u6587\u4ef6", None)
        )
        self.btn_select_folder.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u9009\u62e9\u6587\u4ef6\u5939", None)
        )
        self.btn_clear_files.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u6e05\u7a7a", None)
        )
        self.label_status.setText(
            QCoreApplication.translate(
                "PDFGeneratorDialog", "\u5df2\u9009\u62e9 0 \u4e2a\u6587\u4ef6", None
            )
        )
        self.group_settings.setTitle(
            QCoreApplication.translate("PDFGeneratorDialog", "PDF\u8bbe\u7f6e", None)
        )
        self.label_pdf_type.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "PDF\u7c7b\u578b:", None)
        )
        self.radio_type_editable.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u53ef\u7f16\u8f91\u578b", None)
        )
        self.radio_type_image.setText(
            QCoreApplication.translate(
                "PDFGeneratorDialog", "\u56fe\u7247\u578b(\u4e0d\u53ef\u7f16\u8f91)", None
            )
        )
        self.label_dpi.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u6e05\u6670\u5ea6:", None)
        )
        self.label_engine.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u8f6c\u6362\u5f15\u64ce:", None)
        )
        self.radio_engine_auto.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u81ea\u52a8\u9009\u62e9", None)
        )
        self.radio_engine_office.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "MS Office", None)
        )
        self.radio_engine_wps.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "WPS Office", None)
        )
        self.label_engine_info.setText("")
        self.label_paper_size.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u7eb8\u5f20\u5927\u5c0f:", None)
        )
        self.label_orientation.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u7eb8\u5f20\u65b9\u5411:", None)
        )
        self.label_scale.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u7f29\u653e:", None)
        )
        self.label_output_mode.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u8f93\u51fa\u6a21\u5f0f:", None)
        )
        self.radio_separate.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u5404\u81ea\u751f\u6210PDF", None)
        )
        self.radio_merge.setText(
            QCoreApplication.translate(
                "PDFGeneratorDialog", "\u5408\u5e76\u4e3a\u4e00\u4e2aPDF", None
            )
        )
        self.label_merge_name.setText(
            QCoreApplication.translate(
                "PDFGeneratorDialog", "\u5408\u5e76\u6587\u4ef6\u540d:", None
            )
        )
        self.edit_merge_filename.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u5408\u5e76\u6587\u6863.pdf", None)
        )
        self.edit_merge_filename.setPlaceholderText(
            QCoreApplication.translate(
                "PDFGeneratorDialog", "\u8f93\u5165\u5408\u5e76\u540e\u7684\u6587\u4ef6\u540d", None
            )
        )
        self.label_print_mode.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u6253\u5370\u6a21\u5f0f:", None)
        )
        self.radio_print_single.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u5355\u9762\u6253\u5370", None)
        )
        self.radio_print_duplex.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u53cc\u9762\u6253\u5370", None)
        )
        self.label_print_hint.setText(
            QCoreApplication.translate(
                "PDFGeneratorDialog",
                "(\u53cc\u9762\u6a21\u5f0f\u4f1a\u4e3a\u5947\u6570\u9875\u6587\u6863\u81ea\u52a8\u6dfb\u52a0\u7a7a\u767d\u9875)",
                None,
            )
        )
        self.label_output_dir.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u8f93\u51fa\u76ee\u5f55:", None)
        )
        self.radio_same_dir.setText(
            QCoreApplication.translate(
                "PDFGeneratorDialog", "\u4e0e\u6e90\u6587\u4ef6\u76f8\u540c", None
            )
        )
        self.radio_custom_dir.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u6307\u5b9a\u76ee\u5f55", None)
        )
        self.btn_browse_dir.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u6d4f\u89c8", None)
        )
        ___qtablewidgetitem = self.table_files.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u6e90\u6587\u4ef6", None)
        )
        ___qtablewidgetitem1 = self.table_files.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u8f93\u51fa", None)
        )
        ___qtablewidgetitem2 = self.table_files.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u5927\u5c0f", None)
        )
        ___qtablewidgetitem3 = self.table_files.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u72b6\u6001", None)
        )
        self.label_progress.setText(QCoreApplication.translate("PDFGeneratorDialog", "0%", None))
        self.btn_refresh.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u5237\u65b0\u9884\u89c8", None)
        )
        self.btn_generate.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u5f00\u59cb\u751f\u6210", None)
        )
        self.btn_cancel.setText(
            QCoreApplication.translate("PDFGeneratorDialog", "\u53d6\u6d88", None)
        )

    # retranslateUi
