"""Markdown 转换 Tab GUI 测试:目标联动、参数契约、结果呈现、取消与懒加载登记。

不触发真实 Pandoc/openpyxl 转换:按 core 契约注入假 service,验证 Tab 编排
(与其他 *_gui 测试一致)。模态框在 fixture 统一 mock(未 mock 的弹窗会卡住
无头测试),需捕获文案的单测自行覆写。
"""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 用 QtWidgets 子模块做 importorskip(而非顶层 PySide6):后者只校验包可 import,
# 不触发 libEGL/libGL 原生库加载;真实 import QtWidgets 才会,缺库时应跳过而非收集失败。
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from file_toolbox.core.markdown_convert import (  # noqa: E402
    ConversionItem,
    ConversionResult,
)
from file_toolbox.gui.dialogs.markdown_tab import MarkdownConvertTab  # noqa: E402
from file_toolbox.gui.workers.markdown_worker import MarkdownConvertWorker  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 隔离 settings/history 数据根
    # 统一 mock 模态框:任何未被单测覆写的弹窗都会卡住无头测试
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *_a, **_k: None)
    return MarkdownConvertTab()


class _FakeService:
    """契约假 service:记录调用参数,可注入结果/异常/取消阻塞。"""

    def __init__(self, result=None, error=None, block_until_cancel=False):
        self.calls: list[dict] = []
        self._result = result
        self._error = error
        self._block = block_until_cancel

    def convert(
        self,
        files,
        output_dir,
        target="docx",
        excel_mode="tables",
        progress_callback=None,
        cancel_check=None,
    ):
        self.calls.append(
            {
                "files": list(files),
                "output_dir": output_dir,
                "target": target,
                "excel_mode": excel_mode,
            }
        )
        if self._error is not None:
            raise self._error
        if progress_callback is not None:
            for i, f in enumerate(files):
                progress_callback(i + 1, len(files), f"转换 {f.name}")
        if self._block:
            while cancel_check is not None and not cancel_check():
                time.sleep(0.005)
        return self._result


def _mk(tab_files_dir: Path, name: str) -> Path:
    p = tab_files_dir / name
    p.write_text("# 标题\n", encoding="utf-8")
    return p


def _wait_worker_done(tab, app, timeout_ms: int = 10000) -> None:
    """保留真实线程引用并等待退出,再投递 GUI 结果与 finished。"""
    worker = tab._worker
    assert worker is not None
    assert worker.wait(timeout_ms)
    app.processEvents()
    app.processEvents()
    assert tab._worker is None


# ==================== 初始状态与目标格式联动 ====================


def test_tab_starts_empty(tab):
    """新建 Tab 无文件、无结果行、状态就绪、取消不可用。"""
    assert tab.ui.list_files.count() == 0
    assert tab.ui.table.rowCount() == 0
    assert tab.ui.lbl_status.text() == "就绪"
    assert tab.ui.btn_cancel.isEnabled() is False
    assert tab.ui.btn_convert.isEnabled() is True


def test_word_target_disables_excel_mode_with_boundary_hint(tab):
    """默认 Word:Excel 模式禁用,提示 Pandoc 边界(含图片文件会失败,非静默略过)。"""
    assert tab.ui.cmb_target.currentIndex() == 0
    assert tab.ui.cmb_excel_mode.isEnabled() is False
    assert "Pandoc" in tab.ui.lbl_hint.text()
    assert "含图片的文件会转换失败" in tab.ui.lbl_hint.text()


def test_excel_target_enables_mode_and_switches_hint(tab):
    """切到 Excel:模式可用,提示改为工作簿/工作表语义。"""
    tab.ui.cmb_target.setCurrentIndex(1)
    assert tab.ui.cmb_excel_mode.isEnabled() is True
    assert "工作簿" in tab.ui.lbl_hint.text()
    assert "正文" in tab.ui.lbl_hint.text()
    tab.ui.cmb_target.setCurrentIndex(0)
    assert tab.ui.cmb_excel_mode.isEnabled() is False


def test_target_and_mode_index_mapping(tab):
    """下拉索引 -> service 字符串(docx/xlsx;tables/document)。"""
    assert tab._target() == "docx"
    tab.ui.cmb_target.setCurrentIndex(1)
    assert tab._target() == "xlsx"
    assert tab._excel_mode() == "tables"
    tab.ui.cmb_excel_mode.setCurrentIndex(1)
    assert tab._excel_mode() == "document"


