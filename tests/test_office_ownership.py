"""Office ownership regressions: never mutate or terminate unrelated resources."""

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from file_toolbox.common.office_session import ComSession, init_office_app
from file_toolbox.core.batch_pdf.converters.word_converter import WordConverter
from file_toolbox.core.batch_replace.service import ContentReplaceService


@pytest.fixture(autouse=True)
def _reset_office_kind_evidence():
    """隔离 EngineManager 类级 kind 证据(Dispatch 成功路径现在会登记)。"""
    from file_toolbox.core.batch_pdf.engine_manager import EngineManager

    EngineManager._cached_kind_probes = None
    EngineManager._verified_kinds = {}
    yield
    EngineManager._cached_kind_probes = None
    EngineManager._verified_kinds = {}


def test_shared_powerpoint_keeps_global_ui_properties(monkeypatch):
    import win32com.client

    app = SimpleNamespace(Visible=True, DisplayAlerts=2)
    monkeypatch.setattr(win32com.client, "Dispatch", lambda _: app)
    monkeypatch.setattr(win32com.client, "DispatchEx", lambda _: app)
    init_office_app("PowerPoint.Application")
    assert app.Visible is True
    assert app.DisplayAlerts == 2


def test_replace_close_never_kills_later_unrelated_process(monkeypatch, tmp_path):
    import psutil

    import file_toolbox.core.batch_replace.service as service_module

    processes = []
    monkeypatch.setattr(psutil, "process_iter", lambda _: list(processes))
    process = MagicMock()
    process.name.return_value = "WINWORD.EXE"
    monkeypatch.setattr(psutil, "Process", lambda _: process)
    monkeypatch.setattr(service_module, "get_backup_dir", lambda: tmp_path)
    service = ContentReplaceService()
    processes.append(SimpleNamespace(info={"pid": 12345, "name": "WINWORD.EXE"}))
    service.close(strict=True)
    process.kill.assert_not_called()


def test_export_failure_still_closes_owned_document(tmp_path):
    engine = MagicMock()
    document = engine.init_word.return_value.Documents.Open.return_value
    document.ExportAsFixedFormat.side_effect = RuntimeError("controlled export failure")
    success, error = WordConverter(engine).convert(tmp_path / "fake.docx", tmp_path / "out.pdf", {})
    assert not success
    assert "controlled export failure" in error
    document.Close.assert_called_once_with(False)


def test_com_session_rejects_exit_on_another_thread(monkeypatch):
    from file_toolbox.common import office_session as pythoncom

    monkeypatch.setattr(pythoncom, "_initialize_com", lambda: None)
    uninitialize = MagicMock()
    monkeypatch.setattr(pythoncom, "_uninitialize_com", uninitialize)
    session = ComSession()
    session.__enter__()
    errors = []

    def exit_elsewhere():
        try:
            session.__exit__(None, None, None)
        except RuntimeError as error:
            errors.append(str(error))

    thread = threading.Thread(target=exit_elsewhere)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    try:
        assert errors
        uninitialize.assert_not_called()
    finally:
        session.__exit__(None, None, None)


@pytest.mark.parametrize(
    "prog_id", ["PowerPoint.Application", "KWPS.Application", "Ket.Application", "KWPP.Application"]
)
def test_borrowed_application_is_never_quit(monkeypatch, prog_id):
    import win32com.client

    from file_toolbox.common.office_session import dispose_office_app

    app = MagicMock()
    app.Visible = True
    app.DisplayAlerts = 2
    monkeypatch.setattr(win32com.client, "DispatchEx", lambda _: app)
    result = init_office_app(prog_id)
    dispose_office_app(result, prog_id, raise_on_error=True)
    assert app.Visible is True
    assert app.DisplayAlerts == 2
    app.Quit.assert_not_called()


def test_unclosed_document_prevents_application_quit():
    from file_toolbox.common.office_session import dispose_office_app

    app = MagicMock()
    app.Documents.Count = 1
    with pytest.raises(RuntimeError, match="未关闭文档"):
        dispose_office_app(app, "Word.Application", raise_on_error=True)
    app.Quit.assert_not_called()


