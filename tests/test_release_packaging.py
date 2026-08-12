"""PyInstaller/vpk release exact-set packaging seam。"""

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release_smoke  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_candidate(directory: Path, version: str) -> set[str]:
    directory.mkdir()
    legacy = directory / f"FileToolbox-{version}-win64.zip"
    portable = directory / "FileToolbox-Portable.zip"
    with zipfile.ZipFile(legacy, "w") as package:
        package.writestr("FileToolbox/FileToolbox.exe", b"smoke")
    with zipfile.ZipFile(portable, "w") as package:
        package.writestr("FileToolbox.exe", b"smoke")
    full = directory / f"FileToolbox-{version}-full.nupkg"
    with zipfile.ZipFile(full, "w") as package:
        package.writestr("package/services/metadata/core-properties/x.psmdcp", b"meta")
    setup = directory / "FileToolbox-Setup.exe"
    setup.write_bytes(b"setup")
    feed = directory / "releases.win.json"
    feed.write_text(
        json.dumps(
            {
                "Assets": [
                    {
                        "PackageId": "FileToolbox",
                        "Version": version,
                        "Type": "Full",
                        "FileName": full.name,
                        "SHA256": _sha256(full).upper(),
                        "Size": full.stat().st_size,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    payloads = {legacy.name, portable.name, full.name, setup.name, feed.name}
    (directory / "checksums.txt").write_text(
        "".join(f"{_sha256(directory / name)}  {name}\n" for name in sorted(payloads)),
        encoding="utf-8",
    )
    records = {
        name: {"sha256": _sha256(directory / name), "size": (directory / name).stat().st_size}
        for name in sorted(payloads)
    }
    (directory / "build-identity.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "project": {
                    "component": "file-toolbox",
                    "repository": "FelixJI/file-toolbox",
                    "version": version,
                    "source_sha": "a" * 40,
                },
                "build": {"source_sha": "a" * 40, "assets": records},
            }
        ),
        encoding="utf-8",
    )
    (directory / "SBOM.spdx.json").write_text(
        json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "dataLicense": "CC0-1.0",
                "SPDXID": "SPDXRef-DOCUMENT",
                "documentNamespace": "https://example.invalid/sbom",
                "creationInfo": {"created": "1980-01-01T00:00:00Z"},
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
    identity_path = directory / "build-identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["build"]["archive"] = legacy.name
    identity["build"]["archive_sha256"] = _sha256(legacy)
    identity_path.write_text(json.dumps(identity), encoding="utf-8")
    return payloads | {"checksums.txt", "build-identity.json", "SBOM.spdx.json"}


def test_release_smoke_accepts_exact_bridge_asset_set(tmp_path: Path) -> None:
    expected = _write_candidate(tmp_path / "artifacts", "1.2.3")

    release_smoke.check_release_smoke(tmp_path / "artifacts", "1.2.3")

    assert {path.name for path in (tmp_path / "artifacts").iterdir()} == expected


def test_release_smoke_rejects_missing_or_unexpected_asset(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _write_candidate(artifacts, "1.2.3")
    (artifacts / "unexpected.bin").write_bytes(b"x")

    with pytest.raises(ValueError, match="exact"):
        release_smoke.check_release_smoke(artifacts, "1.2.3")


def test_release_smoke_rejects_feed_that_does_not_bind_full_package(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _write_candidate(artifacts, "1.2.3")
    feed = artifacts / "releases.win.json"
    feed.write_text('{"Assets":[]}', encoding="utf-8")
    feed_sha = _sha256(feed)
    checksums = artifacts / "checksums.txt"
    checksums.write_text(
        "\n".join(
            f"{feed_sha}  releases.win.json" if line.endswith("  releases.win.json") else line
            for line in checksums.read_text(encoding="utf-8").splitlines()
        )
        + "\n",
        encoding="utf-8",
    )
    identity_path = artifacts / "build-identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["build"]["assets"]["releases.win.json"] = {
        "sha256": feed_sha,
        "size": feed.stat().st_size,
    }
    identity_path.write_text(json.dumps(identity), encoding="utf-8")
    sbom_path = artifacts / "SBOM.spdx.json"
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    feed_record = next(item for item in sbom["files"] if item["fileName"] == feed.name)
    feed_record["checksums"] = [{"algorithm": "SHA256", "checksumValue": feed_sha}]
    sbom_path.write_text(json.dumps(sbom), encoding="utf-8")

    with pytest.raises(ValueError, match="feed"):
        release_smoke.check_release_smoke(artifacts, "1.2.3")
