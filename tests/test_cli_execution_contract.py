"""#81: CLI 确认、执行失败与资源收尾契约。"""

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from file_toolbox.cli.main import app


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_mkdir_preview_then_confirm(tmp_path):
    args = ["mkdir", "--root", str(tmp_path), "--levels", "a/b"]
    preview = CliRunner().invoke(app, args)
    assert preview.exit_code == 0 and "预览" in preview.output
    assert not (tmp_path / "a").exists()
    actual = CliRunner().invoke(app, args + ["--yes"])
    assert actual.exit_code == 0 and (tmp_path / "a/b").is_dir()


def test_mkdir_invalid_strategy_does_not_write(tmp_path):
    result = CliRunner().invoke(
        app, ["mkdir", "--root", str(tmp_path), "--levels", "a", "--on-conflict", "typo"]
    )
    assert result.exit_code != 0 and "on-conflict" in result.output
    assert not (tmp_path / "a").exists()


def test_pdf_preview_does_not_construct_service(tmp_path, monkeypatch):
    source = tmp_path / "a.png"
    source.write_bytes(b"not decoded during preview")

    def forbidden(**kwargs):
        raise AssertionError("preview constructed conversion service")

    monkeypatch.setattr("file_toolbox.cli.pdf_cmd.PDFGeneratorService", forbidden)
    result = CliRunner().invoke(app, ["pdf", str(source)])
    assert result.exit_code == 0 and "预览" in result.output
    assert list(tmp_path.iterdir()) == [source]


def test_rename_partial_conflict_is_failure_with_success_preserved(tmp_path):
    a, b, occupied = [tmp_path / name for name in ("a.txt", "b.txt", "P_a.txt")]
    for p in (a, b, occupied):
        p.write_text(p.name)
    args = ["rename", str(a), str(b), "--op", "add_prefix:text=P_"]
    assert CliRunner().invoke(app, args).exit_code == 0
    result = CliRunner().invoke(app, args + ["--yes"])
    assert result.exit_code == 1
    assert a.exists() and occupied.read_text() == "P_a.txt"
    assert not b.exists() and (tmp_path / "P_b.txt").read_text() == "b.txt"
    assert "1 个文件" in result.output and "P_a.txt" in result.output


@pytest.mark.parametrize("command", ["pdf", "replace"])
@pytest.mark.parametrize("failure", [RuntimeError("processing broke"), KeyboardInterrupt()])
def test_service_closes_without_masking_primary_error(command, failure, tmp_path, monkeypatch):
    closed = []

    def run(*args, **kwargs):
        raise failure

    def close(**kwargs):
        closed.append(True)
        raise RuntimeError("cleanup broke")

    service = SimpleNamespace(
        batch_generate=run,
        validate_operations=lambda ops: (True, ""),
        execute_replace=run,
        close=close,
    )
    symbol = "PDFGeneratorService" if command == "pdf" else "ContentReplaceService"
    monkeypatch.setattr(f"file_toolbox.cli.{command}_cmd.{symbol}", lambda **kwargs: service)
    source = tmp_path / "a.png"
    source.write_text("a")
    args = [command, str(source), "--yes"]
    if command == "replace":
        args += ["--op", "simple_replace:find=a,replace=b"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code != 0 and closed == [True]
    if isinstance(failure, RuntimeError):
        assert result.exception is failure
    assert "cleanup broke" in result.output


def test_pdf_partial_failure_closes_and_retains_paths(tmp_path, monkeypatch):
    closed = []
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.touch()
    b.touch()
    rows = [
        {"source": a, "output": a.with_suffix(".pdf"), "success": True, "error": ""},
        {
            "source": b,
            "output": b.with_suffix(".pdf"),
            "success": False,
            "error": "conversion broke",
        },
    ]
    service = SimpleNamespace(
        batch_generate=lambda *args: rows, close=lambda **kwargs: closed.append(True)
    )
    monkeypatch.setattr("file_toolbox.cli.pdf_cmd.PDFGeneratorService", lambda **kwargs: service)
    result = CliRunner().invoke(app, ["pdf", str(a), str(b), "--yes"])
    assert result.exit_code == 1 and closed == [True]
    assert "成功 1, 失败 1" in result.output and "b.png" in result.output


def test_replace_partial_failure_is_nonzero(tmp_path):
    good, bad = tmp_path / "a.txt", tmp_path / "bad.xyz"
    good.write_text("foo")
    bad.write_text("foo")
    result = CliRunner().invoke(
        app,
        [
            "replace",
            str(good),
            str(bad),
            "--op",
            "simple_replace:find=foo,replace=bar",
            "--yes",
            "--no-backup",
        ],
    )
    assert result.exit_code == 1
    assert good.read_text() == "bar" and bad.read_text() == "foo"
    assert "bad.xyz" in result.output


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--output-mode", "typo"),
        ("--pdf-type", "typo"),
        ("--paper", "bad"),
        ("--orientation", "bad"),
        ("--engine", "bad"),
        ("--dpi", "0"),
    ],
)
def test_pdf_invalid_option_no_output(flag, value, tmp_path):
    source = tmp_path / "a.png"
    source.touch()
    result = CliRunner().invoke(app, ["pdf", str(source), flag, value, "--yes"])
    assert result.exit_code != 0 and flag in result.output
    assert not source.with_suffix(".pdf").exists()