# ==================== 文件管理 ====================


def test_is_source_filters_suffix_and_temp(tab):
    assert tab._is_source(Path("C:/x/a.md")) is True
    assert tab._is_source(Path("C:/x/a.MARKDOWN")) is True
    assert tab._is_source(Path("C:/x/a.txt")) is False
    assert tab._is_source(Path("C:/x/~$a.md")) is False


def test_add_paths_dedupes_and_updates_status(tab, tmp_path):
    a = _mk(tmp_path, "a.md")
    b = _mk(tmp_path, "b.md")

    tab._add_paths([a, b, a])

    assert tab.ui.list_files.count() == 2
    assert len(tab._files) == 2
    assert tab.ui.lbl_status.text() == "已选择 2 个文件"


def test_clear_resets_everything(tab, tmp_path):
    a = _mk(tmp_path, "a.md")
    tab._add_paths([a])
    tab._populate_table(ConversionResult([ConversionItem(source=a, output=None, error="x")]))

    tab._clear()

    assert tab.ui.list_files.count() == 0
    assert tab.ui.table.rowCount() == 0
    assert tab.ui.lbl_status.text() == "就绪"


# ==================== 转换启动与参数契约 ====================


def test_convert_without_files_warns(tab, monkeypatch):
    warned: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *_a, text=None, **_k: warned.append(text or _a[-1])
    )
    tab._convert()
    assert warned and "请先添加 Markdown 文件" in warned[0]
    assert tab._worker is None


def test_convert_passes_contract_args(tab, tmp_path):
    """输出目录留空 → None;填写 → Path;目标/模式按索引映射传给 service。"""
    a = _mk(tmp_path, "a.md")
    tab._add_paths([a])
    fake = _FakeService(result=ConversionResult())
    tab._svc = fake

    tab.ui.cmb_target.setCurrentIndex(1)
    tab.ui.cmb_excel_mode.setCurrentIndex(1)
    tab._convert()
    _wait_worker_done(tab, QApplication.instance())

    call = fake.calls[0]
    assert call["files"] == [a]
    assert call["output_dir"] is None
    assert call["target"] == "xlsx"
    assert call["excel_mode"] == "document"

    b = _mk(tmp_path, "b.md")
    tab._add_paths([b])
    out = tmp_path / "out"
    tab.ui.edit_outdir.setText(str(out))
    tab._convert()
    _wait_worker_done(tab, QApplication.instance())
    assert fake.calls[1]["output_dir"] == out


def test_convert_locks_controls_but_keeps_cancel(tab, tmp_path):
    """工作期间输入控件锁住、取消可用;真实 finished 后恢复。"""
    release = {"flag": False}

    class _BlockService(_FakeService):
        def convert(self, *args, **kwargs):
            while not release["flag"]:
                time.sleep(0.005)
            return ConversionResult()

    tab._svc = _BlockService()
    tab._add_paths([_mk(tmp_path, "a.md")])
    tab._convert()
    assert tab.ui.btn_convert.isEnabled() is False
    assert tab.ui.btn_add_files.isEnabled() is False
    assert tab.ui.cmb_target.isEnabled() is False
    assert tab.ui.btn_cancel.isEnabled() is True
    assert tab._worker is not None

    release["flag"] = True
    _wait_worker_done(tab, QApplication.instance())
    assert tab.ui.btn_convert.isEnabled() is True
    assert tab.ui.btn_cancel.isEnabled() is False


def test_convert_reentry_guard_while_running(tab, tmp_path):
    tab._add_paths([_mk(tmp_path, "a.md")])
    running = MagicMock()
    tab._worker = running
    tab._convert()
    assert tab._worker is running


# ==================== 结果呈现(真实 QThread) ====================


