"""PDF Tab GUI 测试:下拉框填充、单选按钮互斥分组、配置构建。

不触发真实 COM/文件操作,仅校验控件状态与逻辑。
"""

import pytest

# 用 QtWidgets 子模块做 importorskip(而非顶层 PySide6):后者只校验包可 import,
# 不触发 libEGL/libGL 原生库加载;真实 import QtWidgets 才会,缺库时应跳过而非收集失败。
pytest.importorskip("PySide6.QtWidgets")

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
    headers = [dlg.ui.table_files.horizontalHeaderItem(i).text() for i in range(4)]
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

    dlg.selected_files = [tmp_path / "no_such.docx"]
    dlg._do_refresh_preview()  # 不应抛
    assert dlg.ui.table_files.item(0, 2).text() == ""


def test_clear_files_resets_table(dlg, tmp_path):
    """_on_clear_files 清空 selected_files 与表。"""

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


# ---------- 停止 worker:不强制 terminate(COM 安全) ----------


class _FakeWorkerStub:
    """纯桩(无真实线程):模拟持 COM 的 QThread 接口供 _stop_worker 调用。

    用记录式 wait() 返回值模拟"在超时内停止"与"超时未停止"两种场景,避免在测试中
    真起 OS 线程(与 Qt 进程退出 GC 交互会导致 Windows 堆损坏 0xc0000374)。
    """

    def __init__(self, wait_returns: bool = True):
        self.cancel_called = False
        self.quit_called = False
        self.terminate_called = False
        self.wait_called_with = []
        self._running = True
        self._wait_returns = wait_returns

    def isRunning(self):
        return self._running

    def cancel(self):
        self.cancel_called = True
        self._running = False  # 协作式取消后视为停止

    def quit(self):
        self.quit_called = True

    def wait(self, timeout_ms):
        self.wait_called_with.append(timeout_ms)
        return self._wait_returns  # 由用例决定是否"及时停止"

    def terminate(self):
        self.terminate_called = True  # 不应被调用


def test_stop_worker_does_not_terminate_com_worker(dlg):
    """回归:PDF worker 持 COM,_stop_worker 必须协作式取消,绝不 terminate。

    验证对正在运行的 PDF worker:
      - cancel() 被调用(协作式取消);
      - quit() 被调用(保持一致);
      - terminate() 绝不被调用(避免 COM 泄漏/死锁)。
    """
    worker = _FakeWorkerStub(wait_returns=True)  # 在超时内停止
    dlg.worker = worker

    dlg._stop_worker(timeout_ms=2000)

    assert worker.cancel_called, "_stop_worker 应调用 cancel()"
    assert worker.quit_called, "_stop_worker 应调用 quit()"
    assert not worker.terminate_called, "_stop_worker 绝不应调用 terminate()"
    assert worker.wait_called_with == [2000]
    assert dlg.worker is None


def test_stop_worker_logs_warning_on_timeout_without_terminate(dlg, caplog):
    """超时未停止时仅记 warning,绝不 terminate。"""
    import logging

    worker = _FakeWorkerStub(wait_returns=False)  # 模拟未在超时内停止
    dlg.worker = worker

    with caplog.at_level(logging.WARNING, logger="file_toolbox.gui.dialogs.pdf_tab"):
        dlg._stop_worker(timeout_ms=100)

    assert worker.cancel_called
    assert not worker.terminate_called, "超时也不应 terminate"
    assert any("未能" in r.message or "terminate" in r.message for r in caplog.records), (
        "超时应记录 warning"
    )
    assert dlg.worker is None


def test_stop_worker_noop_when_no_worker(dlg):
    """无 worker 或已停止 → 不抛、不调任何接口。"""
    dlg.worker = None
    dlg._stop_worker()  # 不应抛
    assert dlg.worker is None

    stopped = _FakeWorkerStub(wait_returns=True)
    stopped._running = False  # 已停止
    dlg.worker = stopped
    dlg._stop_worker()
    assert not stopped.cancel_called  # isRunning()=False 分支不调 cancel


def test_dialog_exposes_logger_for_mixin_contract(dlg):
    """回归:BatchDialogMixin._cleanup_batch_dialog / _stop_worker 调用 self.logger,
    PDFGeneratorDialog 未混入 LoggableMixin,必须自行暴露 logger,否则 closeEvent
    会在清理中途抛 AttributeError。
    """
    import logging

    assert hasattr(dlg, "logger")
    assert isinstance(dlg.logger, logging.Logger)
    # _cleanup_batch_dialog 不应抛(它内部会 self.logger.debug)
    dlg._cleanup_batch_dialog()

    assert dlg.worker is None


# ---------- 文件选择包装器(覆盖 244-245 / 249-250) ----------
# _on_select_files / _on_select_folder 委托给 mixin 的 _select_files / _select_folder,
# 然后调 _refresh_preview(防抖定时器)。这两组测试把 _select_* 替换为 spy,验证委托
# 与预览触发(预览经防抖定时器,_refresh_preview 调用会被记录)。


