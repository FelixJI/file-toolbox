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
        f"FileToolbox-v{version}-win-x64.zip",
        "releases.win.json",
    }


def _delta_name(version: str) -> str:
    return f"FileToolbox-{version}-delta.nupkg"


def _feed_asset_binds(asset: object, package_type: str, version: str, path: Path) -> bool:
    if not isinstance(asset, dict):
        return False
    return (
        asset.get("PackageId") == "FileToolbox"
        and asset.get("Version") == version
        and asset.get("Type") == package_type
        and asset.get("FileName") == path.name
        and str(asset.get("SHA256", "")).casefold() == _sha256(path)
        and asset.get("Size") == path.stat().st_size
    )


def _check_feed_assets(feed_assets: list[object], version: str, full: Path, delta: Path) -> None:
    """校验 Velopack feed:当前版本恰一个 Full(有 delta 文件时)恰一个 Delta。

    其余 Assets 只允许「非当前版本」的 Full 历史条目(vpk 对上一版做差量时会把
    基线 full 一并写进 feed,客户端回退/首次安装依赖它们)。
    """
    full_entries = [
        asset
        for asset in feed_assets
        if isinstance(asset, dict) and asset.get("Version") == version
    ]
    if sum(
        1 for asset in full_entries if isinstance(asset, dict) and asset.get("Type") == "Full"
    ) != 1 or not any(_feed_asset_binds(asset, "Full", version, full) for asset in full_entries):
        raise ValueError("Velopack feed does not bind the full package")
    delta_entries = [
        asset
        for asset in feed_assets
        if isinstance(asset, dict)
        and asset.get("Type") == "Delta"
        and asset.get("Version") == version
    ]
    if delta.exists():
        if len(delta_entries) != 1 or not _feed_asset_binds(
            delta_entries[0], "Delta", version, delta
        ):
            raise ValueError("Velopack feed does not bind the delta package")
    elif delta_entries:
        raise ValueError("Velopack feed must not contain a delta entry without the delta asset")
    for asset in feed_assets:
        if not isinstance(asset, dict):
            raise ValueError("Velopack feed contains a malformed asset entry")
        if asset.get("Version") == version and asset.get("Type") not in ("Full", "Delta"):
            raise ValueError(
                f"Velopack feed contains an unexpected asset entry: {asset.get('FileName')!r}"
            )
        if asset.get("Version") != version and asset.get("Type") != "Full":
            raise ValueError(
                f"Velopack feed contains an unexpected asset entry: {asset.get('FileName')!r}"
            )


def _checksum_records(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2:
            raise ValueError("checksums.txt contains an invalid record")
        records[parts[1]] = parts[0].casefold()
    return records


def check_release_smoke(artifacts_dir: Path, version: str) -> None:
    """验证项目构建资产；候选 manifest/SHA256SUMS 由公共 core 校验。

    delta.nupkg 是条件资产:构建时能取到上一正式版本就会出现(首版引导或本地
    重建已发布版本时降级为仅 full)。无论 delta 是否存在,feed 都必须与实际
    资产互相精确绑定。
    """
    delta = artifacts_dir / _delta_name(version)
    payload_names = _payload_names(version) | ({delta.name} if delta.exists() else set())
    expected_names = payload_names | _METADATA_ASSETS
    actual_names = {path.name for path in artifacts_dir.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise ValueError(
            f"release build assets must be exact: expected={sorted(expected_names)!r}, "
            f"actual={sorted(actual_names)!r}"
        )
    portable = artifacts_dir / f"FileToolbox-v{version}-win-x64.zip"
    with zipfile.ZipFile(portable) as package:
        names = package.namelist()
        if "FileToolbox.exe" not in names and "FileToolbox/FileToolbox.exe" not in names:
            raise ValueError("portable archive must contain FileToolbox.exe")
    full = artifacts_dir / f"FileToolbox-{version}-full.nupkg"
    with zipfile.ZipFile(full):
        pass
    if delta.exists():
        with zipfile.ZipFile(delta):
            pass

    checksum_records = _checksum_records(artifacts_dir / "checksums.txt")
    expected_records = {name: _sha256(artifacts_dir / name) for name in sorted(payload_names)}
    if checksum_records != expected_records:
        raise ValueError("checksums.txt must bind every release payload exactly")

    feed = json.loads((artifacts_dir / "releases.win.json").read_text(encoding="utf-8"))
    _check_feed_assets(feed.get("Assets", []), version, full, delta)

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
