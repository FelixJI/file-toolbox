from typer.testing import CliRunner

from file_toolbox.cli.main import app

runner = CliRunner()


def test_version():
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0
    assert "0.1.0" in r.output


def test_help_lists_commands():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    for cmd in ["rename", "mkdir", "pdf", "replace", "gui", "invoice"]:
        assert cmd in r.output


def test_rename_no_op_errors(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    r = runner.invoke(app, ["rename", str(f)])
    assert r.exit_code == 1
    assert "--op" in r.output


def test_rename_preview(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text("x")
    r = runner.invoke(app, ["rename", str(f), "--op", "add_prefix:text=PRE_"])
    assert r.exit_code == 0
    assert "PRE_report.txt" in r.output
    assert "预览模式" in r.output


def test_rename_execute(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text("x")
    r = runner.invoke(app, ["rename", str(f), "--op", "add_prefix:text=PRE_", "--yes"])
    assert r.exit_code == 0
    assert (tmp_path / "PRE_report.txt").exists()


def test_mkdir_from_levels(tmp_path):
    r = runner.invoke(
        app, ["mkdir", "--root", str(tmp_path), "--levels", "部门A/项目1", "--levels", "部门A/项目2"]
    )
    assert r.exit_code == 0
    assert (tmp_path / "部门A" / "项目1").is_dir()
    assert (tmp_path / "部门A" / "项目2").is_dir()


def test_mkdir_replaces_special_chars(tmp_path):
    r = runner.invoke(app, ["mkdir", "--root", str(tmp_path), "--levels", "a*b"])
    assert r.exit_code == 0
    assert (tmp_path / "a_b").is_dir()
