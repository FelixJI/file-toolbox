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

    def close():
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
    service = SimpleNamespace(batch_generate=lambda *args: rows, close=lambda: closed.append(True))
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

    def close():
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