def test_on_select_files_calls_select_files_and_refresh(dlg, monkeypatch):
    """_on_select_files 委托给 _select_files(list_widget=None)并触发 _refresh_preview。"""
    calls = {"select": 0, "refresh": 0}

    def fake_select_files(list_widget=None, auto_preview=True):
        calls["select"] += 1
        assert list_widget is None

    monkeypatch.setattr(dlg, "_select_files", fake_select_files)
    monkeypatch.setattr(
        dlg, "_refresh_preview", lambda: calls.__setitem__("refresh", calls["refresh"] + 1)
    )

    dlg._on_select_files()

    assert calls["select"] == 1
    assert calls["refresh"] == 1


def test_on_select_folder_calls_select_folder_and_refresh(dlg, monkeypatch):
    """_on_select_folder 委托给 _select_folder(list_widget=None)并触发 _refresh_preview。"""
    calls = {"select": 0, "refresh": 0}

    def fake_select_folder(list_widget=None, ask_recursive=True, auto_preview=True):
        calls["select"] += 1
        assert list_widget is None

    monkeypatch.setattr(dlg, "_select_folder", fake_select_folder)
    monkeypatch.setattr(
        dlg, "_refresh_preview", lambda: calls.__setitem__("refresh", calls["refresh"] + 1)
    )

    dlg._on_select_folder()

    assert calls["select"] == 1
    assert calls["refresh"] == 1


# ---------- 输出目录浏览(覆盖 258-260) ----------


def test_browse_output_dir_sets_edit_when_dir_chosen(dlg, monkeypatch):
    """选到目录 → edit_output_dir 被设为该目录。"""
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.pdf_tab.QFileDialog.getExistingDirectory",
        lambda *a, **k: "/some/out/dir",
    )
    dlg.ui.edit_output_dir.setText("")

    dlg._browse_output_dir()

    assert dlg.ui.edit_output_dir.text() == "/some/out/dir"


def test_browse_output_dir_unchanged_when_cancelled(dlg, monkeypatch):
    """用户取消(返回 "")→ edit_output_dir 不被改写。"""
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.pdf_tab.QFileDialog.getExistingDirectory",
        lambda *a, **k: "",
    )
    dlg.ui.edit_output_dir.setText("/keep/this")

    dlg._browse_output_dir()

    assert dlg.ui.edit_output_dir.text() == "/keep/this"


# ---------- 生成:worker 正在运行时短路(覆盖 268) ----------


class _RunningWorkerStub:
    """isRunning() 恒为 True 的 worker 桩,用于触发 _generate 的短路分支。"""

    started = False

    def isRunning(self):
        return True


def test_generate_short_circuits_when_worker_running(dlg, monkeypatch, tmp_path):
    """worker 正在运行 → _generate 直接 return,不创建/启动新 worker。"""
    from file_toolbox.gui.workers.pdf_worker import PdfGenerateWorker

    f = tmp_path / "a.docx"
    f.write_bytes(b"x")
    dlg.selected_files = [f]

    # 预置一个"运行中"的旧 worker
    pre_existing = _RunningWorkerStub()
    dlg.worker = pre_existing

    started = []
    monkeypatch.setattr(PdfGenerateWorker, "start", lambda self: started.append(True))
    # _build_config 也走 controller;短路分支不应走到这里
    built = []
    monkeypatch.setattr(dlg, "_build_config", lambda: built.append(True) or {})

    dlg._generate()

    assert started == [], "worker 运行中时不应启动新 worker"
    assert built == [], "短路分支不应构建 config"
    assert dlg.worker is pre_existing, "不应替换已有 worker"


# ---------- 生成完成:写历史失败时 UI 仍恢复(覆盖 300-301) ----------


def test_on_generate_ok_restores_ui_when_history_write_fails(dlg, monkeypatch):
    """_build_config 抛异常 → 写历史 except 分支(记 warning),UI 仍恢复 enabled、worker 清空。"""
    from pathlib import Path

    # 完成路径有 fail=0 时不弹 QMessageBox,这里强制全成功避免弹窗
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.pdf_tab.QMessageBox.warning",
        lambda *a, **k: None,
    )
    # _render_results 在 _on_generate_ok 内首次调用一次(用真实结果);随后 try 内再次
    # 调 _build_config 会抛 → 命中 except(300-301)。这里只让第二次(try 内)抛:
    # 简化:直接 stub _build_config 总抛(首次 _render_results 不依赖它)。
    monkeypatch.setattr(
        dlg, "_build_config", lambda: (_ for _ in ()).throw(RuntimeError("cfg boom"))
    )

    results = [
        {"source": Path("a.docx"), "output": Path("a.pdf"), "success": True, "error": ""},
    ]
    dlg.selected_files = [Path("a.docx")]
    dlg._do_refresh_preview()
    dlg.ui.btn_generate.setEnabled(False)
    dlg.ui.btn_cancel.setVisible(True)
    dlg.worker = _RunningWorkerStub()  # 任意非 None,验证会被清空

    dlg._on_generate_ok(results)

    # except 被命中但 UI 仍恢复
    assert dlg.ui.btn_generate.isEnabled() is True
    assert dlg.worker is None
    # 表已被结果态填充(_render_results 先于 try 执行)
    assert dlg.ui.table_files.item(0, 3).text() == "成功"


