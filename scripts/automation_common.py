"""Shared primitives for the repository automation deep module."""

# Mirrored byte-for-byte across repositories. Keep canonical formatting intact.
# fmt: off

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
