"""只读版本信息工具测试。"""

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bump_version  # noqa: E402


@pytest.mark.parametrize(
    "version",
    ["1.2.3", "1.2.3a1", "1.2.3-rc.1"],
)
def test_validate_pep440_accepts_versions(version: str) -> None:
    assert bump_version.validate_pep440(version)


@pytest.mark.parametrize("version", ["", "not-a-version", "1.2.x", "1..2"])
def test_validate_pep440_rejects_invalid_versions(version: str) -> None:
    assert not bump_version.validate_pep440(version)


def test_read_pyproject_version(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "file-toolbox"\nversion = "0.3.7"\n',
        encoding="utf-8",
    )
    assert bump_version.read_pyproject_version(pyproject) == "0.3.7"


def test_read_pyproject_version_requires_version(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "file-toolbox"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        bump_version.read_pyproject_version(pyproject)


def test_current_command_reads_configured_pyproject(monkeypatch, tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "2.4.6"\n', encoding="utf-8")
    monkeypatch.setattr(bump_version, "_PYPROJECT", pyproject)

    result = CliRunner().invoke(bump_version.cli, ["current"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "2.4.6"
