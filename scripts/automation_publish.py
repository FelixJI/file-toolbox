"""Publishing and mirror reconciliation internals for repository automation."""

# Mirrored byte-for-byte across repositories. Keep canonical formatting intact.
# fmt: off

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import quote

if __package__:
    from scripts.automation_common import AutomationError, SemVer, _full_sha, _sha256
else:
    from automation_common import AutomationError, SemVer, _full_sha, _sha256


class _PublishAutomationMixin:
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
        mirrors = self.config["release"].get("mirrors", [])
        if not mirrors:
            return
        self.runner.run(["git", "fetch", "origin", "main", "--tags"])
        local_tags = (
            self.runner.run(
                [
                    "git",
                    "for-each-ref",
                    "--format=%(refname:strip=2)",
                    "refs/tags",
                ],
                capture=True,
            ).stdout
            or ""
        ).splitlines()
        failures: list[str] = []
        successes = 0
        for mirror in mirrors:
            url = os.environ.get(mirror["url_env"], "")
            token = os.environ.get(mirror["token_env"], "")
            user = mirror.get("user") or os.environ.get(mirror.get("user_env", ""), "")
            if not url or not token or not user:
                failures.append(f"{mirror['name']}: missing credentials")
                continue
            target = f"https://{quote(user, safe='')}:{quote(token, safe='')}@{url.removeprefix('https://')}"
            remote = self.runner.run(
                ["git", "ls-remote", "--refs", "--tags", target],
                capture=True,
                check=False,
            )
            if remote.returncode:
                failures.append(f"{mirror['name']}: git ls-remote failed")
                continue
            remote_tags = {
                ref.removeprefix("refs/tags/")
                for line in (remote.stdout or "").splitlines()
                for _, separator, ref in [line.partition("\t")]
                if separator and ref.startswith("refs/tags/")
            }
            missing_tags = [
                f"refs/tags/{tag}:refs/tags/{tag}"
                for tag in local_tags
                if tag not in remote_tags
            ]
            result = self.runner.run(
                [
                    "git",
                    "push",
                    target,
                    "refs/remotes/origin/main:refs/heads/main",
                    *missing_tags,
                ],
                check=False,
            )
            if result.returncode:
                failures.append(f"{mirror['name']}: git push failed")
            else:
                successes += 1
        if mirrors and successes == 0:
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
