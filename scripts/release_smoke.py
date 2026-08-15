"""检查统一发布候选所需的 file-toolbox 资产结构。"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

_METADATA_ASSETS = {"checksums.txt", "SBOM.spdx.json", "build-identity.json"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _payload_names(version: str) -> set[str]:
    return {
        f"FileToolbox-{version}-full.nupkg",
        "FileToolbox-Portable.zip",
        "releases.win.json",
    }


def _checksum_records(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2:
            raise ValueError("checksums.txt contains an invalid record")
        records[parts[1]] = parts[0].casefold()
    return records


def check_release_smoke(artifacts_dir: Path, version: str) -> None:
    """验证项目构建资产；候选 manifest/SHA256SUMS 由公共 core 校验。"""
    payload_names = _payload_names(version)
    expected_names = payload_names | _METADATA_ASSETS
    actual_names = {path.name for path in artifacts_dir.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise ValueError(
            f"release build assets must be exact: expected={sorted(expected_names)!r}, "
            f"actual={sorted(actual_names)!r}"
        )
    portable = artifacts_dir / "FileToolbox-Portable.zip"
    with zipfile.ZipFile(portable) as package:
        names = package.namelist()
        if "FileToolbox.exe" not in names and "FileToolbox/FileToolbox.exe" not in names:
            raise ValueError("portable archive must contain FileToolbox.exe")
    full = artifacts_dir / f"FileToolbox-{version}-full.nupkg"
    with zipfile.ZipFile(full):
        pass

    checksum_records = _checksum_records(artifacts_dir / "checksums.txt")
    expected_records = {name: _sha256(artifacts_dir / name) for name in sorted(payload_names)}
    if checksum_records != expected_records:
        raise ValueError("checksums.txt must bind every release payload exactly")

    feed = json.loads((artifacts_dir / "releases.win.json").read_text(encoding="utf-8"))
    feed_assets = feed.get("Assets", [])
    if len(feed_assets) != 1:
        raise ValueError("Velopack feed must contain exactly one full package")
    feed_asset = feed_assets[0]
    if (
        feed_asset.get("PackageId") != "FileToolbox"
        or feed_asset.get("Version") != version
        or feed_asset.get("Type") != "Full"
        or feed_asset.get("FileName") != full.name
        or str(feed_asset.get("SHA256", "")).casefold() != _sha256(full)
        or feed_asset.get("Size") != full.stat().st_size
    ):
        raise ValueError("Velopack feed does not bind the full package")

    sbom = json.loads((artifacts_dir / "SBOM.spdx.json").read_text(encoding="utf-8"))
    required_document_fields = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
    }
    if any(sbom.get(key) != value for key, value in required_document_fields.items()):
        raise ValueError("SBOM.spdx.json is not a complete SPDX 2.3 document")
    if not sbom.get("documentNamespace") or not sbom.get("creationInfo", {}).get("created"):
        raise ValueError("SBOM.spdx.json is missing document identity or creation time")
    sbom_records = {
        item.get("fileName"): next(
            (
                checksum.get("checksumValue", "").casefold()
                for checksum in item.get("checksums", [])
                if checksum.get("algorithm") == "SHA256"
            ),
            "",
        )
        for item in sbom.get("files", [])
    }
    if sbom_records != expected_records:
        raise ValueError("SBOM.spdx.json must bind every release payload exactly")
    packages = sbom.get("packages", [])
    relationships = sbom.get("relationships", [])
    if (
        not any(
            package.get("SPDXID") == "SPDXRef-Package"
            and package.get("name") == "file-toolbox"
            and package.get("versionInfo") == version
            for package in packages
        )
        or {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package",
        }
        not in relationships
    ):
        raise ValueError("SBOM.spdx.json must describe the file-toolbox package")
    identity = json.loads((artifacts_dir / "build-identity.json").read_text(encoding="utf-8"))
    build = identity.get("build", {})
    identity_records = {
        name: {
            "sha256": _sha256(artifacts_dir / name),
            "size": (artifacts_dir / name).stat().st_size,
        }
        for name in sorted(payload_names)
    }
    if build.get("assets") != identity_records:
        raise ValueError("build identity must bind every release payload exactly")


def main() -> int:
    try:
        artifacts_dir = Path(os.environ["AUTOMATION_ARTIFACTS_DIR"])
        version = os.environ["AUTOMATION_VERSION"]
        check_release_smoke(artifacts_dir, version)
    except (KeyError, OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