def test_already_open_target_is_not_acquired_or_closed(tmp_path):
    from file_toolbox.common.office_session import office_document

    path = tmp_path / "owned-by-another-session.pptx"
    existing = MagicMock()
    existing.FullName = str(path)
    app = MagicMock()
    app.Presentations.__iter__.return_value = iter([existing])
    with (
        pytest.raises(RuntimeError, match="已在 Office 中打开"),
        office_document(app, "Presentations", path),
    ):
        pytest.fail("must not acquire the existing document")
    app.Presentations.Open.assert_not_called()
    existing.Close.assert_not_called()
    app.Quit.assert_not_called()


def test_document_processing_and_cleanup_errors_are_both_reported(tmp_path):
    from file_toolbox.common.office_session import office_document

    app = MagicMock()
    app.Documents.Open.return_value.Close.side_effect = RuntimeError("controlled close failure")
    with (
        pytest.raises(RuntimeError, match="export failure.*close failure"),
        office_document(app, "Documents", tmp_path / "fake.docx"),
    ):
        raise ValueError("controlled export failure")


def test_engine_manager_refuses_cross_thread_reuse_and_close():
    from file_toolbox.core.batch_pdf.engine_manager import EngineManager

    manager = EngineManager()
    app = MagicMock()
    manager._word_app = app
    manager._current_word_engine = "Word.Application"
    manager._office_thread = -1
    with pytest.raises(RuntimeError, match="另一线程"):
        manager.init_word()
    with pytest.raises(RuntimeError, match="创建线程"):
        manager.close(strict=True)
    app.Quit.assert_not_called()
    assert manager._word_app is app


@pytest.mark.parametrize("mode", ["cancel", "timeout"])
def test_blocked_com_returns_before_cooperative_stop(monkeypatch, tmp_path, mode):
    from file_toolbox.common import office_session as pythoncom
    from file_toolbox.core.batch_replace.handlers import word_handler

    entered = threading.Event()
    release = threading.Event()
    cancelled = threading.Event()
    done = threading.Event()
    calls = []
    opened = []

    class Document:
        def Close(self, save=False):
            calls.append(("Close", threading.get_ident()))
            opened.remove(self)

        def Save(self):
            pytest.fail("cancelled/timed-out document must not be saved")

    class Documents:
        @property
        def Count(self):
            return len(opened)

        def __iter__(self):
            return iter(opened)

        def Open(self, path, **kwargs):
            entered.set()
            assert release.wait(5)
            doc = Document()
            opened.append(doc)
            return doc

    app = SimpleNamespace(
        Documents=Documents(), Quit=lambda: calls.append(("Quit", threading.get_ident()))
    )
    monkeypatch.setattr(word_handler, "init_office_app", lambda _: app)
    monkeypatch.setattr(
        pythoncom,
        "_initialize_com",
        lambda: calls.append(("_initialize_com", threading.get_ident())),
    )
    monkeypatch.setattr(
        pythoncom,
        "_uninitialize_com",
        lambda: calls.append(("_uninitialize_com", threading.get_ident())),
    )
    if mode == "timeout":
        monkeypatch.setattr(word_handler, "FILE_OPERATION_TIMEOUT", 0)
    result = {}

    def run():
        try:
            result.update(
                word_handler.WordHandler().batch_replace(
                    [tmp_path / "fake.docx"], [], cancel_check=cancelled.is_set
                )
            )
        finally:
            done.set()

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(5)
        if mode == "cancel":
            cancelled.set()
        assert not done.is_set()  # cooperative request cannot interrupt Documents.Open
        assert [name for name, _ in calls] == ["_initialize_com"]
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert result["success_count"] == 0
    assert any(("取消" if mode == "cancel" else "协作时限") in error for error in result["errors"])
    assert [name for name, _ in calls] == ["_initialize_com", "Close", "Quit", "_uninitialize_com"]
    assert {ident for _, ident in calls} == {thread.ident}


def test_cancel_before_batch_does_not_start_office(monkeypatch, tmp_path):
    from file_toolbox.core.batch_replace.handlers import word_handler

    start = MagicMock(side_effect=AssertionError("must not start Office"))
    monkeypatch.setattr(word_handler, "init_office_app", start)
    result = word_handler.WordHandler().batch_replace(
        [tmp_path / "fake.docx"], [], cancel_check=lambda: True
    )
    assert result["success_count"] == 0
    start.assert_not_called()