# ---------- 取消(覆盖 314-316) ----------


class _CancellableWorkerStub:
    """带 cancel() 的 worker 桩,用于 _on_cancel。"""

    def __init__(self):
        self.cancel_called = False

    def cancel(self):
        self.cancel_called = True


def test_on_cancel_calls_worker_cancel_and_sets_label(dlg):
    """worker 非 None 且有 cancel → 调 cancel(),label 设为"正在取消..."。"""
    worker = _CancellableWorkerStub()
    dlg.worker = worker

    dlg._on_cancel()

    assert worker.cancel_called
    assert dlg.ui.label_progress.text() == "正在取消..."


def test_on_cancel_noop_when_no_worker(dlg):
    """无 worker → 不抛,label 仍更新。"""
    dlg.worker = None

    dlg._on_cancel()  # 不应抛

    assert dlg.ui.label_progress.text() == "正在取消..."


# ---------- 结果渲染:results 行数超过表行数(覆盖 384 break) ----------


def test_render_results_breaks_when_results_exceed_table_rows(dlg, tmp_path):
    """表只有 1 行,results 有 2 条 → 第 2 条被 break 跳过,第 1 行仍正确更新。"""
    from pathlib import Path

    # 预置 1 行预览态
    dlg.selected_files = [Path("a.docx")]
    dlg._do_refresh_preview()
    assert dlg.ui.table_files.rowCount() == 1

    results = [
        {"source": Path("a.docx"), "output": Path("a.pdf"), "success": True, "error": ""},
        {"source": Path("b.docx"), "output": Path("b.pdf"), "success": True, "error": ""},
    ]

    dlg._render_results(results)  # 内部 row=1 时 break,不抛 IndexError

    tbl = dlg.ui.table_files
    assert tbl.item(0, 3).text() == "成功"  # 第 1 行已更新
    assert tbl.rowCount() == 1  # 表行数未被扩


# ---------- 引擎检测:非 NO_COM 路径(覆盖 180-189) ----------


def test_detect_engines_async_path_records_callback(dlg, monkeypatch):
    """非 NO_COM 形态:置"正在检测...",调 detect_engines_async(callback=...)。

    conftest 的 autouse fixture 设了 FILE_TOOLBOX_NO_COM_DETECT=1,这里 delenv 让
    _init_engine_info 走 180-189 的异步分支;并 spy detect_engines_async 捕获 callback。
    """
    monkeypatch.delenv("FILE_TOOLBOX_NO_COM_DETECT", raising=False)

    captured = {}

    def fake_detect_engines_async(callback=None, **kwargs):
        captured["callback"] = callback

    monkeypatch.setattr(dlg._svc, "detect_engines_async", fake_detect_engines_async)

    dlg._init_engine_info()

    assert dlg.ui.label_engine_info.text() == "正在检测可用引擎..."
    assert callable(captured.get("callback"))
    # 回调内部走 QTimer.singleShot(0, ...) 设文本;调用后需 flush 事件循环才生效
    captured["callback"]("检测到: Office")
    QApplication.processEvents()
    assert dlg.ui.label_engine_info.text() == "检测到: Office"


def test_detect_engines_async_exception_falls_back_to_sync(dlg, monkeypatch):
    """detect_engines_async 抛异常 → except 分支回退到 get_engine_info(use_cache=True)。"""
    monkeypatch.delenv("FILE_TOOLBOX_NO_COM_DETECT", raising=False)

    def boom_async(callback=None, **kwargs):
        raise RuntimeError("no pywin32")

    monkeypatch.setattr(dlg._svc, "detect_engines_async", boom_async)
    monkeypatch.setattr(dlg._svc, "get_engine_info", lambda use_cache=False: "fallback-info")

    dlg._init_engine_info()

    assert dlg.ui.label_engine_info.text() == "fallback-info"


# ---------- closeEvent(覆盖 411-414) ----------


def test_close_event_cleans_up_and_closes_service(dlg, monkeypatch):
    """closeEvent 调 _cleanup_batch_dialog + svc.close() + super().closeEvent,不抛。"""
    from PySide6.QtGui import QCloseEvent

    closed = []
    monkeypatch.setattr(dlg._svc, "close", lambda: closed.append(True))

    event = QCloseEvent()
    dlg.closeEvent(event)  # 不应抛

    assert closed == [True], "svc.close() 应被调用"
    assert dlg.worker is None  # _cleanup_batch_dialog → _stop_worker 清空


# ---------- _set_ui_enabled 覆盖(顺带补强,验证取消按钮可见性翻转) ----------


def test_set_ui_enabled_toggles_cancel_button_visibility(dlg):
    """_set_ui_enabled(False) 显示取消按钮,True 隐藏。"""
    dlg._set_ui_enabled(False)
    assert dlg.ui.btn_generate.isEnabled() is False
    assert dlg.ui.btn_cancel.isHidden() is False

    dlg._set_ui_enabled(True)
    assert dlg.ui.btn_generate.isEnabled() is True
    assert dlg.ui.btn_cancel.isHidden() is True
