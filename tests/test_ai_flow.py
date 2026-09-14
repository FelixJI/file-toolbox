"""AI Flow 人工交接模式的真实 Git 产物守卫契约。"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "ai_flow_hygiene", Path(__file__).parents[1] / ".ai-flow/scripts/hygiene.py"
)
assert SPEC is not None and SPEC.loader is not None
hygiene = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hygiene)


def git(root: Path, *args: str) -> str:
    return hygiene.git_bytes(root, *args).decode("utf-8").strip()


@pytest.fixture
def flow_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "tracked.txt").write_text("before", encoding="utf-8")
    git(tmp_path, "add", "tracked.txt")
    git(
        tmp_path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "test: baseline",
    )
    return tmp_path


@pytest.mark.parametrize("boundary", ["commit", "push"])
def test_git_executes_artifact_hooks(flow_repo: Path, boundary: str) -> None:
    git(flow_repo, "config", "user.name", "Test")
    git(flow_repo, "config", "user.email", "test@example.invalid")
    guard = flow_repo / ".ai-flow/scripts/hygiene.py"
    guard.parent.mkdir(parents=True)
    shutil.copyfile(Path(hygiene.__file__), guard)
    # The hook runs through uv, in an isolated local environment without dependency downloads.
    subprocess.run(["uv", "venv", "--python", sys.executable, str(flow_repo / ".venv")], check=True)
    (flow_repo / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    git(flow_repo, "add", ".ai-flow/scripts/hygiene.py", ".gitignore")
    git(flow_repo, "commit", "-qm", "test: guard fixture")
    report = flow_repo / "BOOTSTRAP_RESULT.md"
    report.write_text("local report", encoding="utf-8")
    git(flow_repo, "add", report.name)
    if boundary == "push":
        # Create the legacy report before installing guards; exercise a real pre-push invocation.
        git(flow_repo, "commit", "-qm", "test: legacy local report")
        remote = flow_repo.parent / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True)
        git(flow_repo, "remote", "add", "local-test", str(remote))
    hygiene.install_hooks(flow_repo)
    args = (
        ["commit", "-qm", "test: blocked report"]
        if boundary == "commit"
        else ["push", "local-test", "HEAD:refs/heads/probe"]
    )
    result = subprocess.run(["git", "-C", str(flow_repo), *args], capture_output=True, text=True)
    assert result.returncode != 0
    assert "BLOCKED: machine-local artifacts" in result.stderr
    assert "BOOTSTRAP_RESULT.md" in result.stderr
    if boundary == "commit":
        git(flow_repo, "rm", "--cached", report.name)
        report.unlink()
        # Shared hooks also work on an older branch without the new guard source.
        git(flow_repo, "rm", ".ai-flow/scripts/hygiene.py")
        (flow_repo / "design.md").write_text("persistent design", encoding="utf-8")
        git(flow_repo, "add", "design.md")
        git(flow_repo, "commit", "-qm", "test: allow persistent document")
    else:
        refs = subprocess.run(["git", "--git-dir", str(remote), "show-ref"], capture_output=True)
        assert refs.returncode == 1 and not refs.stdout


def test_pre_push_rejects_report_introduced_only_by_merge(flow_repo: Path) -> None:
    git(flow_repo, "config", "user.name", "Test")
    git(flow_repo, "config", "user.email", "test@example.invalid")
    base = git(flow_repo, "rev-parse", "HEAD")
    git(flow_repo, "switch", "-c", "side")
    (flow_repo / "side.txt").write_text("side", encoding="utf-8")
    git(flow_repo, "add", "side.txt")
    git(flow_repo, "commit", "-qm", "test: side")
    git(flow_repo, "switch", "main")
    (flow_repo / "main.txt").write_text("main", encoding="utf-8")
    git(flow_repo, "add", "main.txt")
    git(flow_repo, "commit", "-qm", "test: main")
    git(flow_repo, "merge", "--no-commit", "--no-ff", "side")
    (flow_repo / "BOOTSTRAP_RESULT.md").write_text("local report", encoding="utf-8")
    git(flow_repo, "add", "BOOTSTRAP_RESULT.md")
    git(flow_repo, "commit", "-qm", "test: merge introduces report")
    git(flow_repo, "rm", "BOOTSTRAP_RESULT.md")
    git(flow_repo, "commit", "-qm", "test: remove report from tip")
    head = git(flow_repo, "rev-parse", "HEAD")
    assert hygiene.pre_push(flow_repo, [f"refs/heads/main {head} refs/heads/main {base}"]) == [
        "BOOTSTRAP_RESULT.md"
    ]


@pytest.mark.parametrize("existing", [False, True])
def test_pre_push_excludes_only_destination_history(flow_repo: Path, existing: bool) -> None:
    git(flow_repo, "config", "user.name", "Test")
    git(flow_repo, "config", "user.email", "test@example.invalid")
    base = git(flow_repo, "rev-parse", "HEAD")
    remote = flow_repo / "destination.git"
    other = flow_repo / "other.git"
    for target in (remote, other):
        subprocess.run(["git", "init", "--bare", str(target)], check=True)
    git(flow_repo, "push", str(remote), "main")
    if existing:
        git(flow_repo, "push", str(remote), "HEAD:refs/heads/topic")
    report = flow_repo / "BOOTSTRAP_RESULT.md"
    report.write_text("legacy", encoding="utf-8")
    git(flow_repo, "add", report.name)
    git(flow_repo, "commit", "-qm", "test: legacy report")
    git(flow_repo, "rm", report.name)
    git(flow_repo, "commit", "-qm", "test: remove legacy report")
    head = git(flow_repo, "rev-parse", "HEAD")
    old = base if existing else "0" * 40
    lines = [f"refs/heads/topic {head} refs/heads/topic {old}"]
    # Another remote owning the history must not exempt it for this destination.
    git(flow_repo, "remote", "add", "other", str(other))
    git(flow_repo, "push", "other", "main")
    assert hygiene.pre_push(flow_repo, lines, str(remote)) == [report.name]
    git(flow_repo, "push", str(remote), "main")
    assert hygiene.pre_push(flow_repo, lines, str(remote)) == []
    # A tracking ref may still claim the destination owns history it no longer advertises.
    git(flow_repo, "remote", "add", "destination", str(remote))
    git(flow_repo, "fetch", "destination")
    git(remote, "update-ref", "refs/heads/main", base)
    assert hygiene.pre_push(flow_repo, lines, str(remote)) == [report.name]
    git(flow_repo, "push", str(remote), "main")
    # Exercise Git's real hook arguments, including a URL rather than a remote name.
    subprocess.run(["uv", "venv", "--python", sys.executable, str(flow_repo / ".venv")], check=True)
    hygiene.install_hooks(flow_repo)
    git(flow_repo, "push", str(remote), "HEAD:refs/heads/topic")
    assert git(flow_repo, "ls-remote", str(remote), "refs/heads/topic").split()[0] == head
    # Destination history never exempts a report still present at the pushed tip.
    report.write_text("new", encoding="utf-8")
    git(flow_repo, "add", report.name)
    tree = git(flow_repo, "write-tree")
    head = git(flow_repo, "commit-tree", tree, "-p", head, "-m", "test: reintroduce report")
    assert hygiene.pre_push(
        flow_repo, [f"refs/heads/topic {head} refs/heads/topic {old}"], str(remote)
    ) == [report.name]


def test_pre_push_refuses_unavailable_destination(flow_repo: Path) -> None:
    head = git(flow_repo, "rev-parse", "HEAD")
    with pytest.raises(ValueError):
        hygiene.pre_push(
            flow_repo,
            [f"refs/heads/main {head} refs/heads/main {'0' * 40}"],
            str(flow_repo / "missing.git"),
        )