def test_ppt_export_uses_fixed_format_pdf_and_explicit_null_print_range(tmp_path):
    from file_toolbox.core.batch_pdf.converters.ppt_converter import PptConverter

    engine = MagicMock()
    document = engine.init_ppt.return_value.Presentations.Open.return_value
    calls = []

    def export(path, format_type, *, PrintRange):
        assert format_type == 2
        assert PrintRange is None
        calls.append(path)

    document.ExportAsFixedFormat.side_effect = export
    success, error = PptConverter(engine).convert(tmp_path / "fake.pptx", tmp_path / "out.pdf", {})
    assert success, error
    assert calls == [str((tmp_path / "out.pdf").absolute())]
    document.Close.assert_called_once_with()


def test_preview_reports_office_failure_instead_of_zero_matches(monkeypatch, tmp_path):
    import file_toolbox.core.batch_replace.service as service_module

    monkeypatch.setattr(service_module, "get_backup_dir", lambda: tmp_path)
    source = tmp_path / "fake.docx"
    source.write_bytes(b"synthetic test input")
    service = ContentReplaceService()
    service._word_handler.read_content = MagicMock(
        side_effect=RuntimeError("controlled Office cleanup failure")
    )
    result = service.preview_replace(
        [source], [{"type": "simple_replace", "params": {"find": "old", "replace": "new"}}]
    )
    assert "controlled Office cleanup failure" in result[source]["status"]
    assert "无匹配" not in result[source]["status"]


def test_engine_rejects_second_start_while_first_initialization_is_blocked(monkeypatch):
    from file_toolbox.core.batch_pdf import engine_manager

    entered = threading.Event()
    release = threading.Event()
    calls = []
    failures = []
    app = MagicMock()
    app.Documents.Count = 0
    manager = engine_manager.EngineManager()
    monkeypatch.setattr(manager, "record_engine_evidence", lambda *_: None)
    monkeypatch.setattr(manager, "_get_prog_id", lambda *_: "Word.Application")

    def initialize(_):
        calls.append(threading.get_ident())
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return app

    monkeypatch.setattr(engine_manager, "init_office_app", initialize)

    def first():
        try:
            manager.init_word()
            manager.close(strict=True)
        except Exception as error:
            failures.append(error)

    thread = threading.Thread(target=first)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(RuntimeError, match="正在初始化或释放"):
            manager.init_word()
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert not failures
    assert calls == [thread.ident]


def test_replace_service_rejects_overlapping_batch_and_close(monkeypatch, tmp_path):
    import file_toolbox.core.batch_replace.service as service_module

    monkeypatch.setattr(service_module, "get_backup_dir", lambda: tmp_path)
    service = ContentReplaceService()
    source = tmp_path / "fake.txt"
    source.write_text("old", encoding="utf-8")
    entered = threading.Event()
    release = threading.Event()
    calls = []
    failures = []

    def count(*_):
        calls.append(threading.get_ident())
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return 1

    monkeypatch.setattr(service, "_count_matches", count)

    def preview():
        try:
            service.preview_replace([source], [])
        except Exception as error:
            failures.append(error)

    thread = threading.Thread(target=preview)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(RuntimeError, match="服务仍在运行"):
            service.preview_replace([source], [])
        with pytest.raises(RuntimeError, match="服务仍在运行"):
            service.close(strict=True)
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert not failures
    assert calls == [thread.ident]


