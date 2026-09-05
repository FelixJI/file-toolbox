"""Excel 合并 Tab GUI 测试:表格结构、选项映射、文件过滤、结果填充、输出目录解析。

不触发真实合并 worker/COM,仅校验控件状态与纯 Python 编排逻辑。
UI 由 generated/ui_excel_merge_dialog.py(Ui_ExcelMergeDialog)构建,本测试验证接入正确。
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 用 QtWidgets 子模块做 importorskip(而非顶层 PySide6):后者只校验包可 import,
# 不触发 libEGL/libGL 原生库加载;真实 import QtWidgets 才会,缺库时应跳过而非收集失败。
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from file_toolbox.core.excel_merge import (  # noqa: E402
    MODE_FORMULAS,
    MODE_VALUES,
    NAMING_KEEP,
    NAMING_PREFIX,
    MergeOptions,
    MergeResult,
)
from file_toolbox.gui.controllers.excel_merge_controller import ExcelMergeController  # noqa: E402
from file_toolbox.gui.dialogs.excel_merge_tab import ExcelMergeTab  # noqa: E402
from file_toolbox.gui.generated.ui_excel_merge_dialog import (  # noqa: E402
    HEADERS,
    MODE_LABELS,
    NAMING_LABELS,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(app):
    return ExcelMergeTab()


# ==================== 控件结构 ====================


def test_tab_has_expected_table_headers(tab):
    """结果表格应预置 4 列业务表头,列数与表头一致。"""
    assert tab.ui.table.columnCount() == len(HEADERS)
    headers = [
        tab.ui.table.horizontalHeaderItem(i).text() for i in range(tab.ui.table.columnCount())
    ]
    assert headers == HEADERS


def test_tab_starts_empty(tab):
    """新建 Tab 无文件、无结果行、状态就绪。"""
    assert tab.ui.list_files.count() == 0
    assert tab.ui.table.rowCount() == 0
    assert tab.ui.lbl_status.text() == "就绪"


def test_combo_labels_and_mapping_aligned(tab):
    """下拉框文案与 controller 索引映射一一对应(顺序契约)。"""
    assert [
        tab.ui.cmb_naming.itemText(i) for i in range(tab.ui.cmb_naming.count())
    ] == NAMING_LABELS
    assert [tab.ui.cmb_mode.itemText(i) for i in range(tab.ui.cmb_mode.count())] == MODE_LABELS


# ==================== controller(无 Qt) ====================


def test_controller_build_options_mapping():
    """索引 -> 常量映射正确;越界索引夹回有效范围(防御)。"""
    c = ExcelMergeController()
    assert c.build_options(0, 0, False) == MergeOptions(
        naming=NAMING_PREFIX, mode=MODE_VALUES, include_hidden=False
    )
    opt = c.build_options(1, 1, True)
    assert opt.naming == NAMING_KEEP
    assert opt.mode == MODE_FORMULAS
    assert opt.include_hidden is True
    # 越界夹回
    assert c.build_options(-3, 99, False).naming == NAMING_PREFIX
    assert c.build_options(0, 99, False).mode == MODE_FORMULAS


def test_controller_format_progress():
    assert ExcelMergeController().format_progress(2, 5, "合并 a.xlsx") == "[2/5] 合并 a.xlsx"


def test_controller_summarize():
    c = ExcelMergeController()
    from file_toolbox.core.excel_merge import FailedSource, MergedSheet

    r = MergeResult(output=Path("out.xlsx"))
    r.sheets = [MergedSheet("a.xlsx", "S", "a-S")]
    assert c.summarize(r) == "已合并 1 个工作表 -> out.xlsx"
    r.failed = [FailedSource("bad.xlsx", "无法读取")]
    assert c.summarize(r) == "已合并 1 个工作表,1 个文件失败 -> out.xlsx"
    assert c.summarize(MergeResult(cancelled=True)) == "已取消"
    assert c.summarize(MergeResult(error_message="全部源文件读取失败")) == (
        "失败:全部源文件读取失败"
    )


# ==================== Tab 行为 ====================


def test_options_reads_controls(tab):
    """_options() 从控件读取并经 controller 映射为 MergeOptions。"""
    assert tab._options().naming == NAMING_PREFIX
    assert tab._options().mode == MODE_VALUES
    assert tab._options().include_hidden is False

    tab.ui.cmb_naming.setCurrentIndex(1)
    tab.ui.cmb_mode.setCurrentIndex(1)
    tab.ui.chk_hidden.setChecked(True)
    opt = tab._options()
    assert opt.naming == NAMING_KEEP
    assert opt.mode == MODE_FORMULAS
    assert opt.include_hidden is True


def test_is_source_filters_suffix_and_temp(tab, tmp_path):
    """仅 .xlsx/.xlsm 且非 ~$ 临时文件可作为源。"""
    assert tab._is_source(Path("C:/x/a.xlsx")) is True
    assert tab._is_source(Path("C:/x/a.XLSM")) is True
    assert tab._is_source(Path("C:/x/a.xls")) is False
    assert tab._is_source(Path("C:/x/a.csv")) is False
    assert tab._is_source(Path("C:/x/~$a.xlsx")) is False


def test_add_paths_dedupes_and_updates_status(tab, make_xlsx):
    """重复路径只加入一次;加入后状态栏显示已选数量。"""
    a = make_xlsx("a.xlsx", {"S": [["v"]]})
    b = make_xlsx("b.xlsx", {"S": [["v"]]})

    tab._add_paths([a, b, a])

    assert tab.ui.list_files.count() == 2
    assert len(tab._files) == 2
    assert tab.ui.lbl_status.text() == "已选择 2 个文件"


def test_add_paths_ignores_unsupported(tab, tmp_path):
    """不支持后缀与不存在的路径被忽略。"""
    txt = tmp_path / "n.txt"
    txt.write_text("x")
    tab._add_paths([txt, tmp_path / "missing.xlsx"])
    assert tab.ui.list_files.count() == 0


def test_clear_resets_everything(tab, make_xlsx):
    a = make_xlsx("a.xlsx", {"S": [["v"]]})
    tab._add_paths([a])
    tab._populate_table(_result_with_failure())

    tab._clear()

    assert tab.ui.list_files.count() == 0
    assert tab.ui.table.rowCount() == 0
    assert tab.ui.lbl_status.text() == "就绪"


def test_merge_without_files_warns(tab, monkeypatch):
    """未选文件点合并 → 警告框,不启动 worker。"""
    warned: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *_a, text=None, **_k: warned.append(text or _a[-1])
    )
    tab._merge()
    assert warned and "请先添加 Excel 文件" in warned[0]
    assert tab._worker is None


def test_populate_table_merges_and_failures(tab):
    """结果表格:已合并行 + 失败行(浅黄底)。"""
    tab._populate_table(_result_with_failure())

    assert tab.ui.table.rowCount() == 2
    assert tab.ui.table.item(0, 2).text() == "a-S"
    assert tab.ui.table.item(0, 3).text() == "已合并"
    assert tab.ui.table.item(1, 0).text() == "bad.xlsx"
    assert "无法读取" in tab.ui.table.item(1, 3).text()
    assert tab.ui.table.item(1, 3).background().color().name().lower() == "#fff2cc"
    assert tab.ui.table.item(0, 3).background().color().name().lower() != "#fff2cc"


def test_resolve_outdir_chain(tab, make_xlsx, monkeypatch, tmp_path):
    """输出目录解析优先级:输入框 > 上次设置 > 首个源文件目录。"""
    monkeypatch.chdir(tmp_path)
    a = make_xlsx("a.xlsx", {"S": [["v"]]})
    tab._add_paths([a])
    sub = tmp_path / "pick"
    sub.mkdir()

    # 1. 无输入框内容、无设置 → 首个源文件目录
    assert tab._resolve_outdir() == a.parent

    # 2. 上次输出目录(settings)仍存在 → 优先于源文件目录
    from file_toolbox.common import settings

    settings.set("excel_merge/last_output_dir", str(sub))
    assert tab._resolve_outdir() == sub

    # 3. 输入框内容最优先
    tab.ui.edit_outdir.setText(str(tmp_path))
    assert tab._resolve_outdir() == tmp_path


def test_close_event_cancels_running_worker(tab, monkeypatch):
    """关闭时若 worker 仍在跑:cancel+quit+wait,引用置空。"""
    worker = MagicMock()
    worker.isRunning.return_value = True
    tab._worker = worker

    tab.closeEvent(QCloseEvent())

    worker.cancel.assert_called_once()
    worker.quit.assert_called_once()
    worker.wait.assert_called_once_with(3000)
    assert tab._worker is None


def test_close_event_without_worker_is_noop(tab):
    """无 worker 时直接关闭,不抛错。"""
    tab.closeEvent(QCloseEvent())
    assert tab._worker is None


# ==================== 端到端 Tab 流程(真实 worker + 虚构 xlsx) ====================


def _wait_worker_done(tab, app, timeout_ms: int = 10000) -> None:
    """轮询事件循环直到 worker 结束(_on_merge_ok/_on_merge_failed 置空引用)。"""
    import time

    deadline = time.monotonic() + timeout_ms / 1000
    while tab._worker is not None:
        app.processEvents()
        if time.monotonic() > deadline:
            raise AssertionError("worker 未在超时内结束")
        time.sleep(0.01)


def test_add_files_via_dialog_and_browse(tab, monkeypatch, make_xlsx):
    """文件/文件夹选择与目录浏览对话框接通,QFileDialog 走 monkeypatch 假实现。"""
    a = make_xlsx("a.xlsx", {"S": [["v"]]})
    b = make_xlsx("b.xlsx", {"S": [["v"]]})
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.excel_merge_tab.QFileDialog.getOpenFileNames",
        lambda *args, **kwargs: ([str(a)], ""),
    )
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.excel_merge_tab.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.excel_merge_tab.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(b.parent),
    )

    tab._add_files()
    assert tab.ui.list_files.count() == 1

    tab._add_folder()  # 非递归:同目录下另一个 xlsx 被加入
    assert tab.ui.list_files.count() == 2

    tab._browse_outdir()
    assert tab.ui.edit_outdir.text() == str(b.parent)


def test_merge_flow_success(tab, app, monkeypatch, make_xlsx, tmp_path):
    """选文件 → 开始合并 → worker 完成:表格填充、状态摘要、输出文件落盘。"""
    monkeypatch.chdir(tmp_path)  # 隔离 settings(成功路径会写 last_output_dir)
    make_xlsx("a.xlsx", {"S1": [["v"]]})
    make_xlsx("b.xlsx", {"S2": [["v"]]})
    infos: list[tuple] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_k: infos.append("info"))
    files = sorted(tmp_path.glob("*.xlsx"), key=lambda p: p.name)
    tab._add_paths(files)
    tab.ui.edit_outdir.setText(str(tmp_path / "out"))

    tab._merge()
    assert tab.ui.btn_merge.isEnabled() is False  # 合并期间禁用
    _wait_worker_done(tab, app)

    out = tmp_path / "out" / "合并结果.xlsx"
    assert out.is_file()
    assert tab.ui.btn_merge.isEnabled() is True
    assert tab.ui.table.rowCount() == 2
    assert "已合并 2 个工作表" in tab.ui.lbl_status.text()
    assert infos == ["info"]
    from file_toolbox.common import settings

    assert settings.get("excel_merge/last_output_dir") == str(tmp_path / "out")


def test_merge_flow_all_failed_warns(tab, app, monkeypatch, tmp_path):
    """全部源文件失败 → 警告框 + 状态栏失败,不写输出。"""
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"nope")
    warns: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append("warn"))
    tab._add_paths([bad])

    tab._merge()
    _wait_worker_done(tab, app)

    assert warns == ["warn"]
    assert tab.ui.lbl_status.text().startswith("失败:")
    assert not (tmp_path / "合并结果.xlsx").exists()


def test_merge_reentry_guard_while_running(tab, monkeypatch, make_xlsx):
    """worker 运行中重复点击不重复启动。"""
    a = make_xlsx("a.xlsx", {"S": [["v"]]})
    tab._add_paths([a])
    running = MagicMock()
    running.isRunning.return_value = True
    tab._worker = running

    tab._merge()

    assert tab._worker is running  # 未被替换


def test_on_merge_failed_shows_critical(tab, monkeypatch):
    """worker 异常信号 → 严重错误框 + 状态合并失败,按钮恢复。"""
    criticals: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: criticals.append("crit"))
    tab._worker = MagicMock()  # 非 None,模拟运行中

    tab._on_merge_failed("boom")

    assert criticals == ["crit"]
    assert tab.ui.lbl_status.text() == "合并失败"
    assert tab.ui.btn_merge.isEnabled() is True
    assert tab._worker is None


def _result_with_failure() -> MergeResult:
    from file_toolbox.core.excel_merge import FailedSource, MergedSheet

    r = MergeResult(output=Path("out.xlsx"))
    r.sheets = [MergedSheet("a.xlsx", "S", "a-S")]
    r.failed = [FailedSource("bad.xlsx", "无法读取: 损坏")]
    return r
