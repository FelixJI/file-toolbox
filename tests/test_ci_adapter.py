"""file-toolbox 对统一自动化协议的项目专属契约。"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

release_smoke = importlib.import_module("release_smoke")
sync_version = importlib.import_module("sync_version")
check_release_contract = importlib.import_module("check_release_contract")
automation_core = importlib.import_module("automation_core")


def test_top_level_automation_import_does_not_probe_unrelated_scripts_namespace(
    tmp_path: Path,
) -> None:
    foreign_root = tmp_path / "foreign"
    (foreign_root / "scripts").mkdir(parents=True)
    code = (
        "import importlib, sys; "
        f"sys.path[:0] = [{str(SCRIPTS)!r}, {str(foreign_root)!r}]; "
        "importlib.import_module('automation_core'); "
        "raise SystemExit('scripts' in sys.modules)"
    )

    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


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


def _archive(directory: Path, version: str) -> None:
    directory.mkdir(parents=True)
    portable = directory / "FileToolbox-Portable.zip"
    with zipfile.ZipFile(portable, "w") as package:
        package.writestr("FileToolbox.exe", b"smoke")
    full = directory / f"FileToolbox-{version}-full.nupkg"
    with zipfile.ZipFile(full, "w") as package:
        package.writestr("package/services/metadata/core-properties/test.psmdcp", b"metadata")
    feed = directory / "releases.win.json"
    full_sha = hashlib.sha256(full.read_bytes()).hexdigest()
    feed.write_text(
        json.dumps(
            {
                "Assets": [
                    {
                        "PackageId": "FileToolbox",
                        "Version": version,
                        "Type": "Full",
                        "FileName": full.name,
                        "SHA256": full_sha,
                        "Size": full.stat().st_size,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    payloads = [full, portable, feed]
    records = {
        path.name: {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }
        for path in sorted(payloads, key=lambda item: item.name)
    }
    (directory / "checksums.txt").write_text(
        "".join(f"{record['sha256']}  {name}\n" for name, record in records.items()),
        encoding="utf-8",
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
                    }
                ],
                "files": [
                    {
                        "SPDXID": f"SPDXRef-File-{index}",
                        "fileName": name,
                        "checksums": [{"algorithm": "SHA256", "checksumValue": record["sha256"]}],
                    }
                    for index, (name, record) in enumerate(records.items())
                ],
                "relationships": [
                    {
                        "spdxElementId": "SPDXRef-DOCUMENT",
                        "relationshipType": "DESCRIBES",
                        "relatedSpdxElement": "SPDXRef-Package",
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
                    "source_sha": "a" * 40,
                    "assets": records,
                },
            }
        ),
        encoding="utf-8",
    )


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


def test_publish_checkout_keeps_job_token_for_git_tag_push() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/cd.yml").read_text(encoding="utf-8")
    publish_job = workflow.split("\n  publish:\n", maxsplit=1)[1]
    permissions = publish_job.split("\n    permissions:\n", maxsplit=1)[1].split(
        "\n    steps:\n", maxsplit=1
    )[0]
    checkout = publish_job.split("- uses: actions/checkout@", maxsplit=1)[1].split(
        "- uses: actions/setup-python@", maxsplit=1
    )[0]

    assert {line.strip() for line in permissions.splitlines() if line.strip()} == {
        "actions: read",
        "attestations: write",
        "contents: write",
        "id-token: write",
    }
    assert "persist-credentials: true" in checkout
    assert "persist-credentials: false" not in checkout
    assert "token:" not in checkout


def test_mirror_pushes_main_and_only_tags_missing_from_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    class Runner(automation_core.CommandRunner):
        def run(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            if argv[:3] == ["git", "for-each-ref", "--format=%(refname:strip=2)"]:
                return subprocess.CompletedProcess(argv, 0, "v0.1.14\nv0.1.15\n", "")
            if argv[:4] == ["git", "ls-remote", "--refs", "--tags"]:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    "old-tag-object\trefs/tags/v0.1.14\n",
                    "",
                )
            return subprocess.CompletedProcess(argv, 0, "", "")

    config = {
        "schema_version": 1,
        "project": {"component": "test", "repository": "owner/repository"},
        "release": {
            "mirrors": [
                {
                    "name": "mirror",
                    "url_env": "TEST_MIRROR_URL",
                    "user": "cnb",
                    "token_env": "TEST_MIRROR_TOKEN",
                }
            ]
        },
    }
    monkeypatch.setenv("TEST_MIRROR_URL", "https://example.invalid/owner/repository")
    monkeypatch.setenv("TEST_MIRROR_TOKEN", "token")

    automation_core.Automation(tmp_path, config, runner=Runner(tmp_path))._mirror()

    push = next(call for call in calls if call[:2] == ["git", "push"])
    assert "refs/remotes/origin/main:refs/heads/main" in push
    assert "refs/tags/v0.1.15:refs/tags/v0.1.15" in push
    assert "refs/tags/v0.1.14:refs/tags/v0.1.14" not in push
    assert "refs/tags/*:refs/tags/*" not in push


def test_repository_release_contract_is_consistent() -> None:
    assert check_release_contract.check_release_contract() == []
