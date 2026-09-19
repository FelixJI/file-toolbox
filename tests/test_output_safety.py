"""Excel/PDF 使用真实序列化器验证输出竞争和失败清理。"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader, PdfWriter

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core import output_file
from file_toolbox.core.excel_merge import ExcelMergeService
from file_toolbox.core.pdf_sort import PdfSortService, SortOptions


@pytest.fixture(params=["excel", "pdf"])
def output_case(request, make_xlsx, make_text_pdf, tmp_path):
    if request.param == "excel":
        source = make_xlsx("source.xlsx", {"Data": [["payload"]]})
        target = tmp_path / "result.xlsx"

        def run(history=None, output=target):
            result = ExcelMergeService(history).merge([source], output)
            return result.success, result.output, result.error_message

        def read(path):
            workbook = load_workbook(path)
            try:
                return workbook.active["A1"].value
            finally:
                workbook.close()

        return source, target, Workbook, "save", run, read, "payload"

    source = make_text_pdf("source.pdf", ["NO.2", "NO.1"])
    target = tmp_path / "result.pdf"

    def run(history=None, output=target):
        result = PdfSortService(history).sort([source], SortOptions(pattern=r"NO\.(\d+)"), output)
        output = result.sorted_files[0].output if result.sorted_files else None
        return result.success, output, ";".join(item.error for item in result.failed)

    def read(path):
        with path.open("rb") as stream:
            return PdfReader(stream).pages[0].extract_text().strip()

    return source, target, PdfWriter, "write", run, read, "NO.1"


def test_competing_target_created_at_serialization(output_case, monkeypatch):
    source, target, writer_type, method, run, read, expected = output_case
    original_source = source.read_bytes()
    serialize = getattr(writer_type, method)

    def competing_write(writer, destination):
        target.write_bytes(b"other writer")
        return serialize(writer, destination)

    monkeypatch.setattr(writer_type, method, competing_write)
    success, output, error = run()
    assert target.read_bytes() == b"other writer"
    assert success, error
    assert output == target.with_stem("result_1")
    assert read(output) == expected
    assert source.read_bytes() == original_source


def test_partial_serialization_failure_removes_owned_output(output_case, monkeypatch):
    source, target, writer_type, method, run, _, _ = output_case
    original_source = source.read_bytes()

    def failing_write(writer, destination):
        if isinstance(destination, (str, Path)):
            Path(destination).write_bytes(b"partial")
        else:
            destination.write(b"partial")
        raise OSError("serialization interrupted")

    monkeypatch.setattr(writer_type, method, failing_write)
    success, output, error = run()
    assert not success
    assert output is None
    assert "serialization interrupted" in error
    assert list(target.parent.iterdir()) == [source]
    assert source.read_bytes() == original_source


def test_two_writers_commit_different_readable_outputs(output_case, monkeypatch):
    source, target, writer_type, method, run, read, expected = output_case
    original_source = source.read_bytes()
    serialize = getattr(writer_type, method)
    barrier = Barrier(2, timeout=10)

    def simultaneous_write(writer, destination):
        barrier.wait()
        return serialize(writer, destination)

    monkeypatch.setattr(writer_type, method, simultaneous_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert all(success for success, _, _ in results), results
    outputs = {output for _, output, _ in results}
    assert outputs == {target, target.with_stem("result_1")}
    assert all(read(path) == expected for path in outputs)
    assert source.read_bytes() == original_source
    assert set(target.parent.iterdir()) == {source, *outputs}


def test_commit_collision_records_only_actual_numbered_output(output_case, monkeypatch):
    source, target, _, _, run, read, expected = output_case
    target.write_bytes(b"existing")
    first = target.with_stem("result_1")
    first.write_bytes(b"existing numbered")
    second = target.with_stem("result_2")
    commit = output_file.rename_no_replace

    def competing_commit(staging, candidate):
        if candidate == second:
            candidate.write_bytes(b"concurrent numbered")
        return commit(staging, candidate)

    monkeypatch.setattr(output_file, "rename_no_replace", competing_commit)
    history = JsonHistoryStore(history_dir=target.parent / "history")
    success, output, error = run(history)
    assert success, error
    assert output == target.with_stem("result_3")
    assert read(output) == expected
    assert target.read_bytes() == b"existing"
    assert first.read_bytes() == b"existing numbered"
    assert second.read_bytes() == b"concurrent numbered"
    module = "excel_merge" if source.suffix == ".xlsx" else "pdf_sort"
    records = history.get_records(module)
    assert len(records) == 1
    data = records[0]["data"]
    recorded = [data["output"]] if module == "excel_merge" else data["outputs"]
    assert recorded == [str(output)]


def test_output_equal_to_source_keeps_source(output_case):
    source, _, _, _, run, read, expected = output_case
    original = source.read_bytes()
    success, output, error = run(output=source)
    assert success, error
    assert output == source.with_stem("source_1")
    assert source.read_bytes() == original
    assert read(output) == expected


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_failed_write_preserves_competitor_and_reports_cleanup(
    output_case, monkeypatch, cleanup_fails
):
    source, target, writer_type, method, run, _, _ = output_case
    original = source.read_bytes()
    history = JsonHistoryStore(history_dir=target.parent / "history")
    unlink = Path.unlink

    def failing_write(writer, destination):
        target.write_bytes(b"competitor")
        destination.write(b"partial")
        raise OSError("primary write failure")

    def failing_cleanup(path, *args, **kwargs):
        if path.name.startswith(".file-toolbox-"):
            raise PermissionError("cleanup denied")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(writer_type, method, failing_write)
    if cleanup_fails:
        monkeypatch.setattr(Path, "unlink", failing_cleanup)
    success, output, error = run(history)
    assert not success
    assert output is None
    assert "primary write failure" in error
    assert target.read_bytes() == b"competitor"
    assert source.read_bytes() == original
    module = "excel_merge" if source.suffix == ".xlsx" else "pdf_sort"
    assert history.get_records(module) == []
    leftovers = list(target.parent.glob(".file-toolbox-*"))
    if cleanup_fails:
        assert "临时文件清理失败" in error
        assert "cleanup denied" in error
        assert len(leftovers) == 1
        assert str(leftovers[0]) in error
        assert leftovers[0].read_bytes() == b"partial"
    else:
        assert leftovers == []


def test_commit_failure_cleans_staging_without_recording_success(output_case, monkeypatch):
    source, target, _, _, run, _, _ = output_case
    original = source.read_bytes()

    def denied_commit(staging, candidate):
        candidate.write_bytes(b"other writer")
        raise PermissionError("commit denied")

    monkeypatch.setattr(output_file, "rename_no_replace", denied_commit)
    history = JsonHistoryStore(history_dir=target.parent / "history")
    success, output, error = run(history)
    assert not success
    assert output is None
    assert "commit denied" in error
    assert target.read_bytes() == b"other writer"
    assert source.read_bytes() == original
    assert list(target.parent.glob(".file-toolbox-*")) == []
    module = "excel_merge" if source.suffix == ".xlsx" else "pdf_sort"
    assert history.get_records(module) == []
