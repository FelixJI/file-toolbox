"""release.py 交互模式测试。

策略:CliRunner 桩掉 run_interactive,只验证「是否进入交互」与「非交互路径参数透传」。
真正的交互体(Step 1-4)在后续任务用更细的纯函数测试覆盖。
"""

import sys
from pathlib import Path

from typer.testing import CliRunner

# 让 tests 能 import scripts 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import release as rel  # noqa: E402

runner = CliRunner()


def test_no_args_enters_interactive(monkeypatch):
    """无参数运行 → 调用 run_interactive。"""
    called = {"n": 0}

    def fake_interactive():
        called["n"] += 1

    monkeypatch.setattr(rel, "run_interactive", fake_interactive)
    r = runner.invoke(rel.cli, [])
    assert r.exit_code == 0
    assert called["n"] == 1


def test_part_arg_skips_interactive(monkeypatch):
    """带 part → 不进交互(走原 bump 逻辑,这里桩掉 _run 防止真跑 bump)。"""
    called = {"interactive": 0, "run": 0}

    monkeypatch.setattr(rel, "run_interactive", lambda: called.__setitem__("interactive", 1))
    monkeypatch.setattr(rel, "_run", lambda *a, **k: called.__setitem__("run", called["run"] + 1))

    r = runner.invoke(rel.cli, ["patch", "--skip-build"])
    assert r.exit_code == 0
    assert called["interactive"] == 0
    assert called["run"] >= 1  # 走了原 bump 路径


def test_set_arg_skips_interactive(monkeypatch):
    called = {"interactive": 0}
    monkeypatch.setattr(rel, "run_interactive", lambda: called.__setitem__("interactive", 1))
    monkeypatch.setattr(rel, "_run", lambda *a, **k: None)
    r = runner.invoke(rel.cli, ["--set", "1.2.3", "--skip-build"])
    assert r.exit_code == 0
    assert called["interactive"] == 0


def test_ci_skips_interactive(monkeypatch):
    called = {"interactive": 0}
    monkeypatch.setattr(rel, "run_interactive", lambda: called.__setitem__("interactive", 1))
    monkeypatch.setattr(rel, "_run", lambda *a, **k: None)
    r = runner.invoke(rel.cli, ["patch", "--ci"])
    assert r.exit_code == 0
    assert called["interactive"] == 0


class TestGitQueries:
    """Step 0 前置检查用的 git 查询纯函数(用 tmp_path 建 mini git 仓)。"""

    def _init_repo(self, tmp_path: Path) -> Path:
        import os
        import subprocess

        root = tmp_path / "repo"
        root.mkdir()
        env = {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        full_env = {**os.environ, **env}

        def run(*a):
            subprocess.run(
                ["git", *a], cwd=str(root), check=True, capture_output=True, env=full_env
            )

        run("init", "-b", "main")
        run("config", "user.name", "t")
        run("config", "user.email", "t@t")
        (root / "f.txt").write_text("x")
        run("add", ".")
        run("commit", "-m", "init")
        return root

    def test_git_branch_main(self, tmp_path):
        root = self._init_repo(tmp_path)
        assert rel._git_branch(root) == "main"

    def test_git_branch_other(self, tmp_path):
        import subprocess

        root = self._init_repo(tmp_path)
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=str(root),
            check=True,
            capture_output=True,
        )
        assert rel._git_branch(root) == "feature"

    def test_unpushed_empty_when_no_upstream(self, tmp_path):
        """无 upstream 时按 spec 不算未推送(查询失败→空列表)。"""
        root = self._init_repo(tmp_path)
        # 无上游,unpushed 应为空(不报错)
        assert rel._unpushed_commits(root) == []

    def test_unpushed_detects_local_commits(self, tmp_path):
        """有上游且本地领先时,返回未推送提交列表。"""
        import subprocess

        root = self._init_repo(tmp_path)
        bare = tmp_path / "origin.git"
        subprocess.run(
            ["git", "init", "--bare", str(bare)], check=True, capture_output=True
        )

        def g(*a):
            subprocess.run(
                ["git", *a], cwd=str(root), check=True, capture_output=True
            )

        g("remote", "add", "origin", str(bare))
        g("push", "-u", "origin", "main")
        # 再造一个本地提交(未推送)
        (root / "g.txt").write_text("y")
        g("add", ".")
        g("commit", "-m", "unpushed")
        commits = rel._unpushed_commits(root)
        assert len(commits) == 1
        assert "unpushed" in commits[0]