def test_legacy_preview_failure_preserves_existing_sibling(monkeypatch, tmp_path):
    from file_toolbox.core.batch_replace import file_converter

    source = tmp_path / "synthetic.doc"
    source.write_bytes(b"legacy synthetic input")
    sibling = source.with_suffix(".docx")
    sibling.write_bytes(b"pre-existing completed output")
    monkeypatch.setattr(
        file_converter,
        "init_office_app",
        MagicMock(side_effect=RuntimeError("controlled start failure")),
    )
    converter = file_converter.FileConverterService()
    try:
        success, _, error = converter.convert_doc_to_docx(source)
        assert not success and "controlled start failure" in error
        assert sibling.read_bytes() == b"pre-existing completed output"
    finally:
        converter.close(strict=True)


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_legacy_explicit_output_commits_only_after_cleanup(monkeypatch, tmp_path, cleanup_fails):
    from file_toolbox.core.batch_replace import file_converter

    source = tmp_path / "fake.doc"
    source.write_bytes(b"synthetic input")
    output = tmp_path / "completed.docx"
    output.write_bytes(b"original completed output")
    app = MagicMock()
    app.Documents.Count = 0
    document = app.Documents.Open.return_value
    document.SaveAs2.side_effect = lambda path, **_: Path(path).write_bytes(b"new completed output")
    if cleanup_fails:
        app.Quit.side_effect = RuntimeError("controlled cleanup failure")
    monkeypatch.setattr(file_converter, "init_office_app", lambda _: app)
    converter = file_converter.FileConverterService()
    success, result, error = converter.convert_doc_to_docx(source, output)
    assert success is not cleanup_fails
    if cleanup_fails:
        assert "controlled cleanup failure" in error
        assert result == source
    else:
        assert result == output and not error
    converter.close(strict=True)
    assert output.read_bytes() == (
        b"original completed output" if cleanup_fails else b"new completed output"
    )
    assert source.read_bytes() == b"synthetic input"


@pytest.mark.parametrize("close_behavior", ["cancel", "failure"])
def test_saved_word_result_survives_cancel_or_close_failure(monkeypatch, tmp_path, close_behavior):
    from file_toolbox.core.batch_replace.handlers import word_handler

    cancelled = threading.Event()
    app = MagicMock()
    app.Documents.Count = 0
    read_document = MagicMock()
    written_document = MagicMock()
    app.Documents.Open.side_effect = [read_document, written_document]
    if close_behavior == "cancel":
        written_document.Close.side_effect = lambda *args: cancelled.set()
    else:
        written_document.Close.side_effect = RuntimeError("controlled close failure")
    monkeypatch.setattr(word_handler, "init_office_app", lambda _: app)
    handler = word_handler.WordHandler()
    monkeypatch.setattr(handler, "_extract_all_text", lambda _: "old")
    monkeypatch.setattr(handler, "_execute_operation", lambda *_: 1)
    result = handler.batch_replace(
        [tmp_path / "fake.docx"],
        [{"type": "simple_replace", "params": {"find": "old", "replace": "new"}}],
        cancel_check=cancelled.is_set,
    )
    written_document.Save.assert_called_once_with()
    assert result["success_count"] == 1 and result["total_replacements"] == 1
    assert any(
        ("取消" if close_behavior == "cancel" else "controlled close failure") in error
        for error in result["errors"]
    )


def test_nested_com_preserves_existing_apartment_in_fresh_process():
    """原生 Windows 契约：主线程嵌套收尾不能撤销 pywin32 已建立的 apartment。"""
    import subprocess
    import sys

    if sys.platform != "win32":
        pytest.skip("Windows COM contract")
    code = """
import ctypes
import pythoncom
from file_toolbox.common.office_session import ComSession
ole = ctypes.WinDLL("ole32")
ole.CoGetApartmentType.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
ole.CoGetApartmentType.restype = ctypes.c_long

def initialized():
    kind, qualifier = ctypes.c_int(), ctypes.c_int()
    return ole.CoGetApartmentType(ctypes.byref(kind), ctypes.byref(qualifier)) == 0
assert initialized()
with ComSession():
    with ComSession():
        assert initialized()
    assert initialized()
assert initialized()
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_retained_office_session_reports_manual_cleanup_identity(monkeypatch):
    import win32gui
    import win32process

    from file_toolbox.common.office_session import dispose_office_app

    app = MagicMock()
    app.Documents.Count = 1
    app.ActiveWindow.Hwnd = 42
    monkeypatch.setattr(win32gui, "IsWindow", lambda hwnd: hwnd == 42)
    monkeypatch.setattr(win32process, "GetWindowThreadProcessId", lambda hwnd: (10, 1234))
    with pytest.raises(RuntimeError, match=r"Word.Application \(PID 1234\).*保存并关闭"):
        dispose_office_app(app, "Word.Application", raise_on_error=True)
    app.Quit.assert_not_called()
