"""Implementation behind the stable :mod:`scripts.automation` workflow interface."""

# This implementation is mirrored byte-for-byte across repositories with
# different Ruff formatter settings. Keep its canonical formatting intact.
# fmt: off

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

_SHA = re.compile(r"^[0-9a-f]{40}$")
_GENERATED_RELEASE_ASSETS = frozenset({"release-manifest.json", "SHA256SUMS"})
_STABLE_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_CONVENTIONAL = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+(?P<title>.+)$"
)
_SECTIONS = {
    "breaking": "Breaking Changes",
    "feat": "Features",
    "fix": "Bug Fixes",
    "perf": "Performance",
    "revert": "Reverts",
    "deps": "Dependencies",
    "other": "Changes",
}
_INCLUDED = frozenset({"feat", "fix", "perf", "revert", "deps"})


class AutomationError(RuntimeError):
    """A fail-closed automation invariant was violated."""


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> SemVer:
        match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value)
        if match is None:
            raise AutomationError(f"not stable SemVer: {value!r}")
        return cls(*(int(part) for part in match.groups()))

    @classmethod
    def parse_project(cls, value: str) -> SemVer:
        match = re.fullmatch(
            r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?",
            value,
        )
        if match is None:
            raise AutomationError(f"not SemVer: {value!r}")
        return cls(*(int(part) for part in match.groups()))

    def bump(self, part: str) -> SemVer:
        if part == "major":
            return SemVer(self.major + 1, 0, 0)
        if part == "minor":
            return SemVer(self.major, self.minor + 1, 0)
        if part == "patch":
            return SemVer(self.major, self.minor, self.patch + 1)
        raise AutomationError(f"unsupported bump: {part}")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class CommandRunner:
    def __init__(self, root: Path) -> None:
        self.root = root

    def run(
        self,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        merged_env = {**os.environ, **(env or {})}
        executable = shutil.which(argv[0], path=merged_env.get("PATH"))
        command = [executable, *argv[1:]] if executable is not None else argv
        process = subprocess.run(
            command,
            cwd=self.root,
            env=merged_env,
            check=False,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
        if check and process.returncode:
            detail = (process.stderr or process.stdout or "").strip()
            raise AutomationError(
                f"command failed ({process.returncode}): {argv!r}"
                + (f"\n{detail}" if detail else "")
            )
        return process

    def json(self, argv: list[str], *, env: dict[str, str] | None = None) -> Any:
        output = self.run(argv, env=env, capture=True).stdout
        return json.loads(output or "null")


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _full_sha(value: str) -> str:
    normalized = value.strip().lower()
    if _SHA.fullmatch(normalized) is None:
        raise AutomationError("source-sha must be a full lowercase Git SHA")
    return normalized


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


class Automation:
    """Deep module used by both workflows and interface-level tests."""

    def __init__(
        self,
        root: Path,
        config: dict[str, Any],
        runner: CommandRunner | None = None,
    ) -> None:
        self.root = root.resolve()
        self.config = config
        self.runner = runner or CommandRunner(self.root)
        if config.get("schema_version") != 1:
            raise AutomationError("unsupported .ci/project.json schema_version")

    @classmethod
    def for_repository(cls) -> Automation:
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / ".ci/project.json").read_text(encoding="utf-8"))
        return cls(root, config)

    @property
    def repository(self) -> str:
        return str(self.config["project"]["repository"])

    @property
    def component(self) -> str:
        return str(self.config["project"]["component"])

    def _read_source_version(self, source: dict[str, Any]) -> SemVer:
        path = self.root / source["path"]
        kind = source["kind"]
        text = path.read_text(encoding="utf-8")
        if kind == "toml":
            value: Any = tomllib.loads(text)
            for token in source["key"].split("."):
                value = value[token]
        elif kind in {"json", "yaml"} and text.lstrip().startswith(("{", "[")):
            value = json.loads(text)
            for token in source["key"].split("."):
                value = value[token]
        elif kind == "yaml":
            value = self._read_yaml_scalar(path, source["key"])
        elif kind == "xml":
            match = re.search(
                rf"<{re.escape(source['key'])}>([^<]+)</{re.escape(source['key'])}>",
                text,
            )
            if match is None:
                raise AutomationError(f"missing XML version in {path}")
            value = match.group(1)
        elif kind == "text":
            value = text.strip()
        elif kind == "python":
            match = re.search(
                rf'(?m)^\s*{re.escape(source["key"])}\s*=\s*["\']([^"\']+)["\']',
                text,
            )
            if match is None:
                raise AutomationError(f"missing Python version assignment in {path}")
            value = match.group(1)
        elif kind == "uv-lock":
            lock = tomllib.loads(text)
            matches = [
                package["version"]
                for package in lock["package"]
                if package["name"] == source["key"]
            ]
            if len(matches) != 1:
                raise AutomationError(
                    f"uv-lock package must match once: {source['key']}"
                )
            value = matches[0]
        else:
            raise AutomationError(f"unsupported version source kind: {kind}")
        return SemVer.parse_project(str(value))

    def _read_yaml_scalar(self, path: Path, dotted_key: str) -> str:
        tokens = dotted_key.split(".")
        stack: list[tuple[int, str]] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            match = re.match(r"^(\s*)([A-Za-z0-9_-]+):(?:\s*(.*?)\s*)?$", raw_line)
            if match is None:
                continue
            indent = len(match.group(1))
            while stack and stack[-1][0] >= indent:
                stack.pop()
            key, raw_value = match.group(2), match.group(3)
            if [item[1] for item in stack] + [key] == tokens and raw_value:
                return raw_value.strip("\"'")
            if not raw_value:
                stack.append((indent, key))
        raise AutomationError(f"missing YAML scalar {dotted_key} in {path}")

    def current_versions(self) -> tuple[SemVer, ...]:
        return tuple(
            self._read_source_version(source)
            for source in self.config["release"]["version_sources"]
        )

    def current_version(self, *, require_consistent: bool = True) -> SemVer:
        versions = self.current_versions()
        if require_consistent and len(set(versions)) != 1:
            raise AutomationError(
                "project version sources disagree: "
                + ", ".join(sorted({str(item) for item in versions}))
            )
        return max(versions)

    def _command_env(
        self,
        *,
        event: str,
        source_sha: str,
        version: SemVer,
        changelog_base_tag: str = "",
    ) -> dict[str, str]:
        automation = self.root / "build/automation"
        values = {
            "AUTOMATION_PROJECT_ROOT": str(self.root),
            "AUTOMATION_ARTIFACTS_DIR": str(automation / "artifacts"),
            "AUTOMATION_CANDIDATE_DIR": str(automation / "release-candidate"),
            "AUTOMATION_SOURCE_SHA": source_sha,
            "AUTOMATION_VERSION": str(version),
            "AUTOMATION_EVENT": event,
            "AUTOMATION_CHANGELOG_BASE_TAG": changelog_base_tag,
        }
        return values

    def _run_templates(
        self,
        templates: list[list[str]],
        env: dict[str, str],
        extra_substitutions: dict[str, str] | None = None,
    ) -> None:
        substitutions = {
            "version": env["AUTOMATION_VERSION"],
            "artifacts_dir": env["AUTOMATION_ARTIFACTS_DIR"],
            "candidate_dir": env["AUTOMATION_CANDIDATE_DIR"],
            "source_sha": env["AUTOMATION_SOURCE_SHA"],
            "changelog_base_tag": env["AUTOMATION_CHANGELOG_BASE_TAG"],
        }
        substitutions.update(extra_substitutions or {})
        for template in templates:
            self.runner.run(
                [part.format(**substitutions) for part in template], env=env
            )

    def _activate_project_environment(self, env: dict[str, str]) -> None:
        venv = self.root / ".venv"
        scripts = venv / ("Scripts" if os.name == "nt" else "bin")
        if not scripts.is_dir():
            return
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH"] = os.pathsep.join((str(scripts), os.environ.get("PATH", "")))

    def _ci_context(self, *, event: str, source_sha: str) -> tuple[str, SemVer]:
        if event not in {"pull_request", "push"}:
            raise AutomationError(f"unsupported event: {event}")
        sha = _full_sha(source_sha)
        actual_sha = self.runner.run(
            ["git", "rev-parse", "HEAD"], capture=True
        ).stdout.strip()
        if actual_sha != sha:
            raise AutomationError(
                f"checked out source {actual_sha} does not match {sha}"
            )
        return sha, self.current_version()

    def _ci_shards(self) -> dict[str, Any]:
        raw = self.config.get("ci_shards")
        if not isinstance(raw, dict):
            raise AutomationError("CI shard phase requires ci_shards configuration")
        lanes = raw.get("lanes")
        handoff_paths = raw.get("handoff_paths")
        if not isinstance(lanes, list) or not lanes:
            raise AutomationError("ci_shards.lanes must be a non-empty list")
        if not isinstance(handoff_paths, list) or not handoff_paths:
            raise AutomationError("ci_shards.handoff_paths must be a non-empty list")
        names = [lane.get("name") if isinstance(lane, dict) else None for lane in lanes]
        if any(
            not isinstance(name, str) or re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name) is None
            for name in names
        ) or len(set(names)) != len(names):
            raise AutomationError("ci_shards lane names must be unique safe identifiers")
        if not all(isinstance(path, str) and path for path in handoff_paths):
            raise AutomationError("ci_shards handoff paths must be non-empty strings")
        for path in handoff_paths:
            candidate = Path(path)
            if (
                candidate.is_absolute()
                or re.search(r"[*?\[\]]", path)
                or not (self.root / candidate).resolve().is_relative_to(self.root)
            ):
                raise AutomationError("ci_shards handoff paths must stay inside the repository")
        if (
            not isinstance(raw.get("run"), list)
            or not raw["run"]
            or not isinstance(raw.get("aggregate"), list)
            or not raw["aggregate"]
        ):
            raise AutomationError("ci_shards run and aggregate commands are required")
        return raw

    def ci_plan(self, *, event: str, source_sha: str) -> dict[str, str]:
        self._ci_context(event=event, source_sha=source_sha)
        if "ci_shards" not in self.config:
            plan = {
                "sharded": "false",
                "matrix": '{"include":[]}',
                "handoff_paths": "",
            }
        else:
            shards = self._ci_shards()
            plan = {
                "sharded": "true",
                "matrix": json.dumps(
                    {"include": shards["lanes"]},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "handoff_paths": "\n".join(shards["handoff_paths"]),
            }
        self._write_outputs(plan)
        return plan

    def ci_prepare(self, *, event: str, source_sha: str) -> None:
        self._ci_shards()
        sha, version = self._ci_context(event=event, source_sha=source_sha)
        automation_root = self.root / "build/automation"
        artifacts_dir = automation_root / "artifacts"
        candidate_dir = automation_root / "release-candidate"
        report_path = automation_root / "prepare-report.json"
        for path in (artifacts_dir, candidate_dir):
            if path.exists():
                shutil.rmtree(path)
        automation_root.mkdir(parents=True, exist_ok=True)
        env = self._command_env(event=event, source_sha=sha, version=version)
        stages: list[dict[str, object]] = []
        failure: str | None = None
        try:
            for stage in ("bootstrap", "quality", "e2e", "release_build"):
                started = time.monotonic()
                self._run_templates(self.config["ci"].get(stage, []), env)
                if stage == "bootstrap":
                    self._activate_project_environment(env)
                stages.append(
                    {
                        "name": stage,
                        "status": "passed",
                        "duration_seconds": round(time.monotonic() - started, 3),
                    }
                )
        except Exception as error:
            failure = str(error)
            raise
        finally:
            _write_json(
                report_path,
                {
                    "schema_version": 1,
                    "event": event,
                    "source_sha": sha,
                    "version": str(version),
                    "status": "failed" if failure else "passed",
                    "error": failure,
                    "stages": stages,
                },
            )

    def ci_shard(self, *, event: str, source_sha: str, lane: str) -> None:
        shards = self._ci_shards()
        sha, version = self._ci_context(event=event, source_sha=source_sha)
        declared = {item["name"] for item in shards["lanes"]}
        if lane not in declared:
            raise AutomationError(f"undeclared CI shard: {lane}")
        env = self._command_env(event=event, source_sha=sha, version=version)
        self._run_templates(
            shards["run"],
            env,
            {
                "lane": lane,
                "lane_report": f"build/automation/lane-reports/{lane}.json",
            },
        )

    def ci_finalize(
        self,
        *,
        event: str,
        source_sha: str,
        reports_dir: str,
    ) -> None:
        shards = self._ci_shards()
        sha, version = self._ci_context(event=event, source_sha=source_sha)
        reports_path = (self.root / reports_dir).resolve()
        if not reports_path.is_relative_to(self.root):
            raise AutomationError("CI shard reports directory must stay inside the repository")
        env = self._command_env(event=event, source_sha=sha, version=version)
        started = time.monotonic()
        failure: str | None = None
        try:
            self._run_templates(
                shards["aggregate"],
                env,
                {"reports_dir": reports_path.relative_to(self.root).as_posix()},
            )
            if event == "push":
                candidate_dir = self.root / "build/automation/release-candidate"
                if candidate_dir.exists():
                    shutil.rmtree(candidate_dir)
                self._finalize_main_candidate(
                    artifacts_dir=self.root / "build/automation/artifacts",
                    candidate_dir=candidate_dir,
                    source_sha=sha,
                    version=version,
                )
        except Exception as error:
            failure = str(error)
            raise
        finally:
            _write_json(
                self.root / "build/automation/report.json",
                {
                    "schema_version": 1,
                    "event": event,
                    "source_sha": sha,
                    "version": str(version),
                    "status": "failed" if failure else "passed",
                    "error": failure,
                    "stages": [
                        {
                            "name": "release_smoke",
                            "status": "failed" if failure else "passed",
                            "duration_seconds": round(time.monotonic() - started, 3),
                        }
                    ],
                },
            )

    def ci(self, *, event: str, source_sha: str) -> None:
        sha, version = self._ci_context(event=event, source_sha=source_sha)
        automation_root = self.root / "build/automation"
        artifacts_dir = automation_root / "artifacts"
        candidate_dir = automation_root / "release-candidate"
        report_path = automation_root / "report.json"
        for path in (artifacts_dir, candidate_dir):
            if path.exists():
                shutil.rmtree(path)
        automation_root.mkdir(parents=True, exist_ok=True)
        env = self._command_env(event=event, source_sha=sha, version=version)
        stages: list[dict[str, object]] = []
        failure: str | None = None
        try:
            for lane in (
                "bootstrap",
                "quality",
                "e2e",
                "release_build",
                "release_smoke",
            ):
                started = time.monotonic()
                self._run_templates(self.config["ci"].get(lane, []), env)
                if lane == "bootstrap":
                    self._activate_project_environment(env)
                stages.append(
                    {
                        "name": lane,
                        "status": "passed",
                        "duration_seconds": round(time.monotonic() - started, 3),
                    }
                )
            if event == "push":
                self._finalize_main_candidate(
                    artifacts_dir=artifacts_dir,
                    candidate_dir=candidate_dir,
                    source_sha=sha,
                    version=version,
                )
        except Exception as error:
            failure = str(error)
            raise
        finally:
            _write_json(
                report_path,
                {
                    "schema_version": 1,
                    "event": event,
                    "source_sha": sha,
                    "version": str(version),
                    "status": "failed" if failure else "passed",
                    "error": failure,
                    "stages": stages,
                },
            )

    def _load_plan(self) -> dict[str, Any] | None:
        path = self.root / ".release/plan.json"
        if not path.is_file():
            return None
        plan = json.loads(path.read_text(encoding="utf-8"))
        if plan.get("schema_version") != 1 or plan.get("state") != "pending":
            raise AutomationError(".release/plan.json must be a pending schema v1 plan")
        return plan

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

    def _stable_tags(self) -> dict[SemVer, str]:
        lines = self.runner.run(
            ["git", "tag", "--list", "v*"], capture=True
        ).stdout.splitlines()
        return {
            SemVer.parse(match.group(0)[1:]): match.group(0)
            for line in lines
            if (match := _STABLE_TAG.fullmatch(line.strip())) is not None
        }

    def _qualified_releases(self) -> dict[SemVer, dict[str, Any]]:
        releases = self.runner.json(
            [
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{self.repository}/releases?per_page=100",
            ]
        )
        if releases and isinstance(releases[0], list):
            releases = [release for page in releases for release in page]
        result: dict[SemVer, dict[str, Any]] = {}
        for release in releases:
            match = _STABLE_TAG.fullmatch(str(release.get("tag_name", "")))
            if (
                match is not None
                and not release.get("draft")
                and not release.get("prerelease")
                and release.get("published_at")
            ):
                result[SemVer.parse(match.group(0)[1:])] = release
        return result

    def _replace_version(self, source: dict[str, Any], version: SemVer) -> None:
        path = self.root / source["path"]
        kind = source["kind"]
        text = path.read_text(encoding="utf-8")
        old = str(self._read_source_version(source))
        old_pattern = re.escape(old) + r"(?:-[0-9A-Za-z.-]+)?"
        if kind == "toml":
            updated, count = re.subn(
                rf'(?m)^(version\s*=\s*)["\']{old_pattern}["\']',
                rf'\1"{version}"',
                text,
                count=1,
            )
        elif kind == "xml":
            key = re.escape(source["key"])
            updated, count = re.subn(
                rf"(<{key}>){old_pattern}(</{key}>)",
                rf"\g<1>{version}\g<2>",
                text,
                count=1,
            )
        elif kind == "text":
            updated, count = f"{version}\n", 1
        elif kind in {"json", "yaml"} and text.lstrip().startswith(("{", "[")):
            value = json.loads(text)
            cursor = value
            tokens = source["key"].split(".")
            for token in tokens[:-1]:
                cursor = cursor[token]
            cursor[tokens[-1]] = str(version)
            updated, count = (
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                1,
            )
        elif kind == "yaml":
            leaf = re.escape(source["key"].split(".")[-1])
            updated, count = re.subn(
                rf'(?m)^(\s*{leaf}:\s*)["\']?{old_pattern}["\']?(\s*(?:#.*)?)$',
                rf'\g<1>"{version}"\g<2>',
                text,
                count=1,
            )
        elif kind == "python":
            key = re.escape(source["key"])
            updated, count = re.subn(
                rf'(?m)^(\s*{key}\s*=\s*)["\']{old_pattern}["\']',
                rf'\g<1>"{version}"',
                text,
                count=1,
            )
        elif kind == "uv-lock":
            raise AutomationError(
                "uv-lock is derived and must be regenerated, not edited"
            )
        else:
            raise AutomationError(f"unsupported version source kind: {kind}")
        if count != 1:
            raise AutomationError(f"could not update version source {path}")
        path.write_text(updated, encoding="utf-8", newline="\n")

    def _commits(self, baseline_tag: str) -> list[dict[str, str]]:
        revision = f"{baseline_tag}..HEAD" if baseline_tag else "HEAD"
        output = self.runner.run(
            ["git", "log", revision, "--format=%H%x1f%s%x1f%b%x1e"], capture=True
        ).stdout
        commits: list[dict[str, str]] = []
        for record in output.split("\x1e"):
            parts = record.strip("\r\n ").split("\x1f", 2)
            if len(parts) == 3:
                commits.append({"sha": parts[0], "subject": parts[1], "body": parts[2]})
        return commits

    def _release_notes(self, version: SemVer, baseline_tag: str) -> str:
        groups: dict[str, list[str]] = {name: [] for name in _SECTIONS}
        for commit in self._commits(baseline_tag):
            match = _CONVENTIONAL.fullmatch(commit["subject"])
            if match is None:
                continue
            body = commit["body"]
            if re.search(r"(?im)^changelog:\s*skip\s*$", body):
                continue
            include = re.search(r"(?im)^changelog:\s*include\s*$", body) is not None
            breaking = (
                bool(match["breaking"])
                or re.search(r"(?im)^BREAKING[ -]CHANGE:\s*.+$", body) is not None
            )
            commit_type = match["type"]
            if not (
                include
                or breaking
                or commit_type in _INCLUDED
                or match["scope"] == "deps"
            ):
                continue
            group = (
                "breaking"
                if breaking
                else "deps"
                if commit_type == "deps" or match["scope"] == "deps"
                else commit_type
            )
            if group not in groups:
                group = "other"
            scope = f"**{match['scope']}:** " if match["scope"] else ""
            groups[group].append(f"- {scope}{match['title']} ({commit['sha'][:7]})")
        lines = [f"## {version}", ""]
        for group, title in _SECTIONS.items():
            if groups[group]:
                lines.extend((f"### {title}", "", *groups[group], ""))
        if len(lines) == 2:
            lines.extend(("内部改进与维护。", ""))
        return "\n".join(lines)

    def _update_changelog(self, version: SemVer, baseline_tag: str) -> None:
        path = self.root / "CHANGELOG.md"
        existing = (
            path.read_text(encoding="utf-8") if path.exists() else "# Changelog\n"
        )
        heading = re.compile(rf"(?m)^## (?:\[)?{re.escape(str(version))}(?:\])?.*$")
        if heading.search(existing):
            start = heading.search(existing).start()  # type: ignore[union-attr]
            following = re.search(
                r"(?m)^## ", existing[heading.search(existing).end() :]
            )  # type: ignore[union-attr]
            end = (
                heading.search(existing).end() + following.start()  # type: ignore[union-attr]
                if following
                else len(existing)
            )
            existing = existing[:start] + existing[end:]
        title_end = existing.find("\n") + 1
        content = (
            existing[:title_end]
            + "\n"
            + self._release_notes(version, baseline_tag)
            + existing[title_end:]
        )
        path.write_text(content, encoding="utf-8", newline="\n")

    def prepare(self, *, bump: str) -> None:
        self.runner.run(["git", "fetch", "origin", "main", "--tags"])
        current = self.current_version(require_consistent=True)
        tags = self._stable_tags()
        releases = self._qualified_releases()
        baseline = max({current, *tags.keys(), *releases.keys()})
        changelog_base_tag = releases[max(releases)]["tag_name"] if releases else ""
        target = baseline.bump(bump)
        branch = "automation/release"
        prs = self.runner.json(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--base",
                "main",
                "--limit",
                "100",
                "--json",
                "number,headRefName,title",
            ]
        )
        matching = [pr for pr in prs if pr["headRefName"] == branch]
        if len(matching) > 1:
            raise AutomationError("multiple open release PRs use the canonical branch")
        if matching:
            self.runner.run(
                ["git", "fetch", "origin", f"{branch}:refs/remotes/origin/{branch}"]
            )
            previous = json.loads(
                self.runner.run(
                    ["git", "show", f"origin/{branch}:.release/plan.json"], capture=True
                ).stdout
            )
            if previous.get("bump") != bump:
                raise AutomationError(
                    f"open release PR requests {previous.get('bump')}; refusing {bump}"
                )
        self.runner.run(["git", "checkout", "-B", branch, "origin/main"])
        for source in self.config["release"]["version_sources"]:
            if not source.get("derived"):
                self._replace_version(source, target)
        for dependency in self.config["release"].get("dependency_versions", []):
            path = self.root / dependency["path"]
            text = path.read_text(encoding="utf-8")
            replacement = dependency["replacement"].format(version=target)
            updated, count = re.subn(dependency["pattern"], replacement, text)
            if count != 1:
                raise AutomationError(f"dependency version replacement failed: {path}")
            path.write_text(updated, encoding="utf-8", newline="\n")
        self._update_changelog(target, changelog_base_tag)
        prepared_from_sha = self.runner.run(
            ["git", "rev-parse", "origin/main"], capture=True
        ).stdout.strip()
        plan = {
            "schema_version": 1,
            "state": "pending",
            "bump": bump,
            "baseline_version": str(baseline),
            "version": str(target),
            "tag": f"v{target}",
            "changelog_base_tag": changelog_base_tag or None,
            "prepared_from_sha": prepared_from_sha,
            "release_branch": branch,
        }
        _write_json(self.root / ".release/plan.json", plan)
        env = self._command_env(
            event="prepare",
            source_sha=prepared_from_sha,
            version=target,
            changelog_base_tag=changelog_base_tag,
        )
        self._run_templates(self.config["release"].get("generated_commands", []), env)
        self.runner.run(["git", "config", "user.name", "github-actions[bot]"])
        self.runner.run(
            [
                "git",
                "config",
                "user.email",
                "41898282+github-actions[bot]@users.noreply.github.com",
            ]
        )
        self.runner.run(["git", "add", "-A"])
        if self.runner.run(
            ["git", "diff", "--cached", "--quiet"], check=False
        ).returncode:
            self.runner.run(["git", "commit", "-m", f"chore(release): {target}"])
        self.runner.run(
            ["git", "push", "--force-with-lease", "origin", f"HEAD:{branch}"]
        )
        title = f"chore(release): {target}"
        body = (
            f"Prepare stable release v{target}. `.release/plan.json` is authoritative."
        )
        if matching:
            self.runner.run(
                [
                    "gh",
                    "pr",
                    "edit",
                    str(matching[0]["number"]),
                    "--title",
                    title,
                    "--body",
                    body,
                ]
            )
        else:
            self.runner.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    "main",
                    "--head",
                    branch,
                    "--title",
                    title,
                    "--body",
                    body,
                ]
            )

    def publish(self, *, candidate_dir: str, source_sha: str) -> None:
        manifest = self._verify_candidate(candidate_dir, source_sha)
        if manifest is None:
            return
        root = Path(candidate_dir).resolve()
        tag = manifest["release"]["tag"]
        sha = _full_sha(source_sha)
        tag_sha = self._tag_sha(tag)
        if tag_sha is None:
            self.runner.run(["git", "tag", tag, sha])
            self.runner.run(["git", "push", "origin", f"refs/tags/{tag}"])
        elif tag_sha != sha:
            raise AutomationError("stable tag identity mismatch")
        release = self._published_release(tag)
        expected = {path.name for path in root.iterdir() if path.is_file()}
        if release is None:
            conflicting = self._release_record(tag)
            if conflicting is not None:
                raise AutomationError(
                    f"stable tag {tag} is occupied by a draft or prerelease Release"
                )
            plan = self._load_plan()
            assert plan is not None
            notes = self._release_notes(
                SemVer.parse(manifest["release"]["version"]),
                plan.get("changelog_base_tag") or "",
            )
            notes_path = root / ".release-notes.md"
            notes_path.write_text(notes, encoding="utf-8", newline="\n")
            try:
                self.runner.run(
                    [
                        "gh",
                        "release",
                        "create",
                        tag,
                        "--repo",
                        self.repository,
                        "--verify-tag",
                        "--title",
                        tag,
                        "--notes-file",
                        str(notes_path),
                        *[str(root / name) for name in sorted(expected)],
                    ]
                )
            finally:
                notes_path.unlink(missing_ok=True)
        else:
            remote = {asset["name"]: asset for asset in release.get("assets", [])}
            remote_manifest = self._remote_manifest(tag)
            if remote_manifest is not None:
                for key in (
                    "release",
                    "source",
                    "project",
                    "build_identity",
                    "protocol",
                ):
                    if remote_manifest.get(key) != manifest.get(key):
                        raise AutomationError(
                            "existing Release manifest identity mismatch"
                        )
            delete_names = set(remote) - expected
            with tempfile.TemporaryDirectory(prefix="automation-assets-") as temporary:
                if remote:
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
                for name in remote:
                    downloaded = Path(temporary) / name
                    if name in expected and (
                        not downloaded.is_file()
                        or _sha256(downloaded) != _sha256(root / name)
                    ):
                        delete_names.add(name)
            for name in sorted(delete_names):
                self.runner.run(
                    [
                        "gh",
                        "api",
                        "--method",
                        "DELETE",
                        f"repos/{self.repository}/releases/assets/{remote[name]['id']}",
                    ]
                )
            missing = expected - (set(remote) - delete_names)
            if missing:
                self.runner.run(
                    [
                        "gh",
                        "release",
                        "upload",
                        tag,
                        "--repo",
                        self.repository,
                        *[str(root / name) for name in sorted(missing)],
                    ]
                )
        refreshed = self._published_release(tag)
        if (
            refreshed is None
            or {asset["name"] for asset in refreshed.get("assets", [])} != expected
        ):
            raise AutomationError(
                "published Release does not have the exact candidate assets"
            )
        with tempfile.TemporaryDirectory(prefix="automation-verify-") as temporary:
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
            for name in expected:
                downloaded = Path(temporary) / name
                if not downloaded.is_file() or _sha256(downloaded) != _sha256(
                    root / name
                ):
                    raise AutomationError(
                        f"published Release asset verification failed: {name}"
                    )
        self._mirror()
        self._cleanup_releases()

    def _mirror(self) -> None:
        self.runner.run(["git", "fetch", "origin", "main", "--tags"])
        failures: list[str] = []
        successes = 0
        for mirror in self.config["release"].get("mirrors", []):
            url = os.environ.get(mirror["url_env"], "")
            token = os.environ.get(mirror["token_env"], "")
            user = mirror.get("user") or os.environ.get(mirror.get("user_env", ""), "")
            if not url or not token or not user:
                failures.append(f"{mirror['name']}: missing credentials")
                continue
            target = f"https://{quote(user, safe='')}:{quote(token, safe='')}@{url.removeprefix('https://')}"
            result = self.runner.run(
                [
                    "git",
                    "push",
                    target,
                    "refs/remotes/origin/main:refs/heads/main",
                    "refs/tags/*:refs/tags/*",
                ],
                check=False,
            )
            if result.returncode:
                failures.append(f"{mirror['name']}: git push failed")
            else:
                successes += 1
        if self.config["release"].get("mirrors") and successes == 0:
            raise AutomationError("mirror failures: " + "; ".join(failures))

    def _cleanup_releases(self) -> None:
        releases = self._qualified_releases()
        ordered = sorted(
            releases.values(), key=lambda item: item["published_at"], reverse=True
        )
        for release in ordered[5:]:
            self.runner.run(
                [
                    "gh",
                    "api",
                    "--method",
                    "DELETE",
                    f"repos/{self.repository}/releases/{release['id']}",
                ]
            )

# fmt: on
