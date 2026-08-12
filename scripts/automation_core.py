"""Implementation behind the stable :mod:`scripts.automation` workflow interface."""

# Mirrored byte-for-byte across repositories. Keep canonical formatting intact.
# fmt: off

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

__all__ = (
    "Automation",
    "AutomationError",
    "CommandRunner",
    "SemVer",
    "shutil",
    "subprocess",
)

try:
    from scripts.automation_candidate import _CandidateAutomationMixin
    from scripts.automation_ci import _CiAutomationMixin
    from scripts.automation_common import (
        AutomationError,
        CommandRunner,
        SemVer,
    )
    from scripts.automation_prepare import _PrepareAutomationMixin
    from scripts.automation_publish import _PublishAutomationMixin
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from automation_candidate import _CandidateAutomationMixin
    from automation_ci import _CiAutomationMixin
    from automation_common import AutomationError, CommandRunner, SemVer
    from automation_prepare import _PrepareAutomationMixin
    from automation_publish import _PublishAutomationMixin


class Automation(
    _CiAutomationMixin,
    _CandidateAutomationMixin,
    _PrepareAutomationMixin,
    _PublishAutomationMixin,
):
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
