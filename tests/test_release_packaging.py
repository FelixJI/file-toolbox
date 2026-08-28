"""Nuitka/vpk release exact-set packaging seam。"""

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
    portable = directory / f"FileToolbox-v{version}-win-x64.zip"
    with zipfile.ZipFile(portable, "w") as package:
        package.writestr("FileToolbox.exe", b"smoke")
    full = directory / f"FileToolbox-{version}-full.nupkg"
    with zipfile.ZipFile(full, "w") as package:
        package.writestr("package/services/metadata/core-properties/x.psmdcp", b"meta")
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
    payloads = {portable.name, full.name, feed.name}
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
    return payloads | {"checksums.txt", "build-identity.json", "SBOM.spdx.json"}


def test_release_smoke_accepts_exact_velopack_asset_set(tmp_path: Path) -> None:
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


def _rebind_feed(artifacts: Path) -> None:
    """feed 内容被测试改动后,把 feed 自身的新哈希重绑进三份清单。"""
    feed = artifacts / "releases.win.json"
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


def _rewrite_binding_manifests(artifacts: Path, version: str, payloads: set[str]) -> None:
    """按新的 payload 集合整体重写 build-identity 与 SBOM(checksums 由调用方处理)。"""
    records = {
        name: {"sha256": _sha256(artifacts / name), "size": (artifacts / name).stat().st_size}
        for name in sorted(payloads)
    }
    identity_path = artifacts / "build-identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["project"]["version"] = version
    identity["build"]["assets"] = records
    identity_path.write_text(json.dumps(identity), encoding="utf-8")
    sbom_path = artifacts / "SBOM.spdx.json"
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    sbom["packages"][0]["versionInfo"] = version
    sbom["files"] = [
        {
            "SPDXID": f"SPDXRef-File-{index}",
            "fileName": name,
            "checksums": [{"algorithm": "SHA256", "checksumValue": record["sha256"]}],
        }
        for index, (name, record) in enumerate(records.items())
    ]
    sbom_path.write_text(json.dumps(sbom), encoding="utf-8")


def _add_delta(artifacts: Path, version: str, previous: str) -> None:
    """在既有候选上补齐 delta 资产并重写全部绑定清单(模拟 vpk 差量构建)。"""
    delta = artifacts / f"FileToolbox-{version}-delta.nupkg"
    with zipfile.ZipFile(delta, "w") as package:
        package.writestr("delta", b"d")
    payloads = {
        f"FileToolbox-v{version}-win-x64.zip",
        f"FileToolbox-{version}-full.nupkg",
        delta.name,
        "releases.win.json",
    }
    feed = json.loads((artifacts / "releases.win.json").read_text(encoding="utf-8"))
    feed["Assets"].extend(
        [
            {
                "PackageId": "FileToolbox",
                "Version": version,
                "Type": "Delta",
                "FileName": delta.name,
                "SHA256": _sha256(delta).upper(),
                "Size": delta.stat().st_size,
            },
            {
                "PackageId": "FileToolbox",
                "Version": previous,
                "Type": "Full",
                "FileName": f"FileToolbox-{previous}-full.nupkg",
                "SHA256": "0" * 64,
                "Size": 1,
            },
        ]
    )
    (artifacts / "releases.win.json").write_text(json.dumps(feed), encoding="utf-8")
    (artifacts / "checksums.txt").write_text(
        "".join(f"{_sha256(artifacts / name)}  {name}\n" for name in sorted(payloads)),
        encoding="utf-8",
    )
    _rewrite_binding_manifests(artifacts, version, payloads)


def test_release_smoke_accepts_delta_package_and_history_feed(tmp_path: Path) -> None:
    """差量构建形态:当前 full+delta、feed 带上一版 full 历史条目,整体通过。"""
    artifacts = tmp_path / "artifacts"
    _write_candidate(artifacts, "1.2.3")
    _add_delta(artifacts, "1.2.3", "1.2.2")

    release_smoke.check_release_smoke(artifacts, "1.2.3")


def test_release_smoke_rejects_delta_file_without_feed_entry(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _write_candidate(artifacts, "1.2.3")
    _add_delta(artifacts, "1.2.3", "1.2.2")
    feed = json.loads((artifacts / "releases.win.json").read_text(encoding="utf-8"))
    feed["Assets"] = [asset for asset in feed["Assets"] if asset["Type"] != "Delta"]
    (artifacts / "releases.win.json").write_text(json.dumps(feed), encoding="utf-8")
    _rebind_feed(artifacts)

    with pytest.raises(ValueError, match="[Dd]elta"):
        release_smoke.check_release_smoke(artifacts, "1.2.3")


def test_release_smoke_rejects_delta_entry_with_wrong_binding(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _write_candidate(artifacts, "1.2.3")
    _add_delta(artifacts, "1.2.3", "1.2.2")
    feed = json.loads((artifacts / "releases.win.json").read_text(encoding="utf-8"))
    next(asset for asset in feed["Assets"] if asset["Type"] == "Delta")["SHA256"] = "0" * 64
    (artifacts / "releases.win.json").write_text(json.dumps(feed), encoding="utf-8")
    _rebind_feed(artifacts)

    with pytest.raises(ValueError, match="[Dd]elta"):
        release_smoke.check_release_smoke(artifacts, "1.2.3")


def test_release_smoke_rejects_unexpected_delta_version_entry(tmp_path: Path) -> None:
    """feed 里不允许出现非当前版本的 Delta 条目(vpk 只对上一版做差量)。"""
    artifacts = tmp_path / "artifacts"
    _write_candidate(artifacts, "1.2.3")
    _add_delta(artifacts, "1.2.3", "1.2.2")
    feed = json.loads((artifacts / "releases.win.json").read_text(encoding="utf-8"))
    next(asset for asset in feed["Assets"] if asset["Type"] == "Delta")["Version"] = "1.2.2"
    (artifacts / "releases.win.json").write_text(json.dumps(feed), encoding="utf-8")
    _rebind_feed(artifacts)

    with pytest.raises(ValueError, match="[Dd]elta"):
        release_smoke.check_release_smoke(artifacts, "1.2.3")
