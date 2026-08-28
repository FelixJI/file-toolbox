"""校验统一自动化的版本来源与发布候选契约。"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_STABLE_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def check_release_contract(root: Path = _ROOT) -> list[str]:
    """返回所有契约错误；空列表表示通过。"""
    errors: list[str] = []
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(pyproject["project"]["version"])
    if _STABLE_SEMVER.fullmatch(version) is None:
        errors.append(f"pyproject version is not stable semantic version: {version}")

    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    local_versions = [
        str(package.get("version"))
        for package in lock.get("package", [])
        if package.get("name") == "file-toolbox"
        and package.get("source", {}).get("editable") == "."
    ]
    if local_versions != [version]:
        errors.append(f"uv.lock editable file-toolbox versions {local_versions!r} != [{version!r}]")

    config = json.loads((root / ".ci/project.json").read_text(encoding="utf-8"))
    version_sources = config["release"]["version_sources"]
    if version_sources != [
        {"kind": "toml", "path": "pyproject.toml", "key": "project.version"},
        {
            "kind": "uv-lock",
            "path": "uv.lock",
            "key": "file-toolbox",
            "derived": True,
        },
    ]:
        errors.append("version sources must keep pyproject.toml canonical and uv.lock derived")

    required_assets = config["release"]["required_assets"]
    expected_assets = [
        "FileToolbox-{version}-full.nupkg",
        "FileToolbox-{version}-delta.nupkg",
        "FileToolbox-v{version}-win-x64.zip",
        "releases.win.json",
        "checksums.txt",
        "SBOM.spdx.json",
        "build-identity.json",
    ]
    if required_assets != expected_assets:
        errors.append("release assets must match the Velopack exact set")

    workflows = {path.name for path in (root / ".github/workflows").glob("*.yml")}
    if workflows != {"ci.yml", "cd.yml"}:
        errors.append(f"only ci.yml and cd.yml are allowed: {sorted(workflows)!r}")
    for legacy in (
        ".release-please-manifest.json",
        "release-please-config.json",
    ):
        if (root / legacy).exists():
            errors.append(f"legacy Release Please config remains: {legacy}")

    return errors


def main() -> int:
    errors = check_release_contract()
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1
    print("Release contract is consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
