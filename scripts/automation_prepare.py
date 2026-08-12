"""Version preparation and changelog internals for repository automation."""

# Mirrored byte-for-byte across repositories. Keep canonical formatting intact.
# fmt: off

from __future__ import annotations

import json
import re
from typing import Any

if __package__:
    from scripts.automation_common import (
        _CONVENTIONAL,
        _INCLUDED,
        _SECTIONS,
        _STABLE_TAG,
        AutomationError,
        SemVer,
        _write_json,
    )
else:
    from automation_common import (
        _CONVENTIONAL,
        _INCLUDED,
        _SECTIONS,
        _STABLE_TAG,
        AutomationError,
        SemVer,
        _write_json,
    )


class _PrepareAutomationMixin:
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
