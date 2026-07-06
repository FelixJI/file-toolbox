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


# ---------- 布局:文件选择与预览合并 ----------


def test_no_separate_list_files_widget(dlg):
    """list_files(QListWidget)已删除。"""
    assert not hasattr(dlg.ui, "list_files")


def test_no_separate_preview_group(dlg):
    """group_preview 已删除(预览并入 group_files)。"""
    assert not hasattr(dlg.ui, "group_preview")


def test_table_files_exists_with_four_columns(dlg):
    """table_files(QTableWidget)存在,4 列。"""
    assert hasattr(dlg.ui, "table_files")
    assert dlg.ui.table_files.columnCount() == 4
    headers = [
        dlg.ui.table_files.horizontalHeaderItem(i).text() for i in range(4)
    ]
    assert headers == ["源文件", "输出", "大小", "状态"]


def test_table_files_supports_dnd_and_multiselect(dlg):
    """table_files 继承原 list_files 的拖拽接收 + 多选能力。"""
    from PySide6.QtWidgets import QAbstractItemView

    tbl = dlg.ui.table_files
    assert tbl.acceptDrops() is True
    assert tbl.dragDropMode() == QAbstractItemView.DropOnly
    assert tbl.selectionMode() == QAbstractItemView.ExtendedSelection


def test_table_files_in_group_files(dlg):
    """table_files 是 group_files 的子控件(合并后)。"""
    assert dlg.ui.table_files.parent() is dlg.ui.group_files


# ---------- 预览:选文件后填表 ----------


def test_do_refresh_preview_populates_table(dlg, tmp_path):
    """selected_files 非空 → _do_refresh_preview 填 4 列,状态=待转换。"""
    from pathlib import Path

    f1 = tmp_path / "a.docx"
    f1.write_bytes(b"x" * 1234)
    f2 = tmp_path / "b.xlsx"
    f2.write_bytes(b"y" * 5678)
    dlg.selected_files = [f1, f2]

    dlg._do_refresh_preview()

    tbl = dlg.ui.table_files
    assert tbl.rowCount() == 2
    assert tbl.item(0, 0).text() == "a.docx"
    assert tbl.item(0, 1).text() == "a.pdf"  # 分离模式预期输出
    assert tbl.item(0, 3).text() == "待转换"
    assert tbl.item(1, 0).text() == "b.xlsx"
    assert tbl.item(1, 1).text() == "b.pdf"


def test_do_refresh_preview_merge_mode_uses_merge_filename(dlg, tmp_path):
    """合并模式 → 输出列填合并文件名。"""
    from pathlib import Path

    f1 = tmp_path / "a.docx"
    f1.write_bytes(b"x")
    dlg.selected_files = [f1]
    dlg.ui.radio_merge.setChecked(True)

    dlg._do_refresh_preview()

    assert dlg.ui.table_files.item(0, 1).text() == "合并文档.pdf"


def test_do_refresh_preview_empty_files_clears_table(dlg):
    """selected_files 空 → 表清空。"""
    dlg.ui.table_files.setRowCount(3)  # 预置一些行
    dlg.selected_files = []

    dlg._do_refresh_preview()

    assert dlg.ui.table_files.rowCount() == 0


def test_do_refresh_preview_missing_file_size_blank(dlg, tmp_path):
    """文件不存在 → 大小列空(不崩)。"""
    from pathlib import Path

    dlg.selected_files = [tmp_path / "no_such.docx"]
    dlg._do_refresh_preview()  # 不应抛
    assert dlg.ui.table_files.item(0, 2).text() == ""


def test_clear_files_resets_table(dlg, tmp_path):
    """_on_clear_files 清空 selected_files 与表。"""
    from pathlib import Path

    f = tmp_path / "a.docx"
    f.write_bytes(b"x")
    dlg.selected_files = [f]
    dlg._do_refresh_preview()
    assert dlg.ui.table_files.rowCount() == 1

    dlg._on_clear_files()

    assert dlg.selected_files == []
    assert dlg.ui.table_files.rowCount() == 0


# ---------- 生成:worker 接入 ----------


def test_generate_with_no_files_shows_message(dlg, monkeypatch):
    """无文件 → 弹提示,不启动 worker。"""
    called = []
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.pdf_tab.QMessageBox.information",
        lambda *a, **k: called.append(True),
    )
    dlg.selected_files = []
    dlg._generate()
    assert called  # 弹了提示


