"""检查统一发布候选所需的 file-toolbox 资产结构。"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expect_zip(artifacts_dir: Path, version: str) -> Path:
    archive = artifacts_dir / f"FileToolbox-{version}-win64.zip"
    if not archive.is_file():
        raise ValueError(f"missing release archive: {archive}")
    with zipfile.ZipFile(archive) as package:
        if "FileToolbox/FileToolbox.exe" not in package.namelist():
            raise ValueError("release archive must contain FileToolbox/FileToolbox.exe")
    checksums = artifacts_dir / "checksums.txt"
    expected = f"{_sha256(archive)}  {archive.name}"
    if (
        not checksums.is_file()
        or expected not in checksums.read_text(encoding="utf-8").splitlines()
    ):
        raise ValueError("checksums.txt must contain the release archive SHA-256")
    return archive


def check_release_smoke(artifacts_dir: Path, version: str) -> None:
    """验证项目构建资产；候选 manifest/SHA256SUMS 由公共 core 校验。"""
    archive = _expect_zip(artifacts_dir, version)
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
    packages = sbom.get("packages", [])
    archive_sha256 = _sha256(archive)
    if not any(
        package.get("name") == "file-toolbox"
        and package.get("versionInfo") == version
        and {"algorithm": "SHA256", "checksumValue": archive_sha256} in package.get("checksums", [])
        for package in packages
    ):
        raise ValueError("SBOM.spdx.json does not bind the release archive")
    identity = json.loads((artifacts_dir / "build-identity.json").read_text(encoding="utf-8"))
    build = identity.get("build", {})
    if build.get("archive") != archive.name or build.get("archive_sha256") != _sha256(archive):
        raise ValueError("build identity does not bind the release archive")


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
