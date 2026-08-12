"""Release-candidate construction and verification internals."""

# Mirrored byte-for-byte across repositories. Keep canonical formatting intact.
# fmt: off

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

try:
    from scripts.automation_common import (
        _GENERATED_RELEASE_ASSETS,
        AutomationError,
        SemVer,
        _full_sha,
        _sha256,
        _write_json,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from automation_common import (
        _GENERATED_RELEASE_ASSETS,
        AutomationError,
        SemVer,
        _full_sha,
        _sha256,
        _write_json,
    )


class _CandidateAutomationMixin:
    def _published_release(self, tag: str) -> dict[str, Any] | None:
        if not os.environ.get("GH_TOKEN"):
            return None
        release = self._release_record(tag)
        if release is None:
            return None
        if (
            release.get("draft")
            or release.get("prerelease")
            or not release.get("published_at")
        ):
            return None
        return release

    def _release_record(self, tag: str) -> dict[str, Any] | None:
        result = self.runner.run(
            ["gh", "api", f"repos/{self.repository}/releases/tags/{tag}"],
            capture=True,
            check=False,
        )
        if result.returncode:
            combined = (result.stderr or "") + (result.stdout or "")
            if "HTTP 404" in combined or "Not Found" in combined:
                return None
            raise AutomationError(f"failed to query Release {tag}: {combined.strip()}")
        return json.loads(result.stdout)

    def _remote_manifest(self, tag: str) -> dict[str, Any] | None:
        with tempfile.TemporaryDirectory(prefix="automation-release-") as temporary:
            result = self.runner.run(
                [
                    "gh",
                    "release",
                    "download",
                    tag,
                    "--repo",
                    self.repository,
                    "--pattern",
                    "release-manifest.json",
                    "--dir",
                    temporary,
                ],
                capture=True,
                check=False,
            )
            path = Path(temporary) / "release-manifest.json"
            if result.returncode or not path.is_file():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

    def _tag_sha(self, tag: str) -> str | None:
        result = self.runner.run(
            ["git", "rev-list", "-n", "1", f"refs/tags/{tag}"],
            capture=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def _sentinel(self, candidate_dir: Path, source_sha: str, reason: str) -> None:
        candidate_dir.mkdir(parents=True, exist_ok=False)
        _write_json(
            candidate_dir / "release-state.json",
            {
                "schema_version": 1,
                "publish": False,
                "reason": reason,
                "source_sha": source_sha,
            },
        )

    def _finalize_main_candidate(
        self,
        *,
        artifacts_dir: Path,
        candidate_dir: Path,
        source_sha: str,
        version: SemVer,
    ) -> None:
        plan = self._load_plan()
        if plan is None:
            self._sentinel(candidate_dir, source_sha, "no-pending-plan")
            return
        if plan.get("version") != str(version) or plan.get("tag") != f"v{version}":
            raise AutomationError("release plan does not match project version")
        plan_change = self.runner.run(
            [
                "git",
                "diff",
                "--name-only",
                "HEAD^",
                "HEAD",
                "--",
                ".release/plan.json",
            ],
            capture=True,
            check=False,
        )
        if (
            plan_change.returncode
            or ".release/plan.json" not in plan_change.stdout.splitlines()
        ):
            self._sentinel(candidate_dir, source_sha, "plan-unchanged")
            return

        actual = {path.name for path in artifacts_dir.iterdir() if path.is_file()}
        build_assets = actual - _GENERATED_RELEASE_ASSETS
        self._validate_asset_patterns(build_assets, version)
        candidate_names = build_assets | _GENERATED_RELEASE_ASSETS
        candidate_manifest = self._build_candidate_manifest(
            artifacts_dir=artifacts_dir,
            plan=plan,
            source_sha=source_sha,
            version=version,
        )
        candidate_identity = {
            key: candidate_manifest[key]
            for key in ("release", "source", "project", "build_identity", "protocol")
        }

        release = self._published_release(plan["tag"])
        if release is not None:
            tag_sha = self._tag_sha(plan["tag"])
            if tag_sha is None:
                raise AutomationError(
                    "published stable Release has no local stable tag"
                )
            remote_manifest = self._remote_manifest(plan["tag"])
            remote_names = {asset["name"] for asset in release.get("assets", [])}
            if remote_manifest is not None:
                tag_identity = {
                    **candidate_identity,
                    "source": {"sha": tag_sha},
                }
                if any(
                    remote_manifest.get(key) != value
                    for key, value in tag_identity.items()
                ):
                    raise AutomationError(
                        "published Release manifest identity mismatch"
                    )
            if remote_names == candidate_names and remote_manifest is None:
                raise AutomationError(
                    "published Release cannot be complete without a verifiable manifest"
                )
            if remote_names == candidate_names and remote_manifest is not None:
                self._verify_remote_release_assets(
                    plan["tag"], build_assets, tag_identity
                )
                self._sentinel(candidate_dir, source_sha, "already-published")
                return
            if tag_sha != source_sha:
                raise AutomationError(
                    "published Release source wins; a different source cannot repair it"
                )

        candidate_dir.mkdir(parents=True, exist_ok=False)
        for path in artifacts_dir.iterdir():
            if path.is_file() and path.name not in _GENERATED_RELEASE_ASSETS:
                shutil.copyfile(path, candidate_dir / path.name)
        _write_json(candidate_dir / "release-manifest.json", candidate_manifest)
        self._write_checksums(candidate_dir)

    def _build_candidate_manifest(
        self,
        *,
        artifacts_dir: Path,
        plan: dict[str, Any],
        source_sha: str,
        version: SemVer,
    ) -> dict[str, Any]:
        artifact_records = {
            path.name: {"sha256": _sha256(path), "size": path.stat().st_size}
            for path in sorted(artifacts_dir.iterdir())
            if path.is_file() and path.name not in _GENERATED_RELEASE_ASSETS
        }
        identity_pattern = self.config["release"].get("identity_asset")
        build_identity = None
        protocol = None
        if identity_pattern:
            matches = sorted(
                path
                for path in artifacts_dir.iterdir()
                if path.is_file()
                and fnmatch.fnmatchcase(
                    path.name, identity_pattern.format(version=version)
                )
            )
            if len(matches) != 1:
                raise AutomationError("build identity asset must match exactly once")
            identity_value = json.loads(matches[0].read_text(encoding="utf-8"))
            expected_project = {
                "component": self.component,
                "repository": self.repository,
                "version": str(version),
                "source_sha": source_sha,
            }
            if (
                identity_value.get("project") is not None
                and identity_value.get("project") != expected_project
            ):
                raise AutomationError("build identity project/source mismatch")
            build_identity = {
                "asset": matches[0].name,
                "sha256": _sha256(matches[0]),
                "value": identity_value,
            }
            protocol = identity_value.get("protocol")
        return {
            "schema_version": 2,
            "release": {"tag": plan["tag"], "version": str(version)},
            "source": {"sha": source_sha},
            "ci": {
                "repository": os.environ.get("GITHUB_REPOSITORY", self.repository),
                "workflow": os.environ.get("GITHUB_WORKFLOW", "CI"),
                "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
                "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
            },
            "project": {"component": self.component, "repository": self.repository},
            "build_identity": build_identity,
            "protocol": protocol,
            "artifacts": artifact_records,
        }

    def _write_checksums(self, root: Path) -> None:
        files = sorted(
            path
            for path in root.iterdir()
            if path.is_file() and path.name != "SHA256SUMS"
        )
        (root / "SHA256SUMS").write_text(
            "".join(f"{_sha256(path)}  {path.name}\n" for path in files),
            encoding="utf-8",
            newline="\n",
        )

    def _validate_asset_patterns(self, actual: set[str], version: SemVer) -> None:
        patterns = [
            pattern.format(version=version)
            for pattern in self.config["release"]["required_assets"]
        ]
        matched: set[str] = set()
        for pattern in patterns:
            matches = {name for name in actual if fnmatch.fnmatchcase(name, pattern)}
            if len(matches) != 1:
                raise AutomationError(
                    f"required asset pattern must match exactly once: {pattern!r}; "
                    f"matches={sorted(matches)}"
                )
            matched.update(matches)
        if matched != actual:
            raise AutomationError(
                f"unexpected release build assets: {sorted(actual - matched)}"
            )

    def _verify_manifested_assets(
        self, root: Path, build_assets: set[str]
    ) -> dict[str, Any]:
        actual = {path.name for path in root.iterdir() if path.is_file()}
        expected = build_assets | _GENERATED_RELEASE_ASSETS
        if actual != expected:
            raise AutomationError("manifested assets are not an exact file set")
        indexed: dict[str, str] = {}
        for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
            if match is None or match.group(2) in indexed:
                raise AutomationError("invalid SHA256SUMS")
            indexed[match.group(2)] = match.group(1)
        if set(indexed) != expected - {"SHA256SUMS"}:
            raise AutomationError("SHA256SUMS does not index the exact assets")
        for name, digest in indexed.items():
            if _sha256(root / name) != digest:
                raise AutomationError(f"asset checksum mismatch: {name}")
        manifest = json.loads(
            (root / "release-manifest.json").read_text(encoding="utf-8")
        )
        if set(manifest.get("artifacts", {})) != build_assets:
            raise AutomationError(
                "release manifest does not describe exact build assets"
            )
        for name in build_assets:
            path = root / name
            if manifest["artifacts"][name] != {
                "sha256": _sha256(path),
                "size": path.stat().st_size,
            }:
                raise AutomationError(f"release manifest asset mismatch: {name}")
        return manifest

    def _verify_remote_release_assets(
        self, tag: str, build_assets: set[str], identity: dict[str, Any]
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="automation-release-exact-"
        ) as temporary:
            self.runner.run(
                [
                    "gh",
                    "release",
                    "download",
                    tag,
                    "--repo",
                    self.repository,
                    "--dir",
                    temporary,
                ]
            )
            manifest = self._verify_manifested_assets(Path(temporary), build_assets)
            if any(manifest.get(key) != value for key, value in identity.items()):
                raise AutomationError("published Release manifest identity mismatch")

    def _verify_candidate(
        self, candidate_dir: str, source_sha: str
    ) -> dict[str, Any] | None:
        root = Path(candidate_dir).resolve(strict=True)
        sha = _full_sha(source_sha)
        manifest_path = root / "release-manifest.json"
        if not manifest_path.is_file():
            if {path.name for path in root.iterdir() if path.is_file()} != {
                "release-state.json"
            }:
                raise AutomationError("release sentinel directory must be exact")
            state = json.loads(
                (root / "release-state.json").read_text(encoding="utf-8")
            )
            if state != {
                "schema_version": 1,
                "publish": False,
                "reason": state.get("reason"),
                "source_sha": sha,
            }:
                raise AutomationError("invalid release sentinel")
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 2:
            raise AutomationError("unsupported candidate manifest")
        if manifest.get("source") != {"sha": sha}:
            raise AutomationError("candidate source identity mismatch")
        if manifest.get("project") != {
            "component": self.component,
            "repository": self.repository,
        }:
            raise AutomationError("candidate project identity mismatch")
        version = SemVer.parse(manifest["release"]["version"])
        if manifest["release"]["tag"] != f"v{version}":
            raise AutomationError("candidate tag/version mismatch")
        actual = {path.name for path in root.iterdir() if path.is_file()}
        common = _GENERATED_RELEASE_ASSETS
        if not common.issubset(actual):
            raise AutomationError(
                "candidate is missing common manifest/checksum assets"
            )
        self._validate_asset_patterns(actual - common, version)
        if "SBOM.spdx.json" not in actual:
            raise AutomationError("candidate must contain fixed SBOM.spdx.json")
        checksum_lines = (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        indexed: dict[str, str] = {}
        for line in checksum_lines:
            match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
            if match is None or match.group(2) in indexed:
                raise AutomationError("invalid SHA256SUMS")
            indexed[match.group(2)] = match.group(1)
        expected_index = actual - {"SHA256SUMS"}
        if set(indexed) != expected_index:
            raise AutomationError("SHA256SUMS does not index the exact candidate")
        for name, digest in indexed.items():
            if _sha256(root / name) != digest:
                raise AutomationError(f"candidate checksum mismatch: {name}")
        artifact_names = actual - _GENERATED_RELEASE_ASSETS
        if set(manifest["artifacts"]) != artifact_names:
            raise AutomationError(
                "candidate manifest does not describe exact artifacts"
            )
        for name in artifact_names:
            record = manifest["artifacts"][name]
            path = root / name
            if record != {"sha256": _sha256(path), "size": path.stat().st_size}:
                raise AutomationError(f"candidate manifest mismatch: {name}")
        ci_identity = manifest.get("ci")
        if (
            not isinstance(ci_identity, dict)
            or ci_identity.get("repository") != self.repository
            or not all(
                ci_identity.get(key) for key in ("workflow", "run_id", "run_attempt")
            )
        ):
            raise AutomationError("candidate CI identity is incomplete")
        identity_pattern = self.config["release"].get("identity_asset")
        build_identity = manifest.get("build_identity")
        if identity_pattern:
            if not isinstance(build_identity, dict):
                raise AutomationError("candidate build identity is missing")
            identity_name = build_identity.get("asset")
            if (
                not isinstance(identity_name, str)
                or identity_name not in artifact_names
                or not fnmatch.fnmatchcase(
                    identity_name, identity_pattern.format(version=version)
                )
                or build_identity.get("sha256") != _sha256(root / identity_name)
            ):
                raise AutomationError("candidate build identity asset mismatch")
            raw_identity = build_identity.get("value")
            if not isinstance(raw_identity, dict):
                raise AutomationError("candidate build identity value is invalid")
            raw_project = raw_identity.get("project")
            if raw_project is not None and raw_project != {
                "component": self.component,
                "repository": self.repository,
                "version": str(version),
                "source_sha": sha,
            }:
                raise AutomationError("candidate build identity project mismatch")
            if manifest.get("protocol") != raw_identity.get("protocol"):
                raise AutomationError("candidate protocol identity mismatch")
        compatibility = self.config["project"].get("protocol_compatibility")
        if compatibility is not None:
            protocol = manifest.get("protocol")
            if not isinstance(protocol, dict) or not protocol.get("version"):
                raise AutomationError("candidate actual Protocol identity is missing")
            protocol_version = SemVer.parse_project(str(protocol["version"]))
            if protocol_version.major not in compatibility["supported_majors"]:
                raise AutomationError("candidate Protocol major is not supported")
        plan = self._load_plan()
        if (
            plan is None
            or plan.get("tag") != f"v{version}"
            or plan.get("version") != str(version)
        ):
            raise AutomationError("candidate does not match authoritative release plan")
        tag_sha = self._tag_sha(f"v{version}")
        if tag_sha is not None and tag_sha != sha:
            raise AutomationError(
                "stable tags are immutable and this tag has another source"
            )
        return manifest

    def _write_outputs(self, values: dict[str, str]) -> None:
        output_path = os.environ.get("GITHUB_OUTPUT")
        if not output_path:
            return
        with Path(output_path).open("a", encoding="utf-8", newline="\n") as output:
            for key, value in values.items():
                if "\n" in value or key in {"checksums", "sbom"}:
                    marker = f"AUTOMATION_{uuid.uuid4().hex}"
                    output.write(f"{key}<<{marker}\n{value}\n{marker}\n")
                else:
                    output.write(f"{key}={value}\n")

    def stage(self, *, candidate_dir: str, source_sha: str) -> None:
        manifest = self._verify_candidate(candidate_dir, source_sha)
        if manifest is None:
            self._write_outputs(
                {"publish": "false", "tag": "", "checksums": "", "sbom": ""}
            )
            return
        root = Path(candidate_dir).resolve()
        self._write_outputs(
            {
                "publish": "true",
                "tag": manifest["release"]["tag"],
                "checksums": str(root / "SHA256SUMS"),
                "sbom": str(root / "SBOM.spdx.json"),
            }
        )
