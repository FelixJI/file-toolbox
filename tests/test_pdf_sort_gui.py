"""PDF 排序 Tab GUI 测试:表格结构、选项映射、文件过滤、结果填充、输出目录解析。

不触发真实排序 worker/IO,仅校验控件状态与纯 Python 编排逻辑。
UI 由 generated/ui_pdf_sort_dialog.py(Ui_PdfSortDialog)构建,本测试验证接入正确。
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 用 QtWidgets 子模块做 importorskip(而非顶层 PySide6):后者只校验包可 import,
# 不触发 libEGL/libGL 原生库加载;真实 import QtWidgets 才会,缺库时应跳过而非收集失败。
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from file_toolbox.core.pdf_sort import (  # noqa: E402
    ORDER_ASC,
    ORDER_DESC,
    UNMATCHED_FAIL,
    UNMATCHED_LAST,
    FailedFile,
    PagePlan,
    SortedFile,
    SortOptions,
    SortResult,
)
from file_toolbox.gui.controllers.pdf_sort_controller import PdfSortController  # noqa: E402
from file_toolbox.gui.dialogs.pdf_sort_tab import PdfSortTab  # noqa: E402
from file_toolbox.gui.generated.ui_pdf_sort_dialog import (  # noqa: E402
    HEADERS,
    ORDER_LABELS,
    UNMATCHED_LABELS,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch):
    """把 settings 读写隔离到内存字典:_on_sort_ok 会记忆上次输出目录,
    不隔离会污染真实 .file_toolbox/settings.json 并串扰同会话其他用例。"""
    from file_toolbox.common import settings

    store: dict[str, object] = {}
    monkeypatch.setattr(settings, "get", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(settings, "set", lambda key, value: store.__setitem__(key, value))


@pytest.fixture
def tab(app):
    return PdfSortTab()


# ==================== 控件结构 ====================


def test_tab_has_expected_table_headers(tab):
    """结果表格应预置 5 列业务表头,列数与表头一致。"""
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
    assert tab.ui.edit_pattern.text() == ""


def test_combo_labels_and_mapping_aligned(tab):
    """下拉框文案与 controller 索引映射一一对应(顺序契约)。"""
    assert [tab.ui.cmb_order.itemText(i) for i in range(tab.ui.cmb_order.count())] == ORDER_LABELS
    assert [
        tab.ui.cmb_unmatched.itemText(i) for i in range(tab.ui.cmb_unmatched.count())
    ] == UNMATCHED_LABELS


# ==================== controller(无 Qt) ====================


def test_controller_build_options_mapping():
    """索引 -> 常量映射正确;越界索引夹回有效范围(防御)。"""
    c = PdfSortController()
    assert c.build_options(r"Date:\s*([0-9-]+)", 0, 0) == SortOptions(
        pattern=r"Date:\s*([0-9-]+)", order=ORDER_ASC, unmatched=UNMATCHED_LAST
    )
    opt = c.build_options("x", 1, 2)
    assert opt.order == ORDER_DESC
    assert opt.unmatched == UNMATCHED_FAIL
    # 越界夹回边界值:负索引 -> 首项,超界 -> 末项
    assert c.build_options("x", -3, -3).unmatched == UNMATCHED_LAST
    assert c.build_options("x", 99, 99).order == ORDER_DESC
    assert c.build_options("x", 99, 0).order == ORDER_DESC


def test_controller_format_progress():
    assert PdfSortController().format_progress(2, 5, "排序 a.pdf") == "[2/5] 排序 a.pdf"


def test_controller_summarize():
    c = PdfSortController()
    r = SortResult(sorted_files=[SortedFile("a.pdf", Path("a_排序.pdf"), [])])
    assert c.summarize(r) == "已写出 1 个排序输出 -> a_排序.pdf"
    r.failed = [FailedFile("bad.pdf", "无法读取")]
    assert c.summarize(r) == "已写出 1 个排序输出,1 个文件失败 -> a_排序.pdf"
    unchanged = SortResult(sorted_files=[SortedFile("a.pdf", None, [], "顺序未变")])
    assert c.summarize(unchanged) == "1 个文件顺序未变,未写出输出"
    assert c.summarize(SortResult(cancelled=True)) == "已取消"
    assert c.summarize(SortResult(error_message="全部源文件失败")) == "失败:全部源文件失败"


# ==================== Tab 行为 ====================


def test_options_reads_controls(tab):
    """_options() 从控件读取并经 controller 映射为 SortOptions。"""
    tab.ui.edit_pattern.setText(r"Date:\s*([0-9-]+)")
    assert tab._options() == SortOptions(pattern=r"Date:\s*([0-9-]+)")

    tab.ui.cmb_order.setCurrentIndex(1)
    tab.ui.cmb_unmatched.setCurrentIndex(2)
    opt = tab._options()
    assert opt.order == ORDER_DESC
    assert opt.unmatched == UNMATCHED_FAIL


def test_is_source_filters_suffix_and_temp(tab):
    """仅 .pdf 且非 ~$ 临时文件可作为源。"""
    assert tab._is_source(Path("C:/x/a.pdf")) is True
    assert tab._is_source(Path("C:/x/a.PDF")) is True
    assert tab._is_source(Path("C:/x/a.docx")) is False
    assert tab._is_source(Path("C:/x/~$a.pdf")) is False


def test_add_paths_dedupes_and_updates_status(tab, make_text_pdf):
    """重复路径只加入一次;加入后状态栏显示已选数量。"""
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    b = make_text_pdf("b.pdf", ["Date: 2024-01-01"])

    tab._add_paths([a, b, a])

    assert tab.ui.list_files.count() == 2
    assert len(tab._files) == 2
    assert tab.ui.lbl_status.text() == "已选择 2 个文件"


def test_add_paths_ignores_unsupported(tab, tmp_path):
    """不支持后缀与不存在的路径被忽略。"""
    txt = tmp_path / "a.txt"
    txt.write_text("x")

    tab._add_paths([txt, tmp_path / "ghost.pdf", tmp_path])

    assert tab.ui.list_files.count() == 0


def test_clear_resets_everything(tab, make_text_pdf):
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    tab._add_paths([a])
    tab.ui.table.setRowCount(2)

    tab._clear()

    assert tab._files == []
    assert tab.ui.list_files.count() == 0
    assert tab.ui.table.rowCount() == 0
    assert tab.ui.lbl_status.text() == "就绪"


def test_resolve_outdir_prefers_edit_text(tab, make_text_pdf):
    """输出框内容优先于上次目录与源文件目录。"""
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    tab._add_paths([a])
    tab.ui.edit_outdir.setText("C:/some/dir")

    assert tab._resolve_outdir() == Path("C:/some/dir")


def test_resolve_outdir_falls_back_to_first_source(tab, make_text_pdf, monkeypatch):
    """输出框为空且无上次目录时,落到首个源文件目录。"""
    from file_toolbox.common import settings

    monkeypatch.setattr(settings, "get", lambda key, default=None: None)
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])

    tab._add_paths([a])

    assert tab._resolve_outdir() == a.parent


def test_sort_warns_when_no_files(tab, monkeypatch):
    """无文件点击排序 → 警告弹窗,不启动 worker。"""
    warned: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, msg: warned.append(msg))
    tab._sort()
    assert warned and "请先添加 PDF 文件" in warned[0]
    assert tab._worker is None


def test_sort_warns_when_no_pattern(tab, make_text_pdf, monkeypatch):
    """匹配格式为空 → 警告弹窗,不启动 worker。"""
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    tab._add_paths([a])
    warned: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, msg: warned.append(msg))

    tab._sort()

    assert warned and "匹配格式" in warned[0]
    assert tab._worker is None


def test_sort_warns_when_pattern_invalid(tab, make_text_pdf, monkeypatch):
    """非法正则 → 警告弹窗提示无效,不启动 worker。"""
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    tab._add_paths([a])
    tab.ui.edit_pattern.setText("([0-9")
    warned: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, msg: warned.append(msg))

    tab._sort()

    assert warned and "无效的匹配格式" in warned[0]
    assert tab._worker is None


def test_sort_starts_worker_single_file(tab, make_text_pdf, monkeypatch):
    """单文件:启动 worker,输出为 outdir/主名_排序.pdf;按钮禁用。"""
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    tab._add_paths([a])
    tab.ui.edit_pattern.setText("Date")
    created = {}
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.pdf_sort_tab.PdfSortWorker",
        lambda svc, files, output, options, parent=None: (
            created.update(files=files, output=output, options=options) or MagicMock()
        ),
    )

    tab._sort()

    assert created["files"] == [a]
    assert created["output"] == a.parent / "a_排序.pdf"
    assert tab._worker is not None
    assert tab.ui.btn_sort.isEnabled() is False
    assert tab.ui.lbl_status.text() == "排序中…"


def test_sort_starts_worker_multiple_files_as_dir(tab, make_text_pdf, monkeypatch):
    """多文件:输出参数为目录(outdir),由 service 决定各文件名。"""
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    b = make_text_pdf("b.pdf", ["Date: 2024-01-01"])
    tab._add_paths([a, b])
    tab.ui.edit_pattern.setText("Date")
    created = {}
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.pdf_sort_tab.PdfSortWorker",
        lambda svc, files, output, options, parent=None: (
            created.update(files=files, output=output, options=options) or MagicMock()
        ),
    )

    tab._sort()

    assert created["files"] == [a, b]
    assert created["output"] == a.parent


def test_sort_guard_while_worker_running(tab, make_text_pdf, monkeypatch):
    """worker 运行中重复点击不重复启动。"""
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    tab._add_paths([a])
    tab.ui.edit_pattern.setText("Date")
    worker = MagicMock()
    worker.isRunning.return_value = True
    tab._worker = worker

    tab._sort()  # 应直接返回,不再创建新 worker

    worker.start.assert_not_called()


def test_on_sort_ok_populates_table_and_status(tab, monkeypatch):
    """结果回填:每页一行(原页/新页/排序文字),失败文件行浅黄;成功弹信息框。"""
    infos: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, _title, msg: infos.append(msg))
    result = SortResult(
        sorted_files=[
            SortedFile(
                "a.pdf",
                Path("a_排序.pdf"),
                [
                    PagePlan(0, "2024-02-01", True, 1),
                    PagePlan(1, "2024-01-01", True, 0),
                    PagePlan(2, "", False, 2),
                ],
            )
        ],
        failed=[FailedFile("b.pdf", "无法读取: broken")],
    )
    tab.ui.btn_sort.setEnabled(False)

    tab._on_sort_ok(result)

    assert tab._worker is None
    assert tab.ui.btn_sort.isEnabled() is True
    assert tab.ui.table.rowCount() == 4
    row = lambda r: [tab.ui.table.item(r, c).text() for c in range(5)]  # noqa: E731
    assert row(0) == ["a.pdf", "1", "2", "2024-02-01", "已排序"]
    assert row(1) == ["a.pdf", "2", "1", "2024-01-01", "已排序"]
    assert row(2) == ["a.pdf", "3", "3", "—", "未匹配"]
    assert row(3) == ["b.pdf", "", "", "", "失败:无法读取: broken"]
    assert tab.ui.lbl_status.text() == "已写出 1 个排序输出,1 个文件失败 -> a_排序.pdf"
    assert infos


def test_on_sort_ok_marks_unchanged_rows(tab, monkeypatch):
    """顺序未变的文件:每页状态列标注,摘要说明未写出输出。"""
    infos: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, _title, msg: infos.append(msg))
    result = SortResult(
        sorted_files=[SortedFile("a.pdf", None, [PagePlan(0, "k", True, 0)], "顺序未变")]
    )

    tab._on_sort_ok(result)

    assert tab.ui.table.item(0, 4).text() == "顺序未变,已排序"
    assert tab.ui.lbl_status.text() == "1 个文件顺序未变,未写出输出"


def test_on_sort_failed_shows_critical(tab, monkeypatch):
    criticals: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda _parent, _title, msg: criticals.append(msg))
    tab.ui.btn_sort.setEnabled(False)

    tab._on_sort_failed("boom")

    assert tab._worker is None
    assert tab.ui.btn_sort.isEnabled() is True
    assert tab.ui.lbl_status.text() == "排序失败"
    assert criticals == ["boom"]


def test_close_event_stops_running_worker(tab, monkeypatch):
    """关闭时仍在运行的 worker 被取消并等待(防泄漏)。"""
    worker = MagicMock()
    worker.isRunning.return_value = True
    tab._worker = worker

    tab.closeEvent(QCloseEvent())

    worker.cancel.assert_called_once()
    worker.quit.assert_called_once()
    worker.wait.assert_called_once_with(3000)
    assert tab._worker is None


def test_close_event_without_worker_noop(tab):
    tab._worker = None
    tab.closeEvent(QCloseEvent())  # 不抛错即通过
