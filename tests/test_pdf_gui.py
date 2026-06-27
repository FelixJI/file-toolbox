"""PDF Tab GUI 测试:下拉框填充、单选按钮互斥分组、配置构建。

不触发真实 COM/文件操作,仅校验控件状态与逻辑。
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from file_toolbox.core.batch_pdf.constants import (  # noqa: E402
    DPI_DEFAULT,
    OUTPUT_SEPARATE,
    PDF_TYPE_EDITABLE,
)
from file_toolbox.gui.dialogs.pdf_tab import PDFGeneratorDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dlg(app):
    return PDFGeneratorDialog()


# ---------- 下拉框填充 ----------


def test_dpi_combo_populated(dlg):
    items = [dlg.ui.combo_dpi.itemText(i) for i in range(dlg.ui.combo_dpi.count())]
    assert items == ["150", "300", "600"]
    assert dlg.ui.combo_dpi.currentText() == str(DPI_DEFAULT)


def test_paper_size_combo_contains_auto_and_a4(dlg):
    items = [dlg.ui.combo_paper_size.itemText(i) for i in range(dlg.ui.combo_paper_size.count())]
    assert "自动" in items
    assert "A4" in items
    assert dlg.ui.combo_paper_size.currentText() == "自动"


def test_orientation_combo_has_options(dlg):
    items = [dlg.ui.combo_orientation.itemText(i) for i in range(dlg.ui.combo_orientation.count())]
    assert set(items) == {"自动", "纵向", "横向"}
    assert dlg.ui.combo_orientation.currentText() == "自动"


def test_scale_combo_populated(dlg):
    assert dlg.ui.combo_scale.count() == 3
    # userData 应为常量值字符串
    data = [dlg.ui.combo_scale.itemData(i) for i in range(dlg.ui.combo_scale.count())]
    assert "shrink_oversized" in data


# ---------- 单选按钮分组互斥 ----------


def test_button_groups_have_correct_sizes(dlg):
    assert len(dlg._type_group.buttons()) == 2
    assert len(dlg._engine_group.buttons()) == 3
    assert len(dlg._output_group.buttons()) == 2
    assert len(dlg._dir_group.buttons()) == 2
    assert len(dlg._print_group.buttons()) == 2


def test_selecting_image_type_does_not_clear_other_groups(dlg):
    """选图片型不应影响输出模式/输出目录等无关选项。"""
    dlg.ui.radio_merge.setChecked(True)
    dlg.ui.radio_custom_dir.setChecked(True)
    dlg.ui.radio_engine_office.setChecked(True)

    dlg.ui.radio_type_image.setChecked(True)

    assert dlg.ui.radio_type_image.isChecked()
    assert dlg.ui.radio_type_editable.isChecked() is False
    # 其它组选中状态保持不变
    assert dlg.ui.radio_merge.isChecked()
    assert dlg.ui.radio_custom_dir.isChecked()
    assert dlg.ui.radio_engine_office.isChecked()


def test_selecting_wps_engine_does_not_clear_type_or_merge(dlg):
    dlg.ui.radio_type_image.setChecked(True)
    dlg.ui.radio_merge.setChecked(True)

    dlg.ui.radio_engine_wps.setChecked(True)

    assert dlg.ui.radio_engine_wps.isChecked()
    assert dlg.ui.radio_type_image.isChecked()
    assert dlg.ui.radio_merge.isChecked()


# ---------- 配置构建 ----------


def test_build_config_defaults(dlg):
    config = dlg._build_config()
    assert config["pdf_type"] == PDF_TYPE_EDITABLE
    assert config["output_mode"] == OUTPUT_SEPARATE
    assert config["same_as_source"] is True
    assert config["dpi"] == DPI_DEFAULT
    assert config["paper_size"] == "auto"
    assert config["orientation"] == "auto"
    assert "output_dir" not in config


def test_build_config_paper_size_maps_auto(dlg):
    dlg.ui.combo_paper_size.setCurrentText("A4")
    assert dlg._build_config()["paper_size"] == "A4"
    dlg.ui.combo_paper_size.setCurrentText("自动")
    assert dlg._build_config()["paper_size"] == "auto"


def test_build_config_custom_dir_includes_output_dir(dlg):
    dlg.ui.radio_custom_dir.setChecked(True)
    dlg.ui.edit_output_dir.setText("/tmp/out")
    config = dlg._build_config()
    assert config["same_as_source"] is False
    assert "output_dir" in config