def test_convert_flow_populates_success_failure_skip(tab, app, tmp_path):
    """成功/失败/跳过逐行可见;失败行浅黄;完成后按钮恢复、引用释放。"""
    a, b, c = (_mk(tmp_path, n) for n in ("a.md", "b.md", "c.md"))
    out = tmp_path / "a.docx"
    result = ConversionResult(
        [
            ConversionItem(source=a, output=out),
            ConversionItem(source=b, output=None, error="无法解析"),
            ConversionItem(source=c, error="输出已存在,跳过覆盖", skipped=True),
        ]
    )
    tab._svc = _FakeService(result=result)
    tab._add_paths([a, b, c])

    tab._convert()
    _wait_worker_done(tab, app)

    assert tab.ui.table.rowCount() == 3
    assert tab.ui.table.item(0, 1).text() == "成功"
    assert tab.ui.table.item(0, 2).text() == str(out)
    assert tab.ui.table.item(1, 1).text() == "失败"
    assert "无法解析" in tab.ui.table.item(1, 3).text()
    assert tab.ui.table.item(1, 3).background().color().name().lower() == "#fff2cc"
    assert tab.ui.table.item(2, 1).text() == "已跳过"
    assert tab.ui.table.item(2, 3).text() == "输出已存在,跳过覆盖"
    assert tab.ui.lbl_status.text() == "转换完成:成功 1、跳过 1、失败 1"


def test_cancel_flow_keeps_partial_outputs_visible(tab, app, monkeypatch, tmp_path):
    """真实线程取消:已产出文件保留在结果表,摘要标记已取消,给出告警框。"""
    warns: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: warns.append("w"))
    a, b = _mk(tmp_path, "a.md"), _mk(tmp_path, "b.md")
    out = tmp_path / "a.docx"
    result = ConversionResult(
        [ConversionItem(source=a, output=out), ConversionItem(source=b, skipped=True)],
        cancelled=True,
    )
    tab._svc = _FakeService(result=result, block_until_cancel=True)
    tab._add_paths([a, b])

    tab._convert()
    worker = tab._worker
    assert worker is not None
    # 等待业务真正进入转换(阻塞循环)后请求取消
    deadline = time.monotonic() + 5
    while not tab._svc.calls and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    tab._cancel_run()
    assert worker._cancel is True
    assert tab.ui.btn_cancel.isEnabled() is False  # 取消请求后防重复点击
    _wait_worker_done(tab, app)

    assert tab.ui.table.rowCount() == 2
    assert tab.ui.table.item(0, 1).text() == "成功"
    assert tab.ui.lbl_status.text().startswith("已取消")
    assert warns == ["w"]


def test_history_warning_keeps_business_result(tab, app, monkeypatch, tmp_path):
    """OperationResultError:业务结果照常呈现,历史失败单独告警。"""
    warns: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, **_k: warns.append(msg))
    a = _mk(tmp_path, "a.md")
    result = ConversionResult([ConversionItem(source=a, output=tmp_path / "a.docx")])
    from file_toolbox.common.operation_errors import OperationResultError

    tab._svc = _FakeService(error=OperationResultError(result, "历史保存失败:boom"))
    tab._add_paths([a])
    worker = MarkdownConvertWorker(tab._svc, [a], None, "docx", "tables", parent=tab)
    worker.finished_ok.connect(tab._on_convert_ok)
    worker.failed.connect(tab._on_convert_failed)
    worker.warning.connect(tab._on_history_warning)
    tab._worker = worker
    worker.run()  # 同步执行:信号在本线程直接投递
    app.processEvents()

    assert tab.ui.table.rowCount() == 1
    assert tab.ui.table.item(0, 1).text() == "成功"
    assert warns and "历史保存失败" in warns[0]
    tab._worker = None
    worker.deleteLater()


def test_on_convert_failed_shows_critical(tab, monkeypatch):
    criticals: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: criticals.append("c"))
    worker = MagicMock()
    tab._worker = worker
    tab._set_running(True)

    tab._on_convert_failed("boom")

    assert criticals == ["c"]
    assert tab.ui.lbl_status.text() == "转换失败"
    assert tab._worker is worker  # 线程仍由真实 finished 释放
    tab._worker = None


# ==================== 关闭与生命周期 ====================


def test_close_event_cancels_running_worker(tab):
    """关闭时协作取消,保留引用并等待真实 finished。"""
    worker = MagicMock()
    tab._worker = worker

    event = QCloseEvent()
    tab.closeEvent(event)

    worker.cancel.assert_called_once()
    worker.quit.assert_not_called()
    worker.wait.assert_not_called()
    assert tab._worker is worker
    assert not event.isAccepted()
    tab._close_pending = False
    tab._worker = None


def test_close_event_without_worker_is_noop(tab):
    tab.closeEvent(QCloseEvent())
    assert tab._worker is None


