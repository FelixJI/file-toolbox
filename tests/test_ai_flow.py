"""AI Flow 本仓适配的真实 Git 契约。"""

import importlib.util
import json
import subprocess
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