def test_generate_starts_worker_and_disables_ui(dlg, monkeypatch, tmp_path):
    """有文件 → 创建 worker、start、UI 禁用、cancel 按钮显示。"""
    from pathlib import Path

    from file_toolbox.gui.workers.pdf_worker import PdfGenerateWorker

    f = tmp_path / "a.docx"
    f.write_bytes(b"x")
    dlg.selected_files = [f]

    started = []

    # 用真 PdfGenerateWorker 但 mock start 避免真起线程
    def fake_start(self):
        started.append(True)

    monkeypatch.setattr(PdfGenerateWorker, "start", fake_start)

    dlg._generate()

    assert started  # 启动了
    assert dlg.worker is not None
    assert isinstance(dlg.worker, PdfGenerateWorker)
    assert dlg.ui.btn_generate.isEnabled() is False  # UI 禁用
    # 对话框未 show 时 isVisible() 恒为 False;isHidden() 反映 setVisible 的真实意图
    assert dlg.ui.btn_cancel.isHidden() is False  # 已设为可见(取消按钮亮起)


def test_on_progress_updates_label_and_bar(dlg):
    """_on_progress 更新 label_progress 与 progress_bar。"""
    dlg._on_progress(2, 5, "处理中")
    assert "2/5" in dlg.ui.label_progress.text()
    assert dlg.ui.progress_bar.value() == 40  # 2/5


def test_on_generate_ok_renders_results_and_restores_ui(dlg, tmp_path, monkeypatch):
    """_on_generate_ok 填结果态 + 恢复 UI。"""
    from pathlib import Path

    # fail>0 时 _on_generate_ok 会弹 QMessageBox.warning,无事件循环会挂 → 打桩
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.pdf_tab.QMessageBox.warning",
        lambda *a, **k: None,
    )

    results = [
        {"source": Path("a.docx"), "output": Path("a.pdf"), "success": True, "error": ""},
        {"source": Path("b.docx"), "output": Path("b.pdf"), "success": False, "error": "boom"},
    ]
    # 真实流程中 _generate 前 _do_refresh_preview 已填好预览行,这里同构预置
    dlg.selected_files = [Path("a.docx"), Path("b.docx")]
    dlg._do_refresh_preview()
    # 预置 UI 禁用态
    dlg.ui.btn_generate.setEnabled(False)
    dlg.ui.btn_cancel.setVisible(True)

    dlg._on_generate_ok(results)

    tbl = dlg.ui.table_files
    assert tbl.rowCount() == 2
    assert tbl.item(0, 3).text() == "成功"
    assert tbl.item(1, 3).text() == "失败: boom"
    assert dlg.ui.btn_generate.isEnabled() is True  # 恢复
    # 对话框未 show,用 isHidden() 反映 setVisible(False) 的真实意图
    assert dlg.ui.btn_cancel.isHidden() is True  # 取消按钮隐藏


def test_on_generate_failed_restores_ui(dlg, monkeypatch):
    """_on_generate_failed 恢复 UI。"""
    # _on_generate_failed 会弹 QMessageBox.critical,无事件循环会挂 → 打桩
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.pdf_tab.QMessageBox.critical",
        lambda *a, **k: None,
    )
    dlg.ui.btn_generate.setEnabled(False)
    dlg.ui.btn_cancel.setVisible(True)

    dlg._on_generate_failed("some error")

    assert dlg.ui.btn_generate.isEnabled() is True
    assert dlg.ui.btn_cancel.isHidden() is True  # 取消按钮隐藏


def test_render_results_keeps_pending_status_for_unprocessed(dlg, tmp_path):
    """取消时 results 少于表行数 → 未处理的行保持"待转换"。"""
    from pathlib import Path

    # 表里 3 行(预览态),但只拿到 1 个结果(取消)
    dlg.selected_files = [Path("a.docx"), Path("b.docx"), Path("c.docx")]
    dlg._do_refresh_preview()
    results = [{"source": Path("a.docx"), "output": Path("a.pdf"), "success": True, "error": ""}]

    dlg._render_results(results)

    tbl = dlg.ui.table_files
    assert tbl.item(0, 3).text() == "成功"
    assert tbl.item(1, 3).text() == "待转换"  # 未处理
    assert tbl.item(2, 3).text() == "待转换"
