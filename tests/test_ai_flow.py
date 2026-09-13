"""AI Flow 本仓适配的真实 Git 契约。"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "ai_flow_runner", Path(__file__).parents[1] / ".ai-flow/scripts/flow.py"
)
assert SPEC is not None and SPEC.loader is not None
flow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(flow)


@pytest.fixture
def flow_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "tracked.txt").write_text("before", encoding="utf-8")
    flow.git(tmp_path, "add", "tracked.txt")
    flow.git(
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


def test_content_change_detected_with_same_porcelain(flow_repo: Path) -> None:
    tracked = flow_repo / "tracked.txt"
    tracked.write_text("first!", encoding="utf-8")
    new = flow_repo / "untracked.bin"
    new.write_bytes(b"\x00\xff")
    before = flow.fingerprint(flow_repo)
    tracked.write_text("second", encoding="utf-8")
    after_tracked = flow.fingerprint(flow_repo)
    assert before["status"] == after_tracked["status"]
    assert before != after_tracked
    new.write_bytes(b"\xff\x00")
    assert after_tracked != flow.fingerprint(flow_repo)


def test_policy_change_detected_but_runtime_ignored(flow_repo: Path) -> None:
    policy = flow_repo / ".ai-flow/project.json"
    policy.parent.mkdir()
    policy.write_text('{"enabled":false}', encoding="utf-8")
    before = flow.policy_snapshot(flow_repo)
    runtime = policy.parent / "runtime"
    runtime.mkdir()
    (runtime / "receipt.json").write_text("{}", encoding="utf-8")
    assert flow.policy_snapshot(flow_repo) == before
    policy.write_text('{"enabled":true}', encoding="utf-8")
    assert flow.policy_snapshot(flow_repo) != before


def test_branch_uses_project_prefix(flow_repo: Path) -> None:
    folder = flow_repo / ".git/flow-test"
    folder.mkdir()
    state = {
        "run_id": "test",
        "sequence": 1,
        "review_needed": {},
        "managed_branches": [],
        "events": [],
        "pending": None,
    }
    decision = {
        "action": "BRANCH",
        "task_id": "test",
        "instructions": json.dumps(
            {
                "branch": "codex/bootstrap-smoke",
                "start_sha": flow.git(flow_repo, "rev-parse", "HEAD"),
            }
        ),
    }
    cfg = {"allow_local_git_writes": True, "default_branch": "main"}
    flow.local_git(flow_repo, folder, state, cfg, decision)
    assert flow.git(flow_repo, "branch", "--show-current") == "codex/bootstrap-smoke"
    decision["instructions"] = json.dumps(
        {"branch": "ai/wrong-prefix", "start_sha": flow.git(flow_repo, "rev-parse", "HEAD")}
    )
    with pytest.raises(ValueError, match="codex/"):
        flow.local_git(flow_repo, folder, state, cfg, decision)


def test_commit_rejects_unlisted_staged_content(flow_repo: Path) -> None:
    flow.git(flow_repo, "switch", "-c", "codex/commit-boundary")
    original = flow_repo / "tracked.txt"
    original.write_text("staged change", encoding="utf-8")
    flow.git(flow_repo, "add", "tracked.txt")
    original.write_text("before", encoding="utf-8")
    (flow_repo / "visible.txt").write_text("intended change", encoding="utf-8")
    head = flow.git(flow_repo, "rev-parse", "HEAD")
    state = {"run_id": "test", "sequence": 1, "review_needed": {}}
    decision = {
        "action": "COMMIT",
        "task_id": "test",
        "instructions": json.dumps({"message": "test(flow): 显式路径", "paths": ["visible.txt"]}),
    }
    with pytest.raises(ValueError, match="exactly match ALL"):
        flow.local_git(
            flow_repo,
            flow_repo / ".git",
            state,
            {"allow_local_git_writes": True, "default_branch": "main"},
            decision,
        )
    assert flow.git(flow_repo, "rev-parse", "HEAD") == head
    assert flow.git(flow_repo, "show", ":tracked.txt") == "staged change"


@pytest.mark.parametrize("role, mode", [("CONTROLLER", "read-only"), ("CODEX", "workspace-write")])
def test_native_thread_uses_schema_sandbox_mode(flow_repo: Path, role: str, mode: str) -> None:
    from unittest.mock import Mock

    import native_rpc

    client = native_rpc.CodexClient.__new__(native_rpc.CodexClient)
    client.root = flow_repo
    client.cfg = {}
    client.wire = Mock()
    client.wire.request.return_value = {"thread": {"id": "new-thread"}}
    assert client.select_thread(None, role) == "new-thread"
    params = client.wire.request.call_args.args[1]
    assert params["sandbox"] == mode
    assert params["approvalPolicy"] == "never"


@pytest.mark.parametrize("boundary", ["commit", "push"])
def test_git_executes_artifact_hooks(flow_repo: Path, boundary: str) -> None:
    import hygiene

    flow.git(flow_repo, "config", "user.name", "Test")
    flow.git(flow_repo, "config", "user.email", "test@example.invalid")
    guard = flow_repo / ".ai-flow/scripts/hygiene.py"
    guard.parent.mkdir(parents=True)
    shutil.copyfile(Path(hygiene.__file__), guard)
    # The hook runs through uv, in an isolated local environment without dependency downloads.
    subprocess.run(["uv", "venv", "--python", sys.executable, str(flow_repo / ".venv")], check=True)
    (flow_repo / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    flow.git(flow_repo, "add", ".ai-flow/scripts/hygiene.py", ".gitignore")
    flow.git(flow_repo, "commit", "-qm", "test: guard fixture")
    report = flow_repo / "BOOTSTRAP_RESULT.md"
    report.write_text("local report", encoding="utf-8")
    flow.git(flow_repo, "add", report.name)
    if boundary == "push":
        # Create the legacy report before installing guards; exercise a real pre-push invocation.
        flow.git(flow_repo, "commit", "-qm", "test: legacy local report")
        remote = flow_repo.parent / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True)
        flow.git(flow_repo, "remote", "add", "local-test", str(remote))
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
        flow.git(flow_repo, "rm", "--cached", report.name)
        report.unlink()
        # Shared hooks also work on an older branch without the new guard source.
        flow.git(flow_repo, "rm", ".ai-flow/scripts/hygiene.py")
        (flow_repo / "design.md").write_text("persistent design", encoding="utf-8")
        flow.git(flow_repo, "add", "design.md")
        flow.git(flow_repo, "commit", "-qm", "test: allow persistent document")
    else:
        refs = subprocess.run(["git", "--git-dir", str(remote), "show-ref"], capture_output=True)
        assert refs.returncode == 1 and not refs.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing contract")
@pytest.mark.parametrize("release_reader", [True, False])
def test_atomic_state_with_concurrent_reader(tmp_path: Path, release_reader: bool) -> None:
    import threading

    state = tmp_path / "state.json"
    state.write_text('{"old":true}', encoding="utf-8")
    reader = state.open("rb")
    timer = threading.Timer(0.05, reader.close) if release_reader else None
    try:
        if timer:
            timer.start()
            flow.atomic(state, '{"new":true}')
            assert json.loads(state.read_text()) == {"new": True}
        else:
            with pytest.raises(PermissionError):
                flow.atomic(state, '{"new":true}')
            assert json.loads(state.read_text()) == {"old": True}
    finally:
        reader.close()
        if timer:
            timer.join()
    assert not list(tmp_path.glob("*.tmp"))
