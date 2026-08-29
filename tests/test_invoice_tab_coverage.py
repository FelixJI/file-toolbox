"""invoice_tab GUI 测试:文件管理、解析、表格填充、导出(mock QFileDialog)。

解析经后台 worker(子项 4.3),_parse 不再同步填充。测试用 _wait_parse 等待
worker 线程结束并 flush 事件,使跨线程的 finished_ok 槽在主线程执行后再断言。
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(app, tmp_path):
    t = InvoiceTab()
    t._history = JsonHistoryStore(tmp_path)
    return t


def _wait_parse(tab) -> None:
    """等待 tab._parse 启动的后台 worker 完成,并投递 finished_ok 槽到主线程。

    worker 解析真实小 XML 文件极快,wait(5s) 即结束;之后 processEvents 让
    queued 的 finished_ok(_on_parse_ok) 在主线程跑,完成表格填充。
    用 QApplication.instance() 取当前应用(与各 test 的 app fixture 同一实例)。
    """
    worker = tab._parse_worker
    if worker is None:
        return
    worker.wait(5000)
    # 跨线程 queued 信号需主线程事件循环 flush
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
        if tab._parse_worker is not None:
            app.processEvents()


def _xml(path: Path, num: str) -> Path:
    path.write_text(
        f'<?xml version="1.0"?><EInvoice>'
        f"<Header><InherentLabel><GeneralOrSpecialVAT><LabelName>增值税专用发票</LabelName></GeneralOrSpecialVAT></InherentLabel></Header>"
        f"<EInvoiceData><SellerInformation><SellerName>s{num}</SellerName><SellerIdNum>sid</SellerIdNum></SellerInformation>"
        f"<BuyerInformation><BuyerName>b{num}</BuyerName><BuyerIdNum>bid</BuyerIdNum></BuyerInformation>"
        f"<BasicInformation><TotalAmWithoutTax>1</TotalAmWithoutTax><TotalTaxAm>0.13</TotalTaxAm>"
        f"<TotalTax-includedAmount>1.13</TotalTax-includedAmount>"
        f"<TotalTax-includedAmountInChinese>圆</TotalTax-includedAmountInChinese>"
        f"<Drawer>x</Drawer></BasicInformation></EInvoiceData>"
        f"<TaxSupervisionInfo><InvoiceNumber>{num}</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>"
        f"</EInvoice>",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# 文件管理
# ---------------------------------------------------------------------------


def test_add_files(tab, monkeypatch, tmp_path):
    f1 = _xml(tmp_path / "1.xml", "1")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(f1)], ""))
    tab._add_files()
    assert len(tab._files) == 1
    assert tab.ui.list_files.count() == 1


def test_add_files_multiple(tab, monkeypatch, tmp_path):
    f1 = _xml(tmp_path / "1.xml", "1")
    f2 = _xml(tmp_path / "2.xml", "2")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(f1), str(f2)], ""))
    tab._add_files()
    assert len(tab._files) == 2


def test_add_folder_non_recursive(tab, monkeypatch, tmp_path):
    _xml(tmp_path / "1.xml", "1")
    (tmp_path / "ignore.txt").write_text("x")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    tab._add_folder()
    assert len(tab._files) == 1
    assert tab._files[0].suffix == ".xml"


def test_add_folder_recursive(tab, monkeypatch, tmp_path):
    _xml(tmp_path / "1.xml", "1")
    sub = tmp_path / "sub"
    sub.mkdir()
    _xml(sub / "2.xml", "2")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    tab._add_folder()
    assert len(tab._files) == 2


def test_add_folder_cancelled(tab, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    tab._add_folder()
    assert tab._files == []


def test_add_folder_dedup(tab, monkeypatch, tmp_path):
    """重复文件不重复加入(行 75-77)。"""
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files.append(f1)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    tab._add_folder()
    assert len(tab._files) == 1  # 不重复


def test_clear(tab, tmp_path):
    tab._files = [tmp_path / "a.xml"]
    tab.ui.list_files.addItem("a.xml")
    tab._result = object()  # 非 None
    tab._clear()
    assert tab._files == []
    assert tab.ui.list_files.count() == 0
    assert tab._result is None
    assert tab.ui.btn_export.isEnabled() is False
    assert tab.ui.lbl_status.text() == "就绪"


def test_browse_outdir(tab, monkeypatch, tmp_path):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    tab._browse_outdir()
    assert tab.ui.edit_outdir.text() == str(tmp_path)


def test_browse_outdir_cancelled(tab, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    tab._browse_outdir()
    assert tab.ui.edit_outdir.text() == ""


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def test_parse_no_files_warns(tab, monkeypatch):
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(1) or QMessageBox.StandardButton.Ok
    )
    tab._parse()
    assert warned


def test_parse_success(tab, tmp_path):
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    _wait_parse(tab)
    assert tab._result is not None
    assert len(tab._result.invoices) == 1
    assert tab.ui.btn_export.isEnabled()
    assert tab.ui.table.rowCount() == 1


def test_parse_mixed_results(tab, tmp_path):
    """含坏文件 → failed 非空,status 反映。"""
    f1 = _xml(tmp_path / "1.xml", "1")
    bad = tmp_path / "bad.xml"
    bad.write_text("not xml", encoding="utf-8")
    tab._files = [f1, bad]
    tab._parse()
    _wait_parse(tab)
    assert len(tab._result.failed) == 1


def test_populate_table_duplicate_color(tab, tmp_path):
    """mark 策略下重复行黄底(行 135-136)。

    直接构造 ParseResult 让 _populate_table 渲染重复标记行。
    """
    from file_toolbox.core.invoice.types import Invoice, ParseResult

    inv1 = Invoice(
        invoice_number="111",
        invoice_type="",
        issue_date="",
        seller_name="",
        seller_tax_id="",
        seller_addr="",
        seller_tel="",
        seller_bank="",
        seller_account="",
        buyer_name="",
        buyer_tax_id="",
        buyer_addr="",
        buyer_tel="",
        buyer_bank="",
        buyer_account="",
        amount_without_tax="",
        tax_amount="",
        amount_with_tax="",
        amount_chinese="",
        drawer="",
        remark="",
        items=[],
        source_file="a.xml",
        parse_method="xml",
    )
    inv2 = Invoice(
        invoice_number="111",
        invoice_type="",
        issue_date="",
        seller_name="",
        seller_tax_id="",
        seller_addr="",
        seller_tel="",
        seller_bank="",
        seller_account="",
        buyer_name="",
        buyer_tax_id="",
        buyer_addr="",
        buyer_tel="",
        buyer_bank="",
        buyer_account="",
        amount_without_tax="",
        tax_amount="",
        amount_with_tax="",
        amount_chinese="",
        drawer="",
        remark="",
        items=[],
        source_file="b.xml",
        parse_method="xml",
        is_duplicate=True,
    )
    tab._result = ParseResult(invoices=[inv1, inv2], duplicates=[], failed=[])
    tab._populate_table()
    assert tab.ui.table.rowCount() == 2


def test_populate_table_pdf_color(tab):
    """pdf 解析行灰底(行 137-138)。"""
    from file_toolbox.core.invoice.types import Invoice, ParseResult

    inv = Invoice(
        invoice_number="1",
        invoice_type="",
        issue_date="",
        seller_name="",
        seller_tax_id="",
        seller_addr="",
        seller_tel="",
        seller_bank="",
        seller_account="",
        buyer_name="",
        buyer_tax_id="",
        buyer_addr="",
        buyer_tel="",
        buyer_bank="",
        buyer_account="",
        amount_without_tax="",
        tax_amount="",
        amount_with_tax="",
        amount_chinese="",
        drawer="",
        remark="",
        items=[],
        source_file="a.pdf",
        parse_method="pdf",
    )
    tab._result = ParseResult(invoices=[inv], duplicates=[], failed=[])
    tab._populate_table()
    assert tab.ui.table.rowCount() == 1


def test_dedupe_strategy_and_format(tab):
    """_dedupe_strategy / _format 委托 controller(行 94-98)。"""
    s = tab._dedupe_strategy()
    assert isinstance(s, str)
    f = tab._format()
    assert isinstance(f, str)


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------


def test_export_no_data_warns(tab, monkeypatch):
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(1) or QMessageBox.StandardButton.Ok
    )
    tab._result = None
    tab._export()
    assert warned


def test_export_success(tab, monkeypatch, tmp_path):
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    _wait_parse(tab)
    tab.ui.edit_outdir.setText(str(tmp_path / "out"))
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    tab._export()
    assert (tmp_path / "out" / "发票结果.xlsx").exists()
    assert info_calls


def test_export_failure_critical(tab, monkeypatch, tmp_path):
    """导出抛异常 → critical 提示(行 160-162)。"""
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    _wait_parse(tab)
    tab.ui.edit_outdir.setText(str(tmp_path))
    # mock svc.export 抛异常
    tab._svc = type(tab._svc)()
    monkeypatch.setattr(
        tab._svc, "export", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    crit_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *a, **k: crit_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    tab._export()
    assert crit_calls


def test_export_default_outdir(tab, monkeypatch, tmp_path):
    """输出框为空且无上次目录 → 默认首个源文件所在目录(回归:曾落到"."即程序目录)。"""
    monkeypatch.chdir(tmp_path)  # settings(cwd-scoped)与回退目录均隔离在 tmp_path
    src = tmp_path / "src"
    src.mkdir()
    f1 = _xml(src / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    _wait_parse(tab)
    tab.ui.edit_outdir.setText("")
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )
    tab._export()
    assert (src / "发票结果.xlsx").exists()
    assert info_calls


def test_export_reuses_last_output_dir(tab, monkeypatch, tmp_path):
    """输出框为空 → 复用上次成功导出的目录(chdir 隔离 settings)。"""
    monkeypatch.chdir(tmp_path)
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    _wait_parse(tab)
    out1 = tmp_path / "out1"
    tab.ui.edit_outdir.setText(str(out1))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    tab._export()
    assert (out1 / "发票结果.xlsx").exists()

    # 第二次导出清空输入框:应落回上次目录 out1,而非 "." 或源文件目录
    tab.ui.edit_outdir.setText("")
    tab._export()
    assert (out1 / "发票结果.xlsx").exists()
    assert not (tmp_path / "发票结果.xlsx").exists()


def test_export_stale_last_dir_falls_back_to_source_dir(tab, monkeypatch, tmp_path):
    """上次目录已被删除 → 回退到首个源文件所在目录。"""
    monkeypatch.chdir(tmp_path)
    from file_toolbox.common import settings

    settings.set("invoice/last_output_dir", str(tmp_path / "gone"))
    src = tmp_path / "src"
    src.mkdir()
    f1 = _xml(src / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    _wait_parse(tab)
    tab.ui.edit_outdir.setText("")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    tab._export()
    assert (src / "发票结果.xlsx").exists()


def test_export_failure_does_not_persist_outdir(tab, monkeypatch, tmp_path):
    """导出失败 → 不记住目录(下次仍按默认解析)。"""
    monkeypatch.chdir(tmp_path)
    from file_toolbox.common import settings

    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files = [f1]
    tab._parse()
    _wait_parse(tab)
    tab.ui.edit_outdir.setText(str(tmp_path / "bad"))
    monkeypatch.setattr(
        tab._svc, "export", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: QMessageBox.StandardButton.Ok)
    tab._export()
    assert settings.get("invoice/last_output_dir") is None


# ---------------------------------------------------------------------------
# closeEvent:解析中关闭窗口应停止 worker(防泄漏)
# ---------------------------------------------------------------------------


def test_close_event_stops_running_parse_worker(tab):
    """解析中触发 closeEvent 应 cancel + wait 停止 _parse_worker,不泄漏。

    回归:InvoiceTab 曾无 closeEvent,关闭窗口(main_window.closeEvent 仅对
    hasattr(tab,'closeEvent') 的 tab 调用)时 _parse_worker 仍在后台跑,
    持有 self 为 parent,进程退出可能崩溃/泄漏。补 closeEvent 协作式停止 worker。
    """
    from PySide6.QtGui import QCloseEvent

    cancelled = []
    waited = []

    class _FakeRunningWorker:
        """模拟正在运行的 worker:isRunning True,cancel/wait 可记录调用。"""

        def isRunning(self) -> bool:
            return True

        def cancel(self) -> None:
            cancelled.append(1)

        def quit(self) -> None:  # 与 _stop_worker 一致:无事件循环 worker 仍调用
            pass

        def wait(self, timeout_ms: int = 0) -> bool:
            waited.append(timeout_ms)
            return True  # 模拟 promptly 停止

    tab._parse_worker = _FakeRunningWorker()  # type: ignore[assignment]
    tab.closeEvent(QCloseEvent())
    assert cancelled, "closeEvent 应调用 worker.cancel() 停止解析"
    assert waited, "closeEvent 应 wait() 等待 worker 退出"
    assert tab._parse_worker is None


# ---------------------------------------------------------------------------
# 重复点击防护与解析失败处理(覆盖 invoice_tab.py 第 111、144-149 行)
# ---------------------------------------------------------------------------


def test_parse_skipped_when_worker_running(tab, monkeypatch, tmp_path):
    """重复点击防护:_parse_worker 仍 running 时直接 return,不新建 worker(第 111 行)。

    _parse() 在 _files 非空时检查 _parse_worker.isRunning():为 True 则提前 return,
    不构造新 worker、不弹"请先添加发票文件"警告。注入一个 isRunning→True 的假 worker
    即可稳定触发(与 test_close_event_stops_running_parse_worker 同款手法)。
    """
    f1 = _xml(tmp_path / "1.xml", "1")
    tab._files = [f1]

    class _FakeRunningWorker:
        def isRunning(self) -> bool:
            return True

    tab._parse_worker = _FakeRunningWorker()  # type: ignore[assignment]

    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(1) or QMessageBox.StandardButton.Ok
    )
    constructed = []
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.invoice_tab.InvoiceParseWorker",
        lambda *a, **k: constructed.append(1),
    )

    tab._parse()

    # 没走"无文件"警告分支
    assert warned == []
    # 没新建 worker(证明提前 return,第 111 行已执行)
    assert constructed == []
    # 引用未替换(仍是注入的假 worker)
    assert isinstance(tab._parse_worker, _FakeRunningWorker)


def test_on_parse_failed_no_prior_result_disables_export(tab, monkeypatch):
    """解析失败且无先前结果 → btn_export 禁用(第 144-149 行,False 分支)。

    _on_parse_failed 直接作为普通方法调用即可覆盖逻辑,不必走真实 worker 线程+信号
    投递(那条路更脆)。第 147 行 _result is None → btn_export.setEnabled(False)。
    """
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(1) or QMessageBox.StandardButton.Ok
    )
    tab._result = None
    tab._parse_worker = object()  # type: ignore[assignment]  # 模拟曾有 worker

    tab._on_parse_failed("解析爆炸")

    assert tab._parse_worker is None
    assert tab.ui.btn_parse.isEnabled() is True
    assert tab.ui.btn_export.isEnabled() is False  # _result is None
    assert tab.ui.lbl_status.text() == "解析失败"
    assert warned, "应弹出失败警告"


def test_on_parse_failed_with_prior_result_keeps_export(tab, monkeypatch):
    """解析失败但曾有成功结果 → btn_export 保留可导出(第 147 行,True 分支)。

    失败时按已有结果重置导出按钮:若曾解析成功(invoices 非空)则保留可导出状态,
    允许用户基于上一次成功结果导出。这是与上一条相反的 True 分支。
    """
    from file_toolbox.core.invoice.types import Invoice, ParseResult

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    inv = Invoice(
        invoice_number="1",
        invoice_type="",
        issue_date="",
        seller_name="",
        seller_tax_id="",
        seller_addr="",
        seller_tel="",
        seller_bank="",
        seller_account="",
        buyer_name="",
        buyer_tax_id="",
        buyer_addr="",
        buyer_tel="",
        buyer_bank="",
        buyer_account="",
        amount_without_tax="",
        tax_amount="",
        amount_with_tax="",
        amount_chinese="",
        drawer="",
        remark="",
        items=[],
        source_file="a.xml",
        parse_method="xml",
    )
    tab._result = ParseResult(invoices=[inv], duplicates=[], failed=[])
    tab._parse_worker = object()  # type: ignore[assignment]

    tab._on_parse_failed("err")

    # 保留先前可导出状态
    assert tab.ui.btn_export.isEnabled() is True
    assert tab.ui.lbl_status.text() == "解析失败"
