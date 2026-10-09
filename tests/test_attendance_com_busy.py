"""考勤 COM 拒绝恢复契约；只使用合成对象，不启动 Excel。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock

import pytest

from file_toolbox.common import office_session
from file_toolbox.core.attendance import excel
from file_toolbox.core.attendance.types import CellRef, SourceLayout

pywintypes = pytest.importorskip("pywintypes")


@pytest.fixture(autouse=True)
def isolate_office_evidence(monkeypatch):
    monkeypatch.setattr(excel, "record_office_session_success", lambda kind, engine: None)


@pytest.fixture
def retry_clock(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(office_session.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(
        office_session.time, "sleep", lambda seconds: setattr(clock, "now", clock.now + seconds)
    )
    return clock


def _busy(hresult=-2147418111):
    return pywintypes.com_error(hresult, "rejected", None, None)


def _source(monkeypatch):
    app = MagicMock()
    app.Workbooks.Count = 0
    workbook = app.Workbooks.Open.return_value
    sheet = MagicMock()
    values = {(2, 1): "张三", (2, 3): "市场部", (2, 7): "正常"}
    sheet.Cells.side_effect = lambda row, col: SimpleNamespace(Value=values.get((row, col)))
    workbook.Worksheets.return_value = sheet
    monkeypatch.setattr(excel, "init_isolated_office_app", lambda prog_id: app)
    return app, workbook, sheet


def _read():
    return excel.ExcelComAdapter().read_source(
        Path("synthetic.xlsx"),
        SourceLayout("Sheet1", CellRef(2, 1), CellRef(2, 3), CellRef(2, 7)),
        1,
    )


@pytest.mark.parametrize("hresult", [-2147418111, -2147417846])
def test_read_source_recovers_worksheet_and_cleanup_rejections(monkeypatch, retry_clock, hresult):
    app, workbook, sheet = _source(monkeypatch)
    workbook.Worksheets.side_effect = [_busy(hresult), sheet]
    workbook.Close.side_effect = [_busy(hresult), None]
    app.Quit.side_effect = [_busy(hresult), None]

    result = _read()

    assert result.employees[0].name == "张三"
    assert workbook.Worksheets.call_count == 2
    assert workbook.Close.call_count == 2
    assert app.Quit.call_count == 2
    assert app.Workbooks.Open.call_count == 1
    assert retry_clock.now == pytest.approx(0.3)


def test_read_source_recovers_value_getter_rejection(monkeypatch, retry_clock):
    _, _, sheet = _source(monkeypatch)
    cell = MagicMock()
    value = PropertyMock(side_effect=[_busy(), "张三"])
    type(cell).Value = value
    default_cells = sheet.Cells.side_effect
    sheet.Cells.side_effect = lambda row, col: (
        cell if (row, col) == (2, 1) else default_cells(row, col)
    )

    assert _read().employees[0].name == "张三"
    assert value.call_count == 2


def test_read_source_non_busy_error_is_not_retried(monkeypatch, retry_clock):
    app, workbook, _ = _source(monkeypatch)
    error = pywintypes.com_error(-2147352567, "other failure", None, None)
    workbook.Worksheets.side_effect = error

    with pytest.raises(pywintypes.com_error) as caught:
        _read()

    assert caught.value is error
    assert workbook.Worksheets.call_count == 1
    workbook.Close.assert_called_once_with(SaveChanges=False)
    app.Quit.assert_called_once_with()
    assert retry_clock.now == 0


def test_retry_stops_at_deadline_and_preserves_last_error(retry_clock):
    operation = MagicMock(side_effect=_busy())

    with pytest.raises(pywintypes.com_error) as caught:
        office_session.retry_com_call(operation)

    assert caught.value is operation.side_effect
    assert retry_clock.now == pytest.approx(5)
    assert operation.call_count <= 52


def test_retry_only_handles_real_com_busy_errors(retry_clock):
    class LookalikeError(RuntimeError):
        hresult = -2147418111

    error = LookalikeError("not COM")
    operation = MagicMock(side_effect=error)
    with pytest.raises(LookalikeError) as caught:
        office_session.retry_com_call(operation)
    assert caught.value is error
    operation.assert_called_once_with()
    assert retry_clock.now == 0


def test_cancel_during_retry_still_recovers_close_and_quit(monkeypatch, retry_clock):
    app, workbook, _ = _source(monkeypatch)
    workbook.Worksheets.side_effect = _busy()
    workbook.Close.side_effect = [_busy(), None]
    app.Quit.side_effect = [_busy(), None]

    with pytest.raises(InterruptedError, match="操作已取消"):
        excel.ExcelComAdapter().read_source(
            Path("synthetic.xlsx"),
            SourceLayout("Sheet1", CellRef(2, 1), CellRef(2, 3), CellRef(2, 7)),
            1,
            cancel_check=lambda: retry_clock.now > 0,
        )

    assert workbook.Worksheets.call_count == 1
    assert workbook.Close.call_count == 2
    assert app.Quit.call_count == 2


def test_write_retry_does_not_replay_successful_insert(monkeypatch, retry_clock):
    app, workbook, sheet = _source(monkeypatch)
    sheet.Rows.return_value.Copy.side_effect = [_busy(), None]
    with excel._excel_workbook(Path("synthetic.xlsx"), read_only=False):
        excel._adjust_employee_rows(sheet, 7, 16)
    sheet.Rows.return_value.Insert.assert_called_once_with(CopyOrigin=0)
    assert sheet.Rows.return_value.Copy.call_count == 2
    app.Workbooks.Open.assert_called_once()
    workbook.Close.assert_called_once_with(SaveChanges=False)


def test_init_property_rejection_retries_without_dispatching_again(monkeypatch, retry_clock):
    import win32com.client

    app = MagicMock()
    app.Workbooks.Count = 0
    visible = PropertyMock(side_effect=[_busy(), None])
    type(app).Visible = visible
    dispatch = MagicMock(return_value=app)
    monkeypatch.setattr(win32com.client, "DispatchEx", dispatch)

    assert office_session.init_isolated_office_app("Excel.Application") is app
    assert visible.call_count == 2
    dispatch.assert_called_once_with("Excel.Application")
    app.Quit.assert_not_called()


def test_init_failed_property_still_recovers_cleanup(monkeypatch, retry_clock):
    import win32com.client

    app = MagicMock()
    app.Workbooks.Count = 0
    error = RuntimeError("bad property")
    type(app).Visible = PropertyMock(side_effect=error)
    app.Quit.side_effect = [_busy(), None]
    monkeypatch.setattr(win32com.client, "DispatchEx", lambda prog_id: app)

    with pytest.raises(RuntimeError) as caught:
        office_session.init_isolated_office_app("Excel.Application")
    assert caught.value is error
    assert app.Quit.call_count == 2


def test_cleanup_busy_count_recovers_but_nonempty_app_is_kept(retry_clock):
    app = MagicMock()
    type(app.Workbooks).Count = PropertyMock(side_effect=[_busy(), 1])

    with pytest.raises(RuntimeError, match="未关闭文档"):
        office_session.dispose_office_app(app, "Excel.Application", raise_on_error=True)

    app.Quit.assert_not_called()


def test_write_property_retry_does_not_replay_number_format(retry_clock):
    sheet = MagicMock()
    target = sheet.Range.return_value
    number_format = PropertyMock()
    value = PropertyMock(side_effect=[_busy(), None])
    type(target).NumberFormat = number_format
    type(target).Value = value

    excel._write_column(sheet, CellRef(7, 3), ("001",), as_text=True)

    number_format.assert_called_once_with("@")
    assert value.call_count == 2
    assert value.call_args_list[0] == value.call_args_list[1]
    assert value.call_args.args == ((("001",),),)
    sheet.Range.assert_called_once()


def test_cleanup_permanent_close_rejection_keeps_nonempty_app(retry_clock):
    app = MagicMock()
    app.Workbooks.Count = 1
    workbook = MagicMock()
    workbook.Close.side_effect = _busy()

    error = excel._release_excel(workbook, app)

    assert isinstance(error, RuntimeError)
    assert "关闭工作簿失败" in str(error)
    assert "未关闭文档" in str(error)
    assert retry_clock.now == pytest.approx(5)
    app.Quit.assert_not_called()


def test_cleanup_permanent_quit_rejection_reports_error(retry_clock):
    app = MagicMock()
    app.Workbooks.Count = 0
    app.Quit.side_effect = _busy()

    error = excel._release_excel(None, app)

    assert isinstance(error, RuntimeError)
    assert "关闭 Office 应用失败" in str(error)
    assert retry_clock.now == pytest.approx(5)


def test_cancel_context_restores_after_base_exception(monkeypatch):
    _source(monkeypatch)

    def parent_check():
        return False

    token = excel._cancel_check.set(parent_check)
    try:
        with (
            pytest.raises(KeyboardInterrupt),
            excel._excel_workbook(
                Path("synthetic.xlsx"), read_only=True, cancel_check=lambda: False
            ),
        ):
            raise KeyboardInterrupt
        assert excel._cancel_check.get() is parent_check
    finally:
        excel._cancel_check.reset(token)
