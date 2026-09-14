"""Guard machine-local AI Flow artifacts at commit, PR diff and push boundaries.

Deliberately narrow path rules: ordinary docs, AGENTS and workflow source remain versioned.
This is a cooperative Git guard, not a security sandbox or a general secret scanner.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath

LOCAL_NAMES = {
    "bootstrap_result.md",
    "ai_flow_result.md",
    "ai_flow_handoff.md",
    "ai_flow_status.json",
}
LOCAL_DIRS = ("runtime/", "migration-backups/", "upgrade-candidates/", "reports/")
IGNORE_BLOCK = """# BEGIN AI-FLOW LOCAL ARTIFACTS
/.ai-flow/local.json
/.ai-flow/runtime/
/.ai-flow/migration-backups/
/.ai-flow/upgrade-candidates/
/.ai-flow/reports/
BOOTSTRAP_RESULT.md
AI_FLOW_RESULT.md
AI_FLOW_HANDOFF.md
AI_FLOW_STATUS.json
# END AI-FLOW LOCAL ARTIFACTS
"""


def is_local_artifact(name: str) -> bool:
    name = name.replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    raw = str(PurePosixPath(name)).casefold()
    if PurePosixPath(raw).name in LOCAL_NAMES:
        return True
    if raw in {".ai-flow/local.json"}:
        return True
    return any(raw.startswith(prefix + part) for prefix in (".ai-flow/",) for part in LOCAL_DIRS)


def git_bytes(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=45)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def paths(root, *args):
    return [os.fsdecode(x) for x in git_bytes(root, *args).split(b"\0") if x]


def violations(root, mode="staged", base=None):
    if mode == "tracked":
        names = paths(root, "ls-files", "-z")
    elif mode == "branch":
        if not base or base.startswith("-"):
            raise ValueError("A real --base commit/ref is required")
        sha = git_bytes(root, "rev-parse", "--verify", base + "^{commit}").decode().strip()
        names = paths(
            root,
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACMRT",
            "-z",
            sha + "...HEAD",
        )
    else:
        names = paths(
            root, "diff", "--cached", "--name-only", "--no-renames", "--diff-filter=ACMRT", "-z"
        )
    return sorted({name for name in names if is_local_artifact(name)})


def pre_push(root, lines, destination=None):
    bad = set()
    exclusions = []
    if destination:
        # Query the actual push URL, not tracking refs (which may be stale or belong
        # to another server). Unknown local objects are not used as exemptions.
        advertised = git_bytes(root, "ls-remote", "--heads", "--", destination)
        for row in advertised.decode().splitlines():
            oid, ref = row.split()
            if not ref.startswith("refs/heads/"):
                raise ValueError("Invalid destination branch advertisement")
            try:
                known = git_bytes(root, "rev-parse", "--verify", oid + "^{commit}")
            except ValueError:
                continue  # conservative: inspect more history until a normal fetch
            exclusions.append("^" + known.decode().strip())
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            raise ValueError("Invalid pre-push hook input; push refused")
        _, local, _, remote = parts
        if set(local) == {"0"}:
            continue  # remote branch deletion: no file contents pushed
        tip = git_bytes(root, "rev-parse", "--verify", local + "^{commit}").decode().strip()
        # Check the tip too: an older already-tracked runtime file still should not be published.
        bad.update(
            name
            for name in paths(root, "ls-tree", "-r", "--name-only", "-z", tip)
            if is_local_artifact(name)
        )
        rev_args = ["rev-list", tip]
        if set(remote) != {"0"}:
            # A missing remote object means we cannot safely define the range: fail closed.
            old = git_bytes(root, "rev-parse", "--verify", remote + "^{commit}").decode().strip()
            rev_args += ["^" + old]
        if destination:
            rev_args += exclusions
        elif set(remote) == {"0"}:
            # Compatibility for already-installed v3.2 hooks without destination.
            rev_args += ["--not", "--remotes"]
        commits = git_bytes(root, *rev_args).decode().splitlines()
        for commit in commits:
            names = paths(
                root,
                "diff-tree",
                "-m",
                "--root",
                "--no-commit-id",
                "-r",
                "--no-renames",
                "--name-only",
                "--diff-filter=ACMRT",
                "-z",
                commit,
            )
            bad.update(name for name in names if is_local_artifact(name))
    return sorted(bad)


def migrate(root, apply=False):
    """Move only exact recognized tracked artifacts; preserve bytes and stage deletion, never force."""
    bad = violations(root, "tracked")
    for name in bad:
        keep = name.replace("\\", "/").casefold() == ".ai-flow/local.json"
        print(
            ("UNTRACK + BACKUP " if keep else "MOVE ")
            + ("" if apply else "(preview) ")
            + name
            + " -> .ai-flow/runtime/legacy/"
        )
        source = root / name
        current = root
        for part in Path(name).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symlink artifact path refused: " + name)
        if source.is_symlink() or not source.is_file():
            raise ValueError("Inspect missing/symlink artifact manually: " + name)
        # Do not run an all-tree cleanup or unstage unrelated user files.
        if apply:
            data = source.read_bytes()
            target = root / ".ai-flow/runtime/legacy" / uuid.uuid4().hex / name
            current = root
            for part in target.relative_to(root).parts:
                current = current / part
                if current.is_symlink():
                    raise ValueError("Symlink destination refused: " + str(current))
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != data:
                raise ValueError("Backup collision")
            target.write_bytes(data)
            git_bytes(root, "rm", "--cached", "--", name)  # deliberately no -f
            if source.read_bytes() != data:
                raise ValueError(
                    "File changed during migration; preserved both copies for inspection"
                )
            if not keep:
                source.unlink()
    return bad


def install_hooks(root):
    """Never replace an existing hook manager. Existing hooks need one explicit guard call."""
    configured = subprocess.run(
        ["git", "-C", str(root), "config", "--get", "core.hooksPath"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if configured.returncode == 0 and configured.stdout.strip():
        raise ValueError(
            "Existing core.hooksPath preserved. Integrate hygiene.py --staged / --pre-push into that hook manager."
        )
    common = Path(git_bytes(root, "rev-parse", "--git-common-dir").decode().strip())
    if not common.is_absolute():
        common = root / common
    hooks = common.resolve() / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    marker = "# AI-FLOW-NATIVE-GUARD v3.2"
    fallback = hooks / "ai-flow-hygiene.py"
    if fallback.is_symlink() or (
        fallback.exists() and marker not in fallback.read_text(encoding="utf-8", errors="replace")
    ):
        raise ValueError("Existing hook helper preserved: " + str(fallback))
    # All worktrees share hooks; older branches may not contain the new guard yet.
    planned = [(fallback, marker + "\n" + Path(__file__).read_text(encoding="utf-8"))]
    for name, flag in [("pre-commit", "--staged"), ("pre-push", "--pre-push")]:
        target = hooks / name
        if target.is_symlink() or (
            target.exists() and marker not in target.read_text(encoding="utf-8", errors="replace")
        ):
            raise ValueError(
                "Existing hook preserved: "
                + str(target)
                + "; integrate guard without replacing it."
            )
        # Use this repository's locked uv environment; preserve pre-push stdin.
        data = (
            "#!/bin/sh\n"
            + marker
            + "\nroot=$(git rev-parse --show-toplevel) || exit 1\n"
            + 'guard="$root/.ai-flow/scripts/hygiene.py"\n'
            + '[ -f "$guard" ] || guard="$(dirname "$0")/ai-flow-hygiene.py"\n'
            + ('export AI_FLOW_PUSH_DESTINATION="$2"\n' if name == "pre-push" else "")
            + 'exec uv run --frozen python "$guard" --repo "$root" '
            + flag
            + "\n"
        )
        planned.append((target, data))
    for target, data in planned:
        target.write_text(data, encoding="utf-8", newline="\n")
        target.chmod(0o755)
        print("Installed local hook: " + str(target))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", default=".")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true")
    group.add_argument("--tracked", action="store_true")
    group.add_argument("--base")
    group.add_argument("--pre-push", action="store_true")
    group.add_argument("--migrate", action="store_true")
    group.add_argument("--install-hooks", action="store_true")
    p.add_argument("--push-destination", help="Actual push URL supplied by pre-push $2")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args(argv)
    try:
        root = Path(args.repo).resolve()
        actual = Path(git_bytes(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
        if actual != root:
            raise ValueError("Use repository root")
        if args.install_hooks:
            install_hooks(root)
            return 0
        if args.migrate:
            migrate(root, args.apply)
            return 0
        bad = (
            pre_push(
                root,
                sys.stdin.read().splitlines(),
                args.push_destination or os.environ.get("AI_FLOW_PUSH_DESTINATION"),
            )
            if args.pre_push
            else violations(
                root, "tracked" if args.tracked else "branch" if args.base else "staged", args.base
            )
        )
        if bad:
            print(
                "BLOCKED: machine-local artifacts must not be committed/pushed:\n" + "\n".join(bad),
                file=sys.stderr,
            )
            return 2
        print("AI Flow artifact hygiene: PASS")
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