# ==================== 历史摘要与主窗口登记 ====================


def test_history_summary_markdown_convert():
    from file_toolbox.gui.dialogs.history_dialog import _summary_label

    label = _summary_label(
        "markdown_convert",
        {"success": 2, "file_count": 3, "target": "xlsx", "excel_mode": "tables"},
    )
    assert "2/3" in label and "xlsx" in label and "[tables]" in label
    assert _summary_label("markdown_convert", {"target": "docx"}) == "0/0 个文件 → docx"


def test_main_window_registers_markdown_tab(app, monkeypatch, tmp_path):
    """懒加载登记:Markdown 页在计划排布后、更新前;历史工具 markdown_convert。"""
    monkeypatch.chdir(tmp_path)
    from file_toolbox.gui.main_window import MainWindow

    class _Latest:
        def check(self):
            from file_toolbox.updater.models import UpdateCheckResult, UpdateCheckStatus

            return UpdateCheckResult(UpdateCheckStatus.LATEST)

        def download_and_apply(self, *args, **kwargs):
            raise AssertionError("不应触发下载")

    win = MainWindow(_Latest())
    assert win._tabs.tabText(9) == "Markdown转换"
    assert win._tab_tools[9] == "markdown_convert"
    assert win._markdown_tab is None  # 未切换不构造

    win._tabs.setCurrentIndex(9)
    app.processEvents()
    assert isinstance(win._markdown_tab, MarkdownConvertTab)
    assert win._tabs.widget(9) is win._markdown_tab

    win._tabs.setCurrentIndex(10)
    assert win._tabs.tabText(10) == "更新"
    assert win.btn_history.isEnabled() is False


# ==================== 公共任务生命周期契约(TaskLifecycle,真实 QThread) ====================


def _latest_coordinator():
    from file_toolbox.updater.models import UpdateCheckResult, UpdateCheckStatus

    class _Latest:
        def check(self):
            return UpdateCheckResult(UpdateCheckStatus.LATEST)

        def download_and_apply(self, *args, **kwargs):
            raise AssertionError("不应触发下载")

    return _Latest()


def test_result_before_finished_blocks_reentry_and_stale_signals(tab, app, monkeypatch, tmp_path):
    """真实线程:结果先发/finished 后到期间不可重入,旧线程信号被隔离(AC5)。"""
    import threading

    from PySide6.QtCore import QThread, Signal

    release = threading.Event()
    result_seen = threading.Event()

    class HeldWorker(MarkdownConvertWorker):
        def run(self):
            super().run()  # 先真实投递结果信号,再保持线程存活(finished 后到)
            result_seen.set()
            assert release.wait(10)

    monkeypatch.setattr("file_toolbox.gui.dialogs.markdown_tab.MarkdownConvertWorker", HeldWorker)
    a = _mk(tmp_path, "a.md")
    tab._svc = _FakeService(
        result=ConversionResult([ConversionItem(source=a, output=tmp_path / "a.docx")])
    )
    tab._add_paths([a])
    tab._convert()
    worker = tab._worker
    assert isinstance(worker, HeldWorker) and worker.isRunning()
    assert result_seen.wait(5)

    deadline = time.monotonic() + 5
    while tab.ui.lbl_status.text() != "转换完成:成功 1" and time.monotonic() < deadline:
        app.processEvents()
    assert tab.ui.lbl_status.text() == "转换完成:成功 1"
    assert tab._worker is worker, "结果信号不得提前释放线程"
    assert tab.ui.btn_convert.isEnabled() is False, "真实 finished 前不得恢复启动"

    # 不可重入:结果已到但线程未结束,再次点击不能开新任务
    tab._add_paths([_mk(tmp_path, "b.md")])
    tab._convert()
    assert tab._worker is worker
    assert len(tab._svc.calls) == 1

    class LateSignals(QThread):
        finished_ok = Signal(object)
        failed = Signal(str)
        warning = Signal(str)
        progress = Signal(int, int, str)

    late = LateSignals(tab)
    late.finished_ok.connect(tab._on_convert_ok)
    late.failed.connect(tab._on_convert_failed)
    late.warning.connect(tab._on_history_warning)
    late.progress.connect(tab._on_progress)
    late.finished.connect(tab._on_worker_finished)
    previous = tab.ui.lbl_status.text(), tab.ui.table.rowCount()
    late.finished_ok.emit(None)
    late.failed.emit("stale failure")
    late.warning.emit("stale warning")
    late.progress.emit(9, 9, "stale progress")
    late.finished.emit()
    app.processEvents()
    assert (tab.ui.lbl_status.text(), tab.ui.table.rowCount()) == previous
    assert tab._worker is worker

    # 真实 finished 到达后才释放线程引用并恢复控件
    release.set()
    assert worker.wait(5000)
    deadline = time.monotonic() + 5
    while tab._worker is not None and time.monotonic() < deadline:
        app.processEvents()
    assert tab._worker is None
    assert tab.ui.btn_convert.isEnabled() is True
    assert tab.ui.btn_cancel.isEnabled() is False


