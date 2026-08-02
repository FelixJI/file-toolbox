"""校验版本来源与 GitHub Release 编排契约。"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_VISIBLE_CHANGELOG_TYPES = {"feat", "fix", "perf", "deps", "revert"}
_HIDDEN_CHANGELOG_TYPES = {
    "docs",
    "style",
    "chore",
    "refactor",
    "test",
    "build",
    "ci",
}


def check_release_contract(root: Path = _ROOT) -> list[str]:
    """返回所有契约错误；空列表表示通过。"""
    errors: list[str] = []

    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(pyproject["project"]["version"])
    if not _SEMVER.fullmatch(version):
        errors.append(f"pyproject version is not semantic: {version}")

    manifest = json.loads((root / ".release-please-manifest.json").read_text(encoding="utf-8"))
    if manifest.get(".") != version:
        errors.append(
            f"release-please manifest version {manifest.get('.')!r} != pyproject {version!r}"
        )

    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    local_versions = [
        str(package.get("version"))
        for package in lock.get("package", [])
        if package.get("name") == "file-toolbox"
        and package.get("source", {}).get("editable") == "."
    ]
    if local_versions != [version]:
        errors.append(f"uv.lock editable file-toolbox versions {local_versions!r} != [{version!r}]")

    config = json.loads((root / "release-please-config.json").read_text(encoding="utf-8"))
    if config.get("draft") is not True:
        errors.append("release-please must create draft Releases")
    if config.get("include-v-in-tag") is not True:
        errors.append("release tags must use the v prefix")

    sections = config.get("changelog-sections", [])
    section_visibility = {
        section.get("type"): section.get("hidden", False)
        for section in sections
        if isinstance(section, dict)
    }
    expected_types = _VISIBLE_CHANGELOG_TYPES | _HIDDEN_CHANGELOG_TYPES
    if len(sections) != len(expected_types) or set(section_visibility) != expected_types:
        errors.append("release-please changelog types must be explicit and complete")
    for changelog_type in _VISIBLE_CHANGELOG_TYPES:
        if section_visibility.get(changelog_type) is not False:
            errors.append(f"changelog type must be visible: {changelog_type}")
    for changelog_type in _HIDDEN_CHANGELOG_TYPES:
        if section_visibility.get(changelog_type) is not True:
            errors.append(f"changelog type must be hidden: {changelog_type}")

    package_config = config.get("packages", {}).get(".", {})
    extra_paths = {
        entry.get("path")
        for entry in package_config.get("extra-files", [])
        if isinstance(entry, dict)
    }
    missing_paths = {"pyproject.toml", "uv.lock"} - extra_paths
    if missing_paths:
        errors.append(f"release-please does not update: {sorted(missing_paths)!r}")

    release_please_workflow = (root / ".github/workflows/release-please.yml").read_text(
        encoding="utf-8"
    )
    if "release-please@17.11.1 release-pr" not in release_please_workflow:
        errors.append("manual release PR creation must use the pinned Release Please CLI")
    if '--release-as="$RELEASE_AS"' not in release_please_workflow:
        errors.append("manual release PR creation must forward the requested manifest version")

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
