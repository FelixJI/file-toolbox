"""file-toolbox 对统一自动化协议的项目专属契约。"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

release_smoke = importlib.import_module("release_smoke")
sync_version = importlib.import_module("sync_version")
check_release_contract = importlib.import_module("check_release_contract")


def test_sync_version_updates_only_derived_lockfile(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "file-toolbox"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "file-toolbox"\nversion = "0.1.0" # generated\nsource = { editable = "." }\n',
        encoding="utf-8",
    )
    sync_version.sync_version(tmp_path, "2.3.4")
    assert 'version = "2.3.4"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "2.3.4" # generated' in (tmp_path / "uv.lock").read_text(encoding="utf-8")


def _archive(directory: Path, version: str) -> Path:
    directory.mkdir(parents=True)
    archive = directory / f"FileToolbox-{version}-win64.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("FileToolbox/FileToolbox.exe", b"smoke")
    (directory / "checksums.txt").write_text(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="utf-8"
    )
    (directory / "SBOM.spdx.json").write_text(
        json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "dataLicense": "CC0-1.0",
                "SPDXID": "SPDXRef-DOCUMENT",
                "name": "file-toolbox-1.0.0-build",
                "documentNamespace": "https://example.invalid/file-toolbox/1.0.0",
                "creationInfo": {
                    "created": "1980-01-01T00:00:00Z",
                    "creators": ["Tool: test"],
                },
                "packages": [
                    {
                        "SPDXID": "SPDXRef-Package",
                        "name": "file-toolbox",
                        "versionInfo": version,
                        "checksums": [
                            {
                                "algorithm": "SHA256",
                                "checksumValue": hashlib.sha256(archive.read_bytes()).hexdigest(),
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (directory / "build-identity.json").write_text(
        json.dumps(
            {
                "project": {
                    "component": "file-toolbox",
                    "repository": "FelixJI/file-toolbox",
                    "version": version,
                    "source_sha": "a" * 40,
                },
                "build": {
                    "archive": archive.name,
                    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    "source_sha": "a" * 40,
                },
            }
        ),
        encoding="utf-8",
    )
    return archive


def test_release_smoke_validates_project_archive_sbom_and_build_identity(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _archive(artifacts, "1.0.0")
    release_smoke.check_release_smoke(artifacts, "1.0.0")


def test_release_smoke_rejects_bad_build_identity(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _archive(artifacts, "1.0.0")
    (artifacts / "build-identity.json").write_text('{"build":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="build identity"):
        release_smoke.check_release_smoke(artifacts, "1.0.0")


def test_release_smoke_rejects_incomplete_spdx(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _archive(artifacts, "1.0.0")
    (artifacts / "SBOM.spdx.json").write_text('{"spdxVersion":"SPDX-2.3"}', encoding="utf-8")
    with pytest.raises(ValueError, match="complete SPDX"):
        release_smoke.check_release_smoke(artifacts, "1.0.0")


def test_project_config_has_required_protocol_steps_and_mirrors() -> None:
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / ".ci" / "project.json").read_text(encoding="utf-8"))
    assert list(config["ci"])[-2:] == ["release_build", "release_smoke"]
    coverage_targets = [
        argument
        for command in config["ci"]["e2e"]
        for argument in command
        if argument.startswith("--cov=")
    ]
    assert coverage_targets == ["--cov=file_toolbox.core", "--cov=file_toolbox"]
    assert config["ci"]["release_smoke"] == [["python", "scripts/release_smoke.py"]]
    mirrors = {mirror["name"]: mirror for mirror in config["release"]["mirrors"]}
    assert mirrors["gitee"]["url_env"] == "GITEE_URL"
    assert "user" not in mirrors["gitee"]
    assert mirrors["cnb"]["token_env"] == "CNB_TOKEN"
    assert mirrors["cnb"]["user"] == "cnb"
    assert config["release"]["identity_asset"] == "build-identity.json"
    assert "SHA256SUMS" not in config["release"]["required_assets"]
    assert "release-manifest.json" not in config["release"]["required_assets"]


def test_only_canonical_workflows_remain() -> None:
    workflows = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    assert {path.name for path in workflows.glob("*.yml")} == {"ci.yml", "cd.yml"}


def test_repository_release_contract_is_consistent() -> None:
    assert check_release_contract.check_release_contract() == []
