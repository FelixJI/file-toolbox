"""#79:文本保真、数值校验与真实 CLI 确认边界。"""

import copy

import pytest
from typer.testing import CliRunner

from file_toolbox.cli.main import app
from file_toolbox.cli.op_parser import parse_op
from file_toolbox.core.batch_rename import FileRenameService


@pytest.mark.parametrize("value", ["001", "false", "FALSE", "True", " a,b=001 ", ""])
def test_quoted_values_are_literal_strings(value):
    assert parse_op(f'add_prefix:text="{value}"')["params"]["text"] == value


@pytest.mark.parametrize("value", ["001", "false", "FALSE"])
def test_rename_cli_keeps_literal_text_and_requires_yes(tmp_path, monkeypatch, value):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "a.txt"
    source.write_text("content")
    args = ["rename", str(source), "--op", f'add_prefix:text="{value}"']
    preview = CliRunner().invoke(app, args)
    assert preview.exit_code == 0 and source.exists()
    target = tmp_path / f"{value}a.txt"
    assert not target.exists()
    actual = CliRunner().invoke(app, args + ["--yes"])
    assert actual.exit_code == 0 and target.read_text() == "content"
    assert not source.exists()


@pytest.mark.parametrize("replacement", ["001", "false", "FALSE"])
def test_replace_cli_keeps_literal_find_and_replacement(tmp_path, monkeypatch, replacement):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "sample.txt"
    source.write_text("007", encoding="utf-8")
    args = ["replace", str(source), "--op", f'simple_replace:find="007",replace="{replacement}"']
    preview = CliRunner().invoke(app, args)
    assert preview.exit_code == 0 and source.read_text() == "007"
    actual = CliRunner().invoke(app, args + ["--yes", "--no-backup"])
    assert actual.exit_code == 0 and source.read_text() == replacement


def test_numeric_cli_and_gui_operations_have_same_core_plan(tmp_path):
    source = tmp_path / "a.txt"
    source.write_text("a")
    cli = parse_op('add_number:start="2",digits="3",format=none')
    gui = {"type": "add_number", "params": {"start": 2, "digits": 3, "format": "none"}}
    svc = FileRenameService()
    assert svc.validate_operations([cli])[0]
    assert svc.validate_operations([gui])[0]
    assert cli == gui
    assert svc.plan_operations([source], [cli]) == svc.plan_operations([source], [gui])
    assert svc.plan_operations([source], [cli])[source].target.name == "a002.txt"


@pytest.mark.parametrize(
    "kind,params",
    [
        ("add_prefix", {"text": 2026}),
        ("replace_text", {"find": 2024, "replace": 2026}),
        ("regex_replace", {"pattern": 2024, "replace": 2026}),
    ],
)
def test_rename_shared_boundary_normalizes_numeric_text(kind, params):
    op = {"type": kind, "params": copy.deepcopy(params)}
    assert FileRenameService().validate_operations([op])[0]
    assert op["params"] == {key: str(value) for key, value in params.items()}


@pytest.mark.parametrize("value", [None, [], {}, 1.5, "bad"])
def test_invalid_numeric_parameter_is_diagnostic(value):
    valid, message = FileRenameService().validate_operations(
        [{"type": "add_number", "params": {"start": value, "digits": 3}}]
    )
    assert not valid and "序号参数" in message


@pytest.mark.parametrize("value", [[], {}, None])
def test_invalid_text_type_is_diagnostic(value):
    valid, message = FileRenameService().validate_operations(
        [{"type": "replace_text", "params": {"find": "a", "replace": value}}]
    )
    assert not valid and "replace" in message


@pytest.mark.parametrize("raw", ['"false"', "false", '"FALSE"', "0"])
def test_boolean_configuration_remains_boolean(raw, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "A.txt"
    source.write_text("A")
    op = parse_op(f'replace_text:find=a,replace="001",case_sensitive={raw}')
    svc = FileRenameService()
    assert svc.validate_operations([op])[0]
    assert op["params"]["case_sensitive"] is False
    assert svc.plan_operations([source], [op])[source].target.name == "001.txt"
    result = CliRunner().invoke(
        app,
        [
            "replace",
            str(source),
            "--op",
            f'simple_replace:find=a,replace="001",case_sensitive={raw}',
            "--yes",
            "--no-backup",
        ],
    )
    assert result.exit_code == 0 and source.read_text() == "001"


def test_invalid_boolean_cli_is_diagnostic_without_writing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "a.txt"
    source.write_text("a")
    result = CliRunner().invoke(
        app,
        [
            "rename",
            str(source),
            "--op",
            "replace_text:find=a,replace=b,case_sensitive=maybe",
            "--yes",
        ],
    )
    assert result.exit_code != 0 and "布尔值" in result.output
    assert source.read_text() == "a" and not (tmp_path / "b.txt").exists()


@pytest.mark.parametrize(
    "value,expected", [("00", False), (" 0 ", False), ("+1", True), ("2", True), ("-1", True)]
)
@pytest.mark.parametrize("quoted", [False, True])
@pytest.mark.parametrize(
    "kind,key", [("replace_text", "case_sensitive"), ("regex_replace", "ignore_case")]
)
def test_integer_boolean_spellings_preserve_existing_semantics(
    value, expected, quoted, kind, key, tmp_path
):
    source = tmp_path / "A.txt"
    source.write_text("A")
    raw = f'"{value}"' if quoted else value
    field = "find" if kind == "replace_text" else "pattern"
    op = parse_op(f"{kind}:{field}=a,replace=b,{key}={raw}")
    svc = FileRenameService()
    assert svc.validate_operations([op])[0]
    assert op["params"][key] is expected
    insensitive = expected if key == "ignore_case" else not expected
    assert svc.plan_operations([source], [op])[source].target.name == (
        "b.txt" if insensitive else "A.txt"
    )