def test_deferred_close_waits_for_real_finished_and_keeps_outputs(tab, app, monkeypatch, tmp_path):
    """协作关闭:取消请求后等待真实 finished;已完成产物保留在表格(AC5)。"""
    import threading

    release = threading.Event()
    result_seen = threading.Event()

    class HeldWorker(MarkdownConvertWorker):
        def run(self):
            super().run()
            result_seen.set()
            assert release.wait(10)

    monkeypatch.setattr("file_toolbox.gui.dialogs.markdown_tab.MarkdownConvertWorker", HeldWorker)
    a, b = _mk(tmp_path, "a.md"), _mk(tmp_path, "b.md")
    out = tmp_path / "a.docx"
    result = ConversionResult(
        [ConversionItem(source=a, output=out), ConversionItem(source=b, skipped=True)],
        cancelled=True,
    )
    tab._svc = _FakeService(result=result)
    tab._add_paths([a, b])
    tab._convert()
    worker = tab._worker
    assert worker is not None
    tab.show()
    assert result_seen.wait(5)

    event = QCloseEvent()
    before = time.monotonic()
    tab.closeEvent(event)
    assert not event.isAccepted()
    assert time.monotonic() - before < 0.5, "关闭不得阻塞事件循环"
    assert tab.isVisible() and tab.close_pending is True

    # 取消路径:结果先到 → 已完成产物保留展示,收尾弹窗被抑制
    deadline = time.monotonic() + 5
    while tab.ui.table.rowCount() == 0 and time.monotonic() < deadline:
        app.processEvents()
    assert tab.ui.table.rowCount() == 2
    assert tab.ui.table.item(0, 1).text() == "成功"
    assert tab._worker is worker

    release.set()
    assert worker.wait(5000)
    deadline = time.monotonic() + 5
    while tab.isVisible() and time.monotonic() < deadline:
        app.processEvents()
    assert not tab.isVisible()
    assert tab.close_pending is False and tab._worker is None


def test_markdown_tab_disabled_when_lazily_built_during_download(app, monkeypatch, tmp_path):
    """下载锁期间懒构造的业务页(Markdown)按锁状态禁用,更新页保持可用(AC4)。"""
    monkeypatch.chdir(tmp_path)
    from file_toolbox.gui.main_window import MainWindow

    win = MainWindow(_latest_coordinator())
    win._set_business_tabs_locked(True)
    win._tabs.setCurrentIndex(9)
    assert win._markdown_tab is not None and win._markdown_tab.isEnabled() is False
    win._open_update_page()
    assert win._update_tab is not None and win._update_tab.isEnabled() is True


def test_running_markdown_worker_blocks_update_start(app, monkeypatch, tmp_path):
    """Markdown 任务运行中经 _task 登记:更新提交被安全拒绝(主窗口互斥)。"""
    from PySide6.QtCore import QThread

    from file_toolbox.gui.main_window import MainWindow
    from file_toolbox.updater.models import UpdateCheckResult, UpdateCheckStatus

    monkeypatch.chdir(tmp_path)
    win = MainWindow(_latest_coordinator())
    win._tabs.setCurrentIndex(9)
    assert win._markdown_tab is not None
    thread = QThread(win._markdown_tab)  # 父子关系使其进入 findChildren 收尾扫描
    thread.start()
    try:
        assert thread in win._running_business_workers()
        warned: list[str] = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *_a: warned.append("w"))
        win._pending_update = UpdateCheckResult(UpdateCheckStatus.AVAILABLE, version="9.9.9")
        win._start_download()
        assert warned == ["w"] and win._download_request is None
    finally:
        thread.quit()
        assert thread.wait(5000)