def test_excel_partial_failure_reports_written_output(make_xlsx, tmp_path):
    good = make_xlsx("good.xlsx", {"Sheet": [["v"]]})
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"broken workbook")
    out = tmp_path / "merged.xlsx"
    result = CliRunner().invoke(
        app, ["excel-merge", str(good), str(bad), "--output", str(out), "--yes"]
    )
    assert result.exit_code == 1 and out.is_file()
    assert "bad.xlsx" in result.output and str(out) in result.output


def test_pdf_sort_partial_failure_reports_written_output(make_text_pdf, tmp_path):
    good = make_text_pdf("good.pdf", ["Date: 2", "Date: 1"])
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"broken pdf")
    result = CliRunner().invoke(
        app, ["pdf-sort", str(good), str(bad), "--pattern", r"Date: (\d)", "--yes"]
    )
    assert result.exit_code == 1 and (tmp_path / "good_排序.pdf").is_file()
    assert "bad.pdf" in result.output and "good_排序.pdf" in result.output


def test_invoice_partial_failure_reports_export(ofd_sample, tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("<broken")
    out = tmp_path / "result.json"
    result = CliRunner().invoke(
        app,
        ["invoice", str(ofd_sample), str(bad), "--format", "json", "--output", str(out), "--yes"],
    )
    assert result.exit_code == 1 and out.is_file()
    assert "bad.xml" in result.output and str(out) in result.output


@pytest.mark.parametrize("phase", ["validation", "preview", "success", "close_failure"])
def test_replace_closes_each_exit_path(phase, tmp_path, monkeypatch):
    closed = []

    def close(**kwargs):
        closed.append(True)
        if phase == "close_failure":
            raise RuntimeError("cleanup failed")

    svc = SimpleNamespace(
        validate_operations=lambda ops: (phase != "validation", "invalid"),
        preview_replace=lambda *args: {},
        execute_replace=lambda *args, **kwargs: (1, 1, []),
        close=close,
    )
    monkeypatch.setattr("file_toolbox.cli.replace_cmd.ContentReplaceService", lambda **kwargs: svc)
    source = tmp_path / "a.txt"
    source.write_text("a")
    args = ["replace", str(source), "--op", "simple_replace:find=a,replace=b"]
    if phase != "preview":
        args += ["--yes"]
    result = CliRunner().invoke(app, args)
    assert closed == [True]
    assert (result.exit_code == 0) == (phase in ("preview", "success"))


@pytest.mark.parametrize("command", ["pdf", "replace"])
def test_real_service_cleanup_failure_is_visible(command, tmp_path, monkeypatch, make_text_pdf):
    from file_toolbox.core.batch_pdf.engine_manager import EngineManager
    from file_toolbox.core.batch_replace.file_converter import FileConverterService
    from file_toolbox.core.batch_replace.service import ContentReplaceService

    monkeypatch.setattr(ContentReplaceService, "_get_office_pids", lambda *args: [])

    def fail(*args, **kwargs):
        raise RuntimeError("underlying cleanup failed")

    if command == "pdf":
        source = make_text_pdf("source.pdf", ["x"])
        monkeypatch.setattr(EngineManager, "close", fail)
        args = ["pdf", str(source), "--yes"]
    else:
        source = tmp_path / "source.txt"
        source.write_text("foo")
        monkeypatch.setattr(FileConverterService, "close", fail)
        args = [
            "replace",
            str(source),
            "--op",
            "simple_replace:find=foo,replace=bar",
            "--yes",
            "--no-backup",
        ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code != 0
    assert "underlying cleanup failed" in result.output


@pytest.mark.parametrize("command", ["pdf", "replace", "excel-merge", "pdf-sort", "invoice"])
def test_history_failure_retains_real_completed_result(
    command, tmp_path, monkeypatch, make_text_pdf, make_xlsx, ofd_sample
):
    from file_toolbox.common.history import JsonHistoryStore
    from file_toolbox.core.batch_replace.service import ContentReplaceService

    monkeypatch.setattr(ContentReplaceService, "_get_office_pids", lambda *args: [])

    def fail(*args, **kwargs):
        raise OSError("history disk full")

    monkeypatch.setattr(JsonHistoryStore, "add_record", fail)
    if command == "pdf":
        source = make_text_pdf("source.pdf", ["x"])
        (tmp_path / "source_1.pdf").write_bytes(b"occupied")
        expected = tmp_path / "source_2.pdf"
        args = ["pdf", str(source), "--yes"]
    elif command == "replace":
        expected = tmp_path / "source.txt"
        expected.write_text("foo")
        args = [
            "replace",
            str(expected),
            "--op",
            "simple_replace:find=foo,replace=bar",
            "--yes",
            "--no-backup",
        ]
    elif command == "excel-merge":
        source = make_xlsx("source.xlsx", {"Sheet": [["v"]]})
        expected = tmp_path / "out.xlsx"
        args = ["excel-merge", str(source), "--output", str(expected), "--yes"]
    elif command == "pdf-sort":
        source = make_text_pdf("source.pdf", ["Date: 2", "Date: 1"])
        expected = tmp_path / "out.pdf"
        args = [
            "pdf-sort",
            str(source),
            "--pattern",
            r"Date: (\d)",
            "--output",
            str(expected),
            "--yes",
        ]
    else:
        expected = tmp_path / "out.json"
        args = ["invoice", str(ofd_sample), "--format", "json", "--output", str(expected), "--yes"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1 and expected.is_file()
    assert "history disk full" in result.output
    if command == "replace":
        assert expected.read_text() == "bar" and "处理 1 个文件" in result.output
    else:
        assert expected.name in result.output


def test_engine_strict_close_attempts_all_apps(monkeypatch):
    from file_toolbox.core.batch_pdf.engine_manager import EngineManager

    manager = EngineManager()
    calls = []

    def quit_word():
        calls.append("word")
        raise RuntimeError("Quit failed")

    manager._word_app = SimpleNamespace(Quit=quit_word)
    manager._excel_app = SimpleNamespace(Quit=lambda: calls.append("excel"))
    with pytest.raises(ExceptionGroup, match="Quit failed"):
        manager.close(strict=True)
    assert calls == ["word", "excel"]


def test_converter_strict_close_reports_locked_temp(tmp_path, monkeypatch):
    from pathlib import Path

    from file_toolbox.core.batch_replace.file_converter import FileConverterService

    converter = FileConverterService()
    source = tmp_path / "temporary.docx"
    source.touch()
    converter.temp_files.append(source)
    real_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        if path == source:
            raise PermissionError("locked temporary file")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(ExceptionGroup, match="locked temporary file"):
        converter.close(strict=True)
    assert source in converter.temp_files


@pytest.mark.parametrize("merge_failure", [False, True])
def test_pdf_merge_reports_final_output_only(merge_failure, make_text_pdf, tmp_path, monkeypatch):
    from file_toolbox.core.batch_pdf.service import PDFGeneratorService

    source = make_text_pdf("source.pdf", ["page"])
    if merge_failure:
        monkeypatch.setattr(
            PDFGeneratorService, "merge_pdfs", lambda *args: (False, "merge failed")
        )
    result = CliRunner().invoke(app, ["pdf", str(source), "--output-mode", "merge", "--yes"])
    output = tmp_path / "合并文档.pdf"
    assert result.exit_code == int(merge_failure)
    assert output.exists() != merge_failure
    assert ("成功 0, 失败 1" if merge_failure else "成功 1, 失败 0") in result.output
    assert "source_0.pdf" not in result.output
    assert output.name in result.output


@pytest.mark.parametrize("merge_raises", [False, True])
def test_pdf_temp_cleanup_failure_preserves_output_or_primary(
    merge_raises, make_text_pdf, tmp_path, monkeypatch
):
    from pathlib import Path

    from file_toolbox.core.batch_pdf.engine_manager import EngineManager
    from file_toolbox.core.batch_pdf.service import PDFGeneratorService

    source = make_text_pdf("source.pdf", ["page"])
    real_unlink = Path.unlink
    locked = []
    closed = []
    primary = RuntimeError("merge raised")

    def unlink(path, *args, **kwargs):
        if path.parent.name.startswith("file-toolbox-pdf-"):
            locked.append(path)
            raise PermissionError("locked merge temp")
        return real_unlink(path, *args, **kwargs)

    def merge(*args):
        raise primary

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(EngineManager, "close", lambda *args, **kwargs: closed.append(True))
    if merge_raises:
        monkeypatch.setattr(PDFGeneratorService, "merge_pdfs", merge)
    try:
        result = CliRunner().invoke(app, ["pdf", str(source), "--output-mode", "merge", "--yes"])
        assert result.exit_code == 1 and closed
        assert "locked merge temp" in result.output
        assert locked and all(path.exists() for path in locked)
        if merge_raises:
            assert result.exception is primary
        else:
            assert (tmp_path / "合并文档.pdf").is_file()
            assert "成功 1, 失败 0" in result.output and "合并文档.pdf" in result.output
    finally:
        for path in set(locked):
            real_unlink(path)
            path.parent.rmdir()


def test_pdf_image_intermediate_cleanup_on_conversion_failure(tmp_path, monkeypatch):
    from file_toolbox.core.batch_pdf.service import PDFGeneratorService

    service = PDFGeneratorService()
    paths = []

    def fail(source, output, config):
        output.write_bytes(b"partial editable PDF")
        paths.append(output)
        return False, "conversion failed"

    monkeypatch.setattr(service, "_generate_editable_pdf", fail)
    source = tmp_path / "input.docx"
    source.touch()
    assert service.generate_pdf(source, tmp_path / "out.pdf", {"pdf_type": "image"}) == (
        False,
        "conversion failed",
    )
    assert paths and not paths[0].exists() and not paths[0].parent.exists()
    assert not service.temp_files
    service.close(strict=True)


@pytest.mark.parametrize("failed_format", ["excel", "json"])
def test_invoice_export_failure_retains_completed_paths(failed_format, ofd_sample, tmp_path):
    output = tmp_path / "export.xlsx"
    blocked = output if failed_format == "excel" else output.with_suffix(".json")
    blocked.mkdir()
    result = CliRunner().invoke(
        app, ["invoice", str(ofd_sample), "--format", "both", "--output", str(output), "--yes"]
    )
    assert result.exit_code == 1
    assert "导出失败" in result.output and str(blocked) in result.output
    assert blocked.is_dir()
    if failed_format == "json":
        assert output.is_file() and str(output) in result.output
        assert "已导出 1 个文件" in result.output
    else:
        assert not output.with_suffix(".json").exists()
        assert "已导出 0 个文件" in result.output


@pytest.mark.parametrize("partial_failure", [False, True])
def test_mkdir_history_failure_preserves_counts_once(partial_failure, tmp_path, monkeypatch):
    from file_toolbox.common.history import JsonHistoryStore

    calls = []

    def fail(*args, **kwargs):
        calls.append(True)
        raise OSError("history disk full")

    monkeypatch.setattr(JsonHistoryStore, "add_record", fail)
    args = ["mkdir", "--root", str(tmp_path), "--levels", "a/b", "--yes"]
    if partial_failure:
        (tmp_path / "blocked").write_text("occupied")
        args += ["--levels", "blocked/child"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1 and calls == [True]
    assert (tmp_path / "a/b").is_dir()
    assert "history disk full" in result.output and "完成: 新建 1" in result.output
    assert str(tmp_path / "a/b") in result.output
    if partial_failure:
        assert "创建文件夹失败" in result.output and "blocked" in result.output
        assert (tmp_path / "blocked").read_text() == "occupied"
