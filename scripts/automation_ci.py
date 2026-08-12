"""CI planning and execution internals for repository automation."""

# Mirrored byte-for-byte across repositories. Keep canonical formatting intact.
# fmt: off

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

try:
    from scripts.automation_common import (
        AutomationError,
        SemVer,
        _full_sha,
        _write_json,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from automation_common import AutomationError, SemVer, _full_sha, _write_json


class _CiAutomationMixin:
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
