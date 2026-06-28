"""release.py 交互模式测试。

策略:CliRunner 桩掉 run_interactive,只验证「是否进入交互」与「非交互路径参数透传」。
真正的交互体(Step 1-4)在后续任务用更细的纯函数测试覆盖。
"""

import sys
from pathlib import Path

import pytest
import typer
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


class TestVersionChoice:
    """Step 1: 数字选择 → (part, new_version) 映射。part='__custom__' 表示自定义版本。"""

    def test_patch(self):
        assert rel._resolve_version_choice("1", "0.1.0") == ("patch", "0.1.1")

    def test_minor(self):
        assert rel._resolve_version_choice("2", "0.1.0") == ("minor", "0.2.0")

    def test_major(self):
        assert rel._resolve_version_choice("3", "0.1.0") == ("major", "1.0.0")

    def test_prerelease(self):
        assert rel._resolve_version_choice("4", "0.1.0") == ("prerelease", "0.1.1a1")

    def test_custom_marker(self):
        # 选 5 → 返回特殊标记,具体版本号由后续 prompt+校验处理
        assert rel._resolve_version_choice("5", "0.1.0") == ("__custom__", None)

    def test_invalid_choice_returns_none(self):
        # 非法输入(非 1-5)→ None,调用方负责重新提示
        assert rel._resolve_version_choice("9", "0.1.0") is None
        assert rel._resolve_version_choice("abc", "0.1.0") is None


class TestCustomVersionValidate:
    def test_valid(self):
        assert rel._validate_custom_version("1.2.3") == "1.2.3"

    def test_invalid_returns_none(self):
        assert rel._validate_custom_version("not-a-ver") is None
        assert rel._validate_custom_version("1.2.x") is None


class TestInteractiveFlow:
    """run_interactive 编排:用 monkeypatch 桩掉所有 IO 与子进程,验证分支与调用。"""

    def _stub_clean_state(self, monkeypatch, tmp_path):
        """桩掉 Step 0 所有检查为「干净 main 无未推送」状态。"""
        monkeypatch.setattr(rel, "_ROOT", tmp_path)
        monkeypatch.setattr(rel, "working_tree_clean", lambda root: True)
        monkeypatch.setattr(rel, "_git_branch", lambda root: "main")
        monkeypatch.setattr(rel, "_unpushed_commits", lambda root: [])
        monkeypatch.setattr(rel, "read_pyproject_version", lambda p: "0.1.0")

    def test_dirty_workspace_aborts(self, monkeypatch, tmp_path, capsys):
        # 工作区脏 → 直接退出,不进菜单、不调 _run
        monkeypatch.setattr(rel, "_ROOT", tmp_path)
        monkeypatch.setattr(rel, "working_tree_clean", lambda root: False)
        run_called = {"n": 0}
        monkeypatch.setattr(
            rel, "_run", lambda *a, **k: run_called.__setitem__("n", run_called["n"] + 1)
        )

        with pytest.raises(typer.Exit) as exc:
            rel.run_interactive()
        assert exc.value.exit_code == 1
        assert run_called["n"] == 0
        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "工作区" in out or "干净" in out  # 错误提示

    def test_confirm_no_runs_nothing(self, monkeypatch, tmp_path):
        """确认=否 → 不调用任何 _run(bump/build 都不跑)。"""
        self._stub_clean_state(monkeypatch, tmp_path)
        run_called = {"n": 0}
        monkeypatch.setattr(
            rel, "_run", lambda *a, **k: run_called.__setitem__("n", run_called["n"] + 1)
        )

        # 序列:选 minor(2) → 不打包(N) → 总览确认否(N)
        inputs = iter(["2", "N", "N"])
        monkeypatch.setattr(rel.typer, "prompt", lambda *a, **k: next(inputs))
        monkeypatch.setattr(rel.typer, "confirm", lambda *a, **k: next(inputs) in ("y", "Y"))

        rel.run_interactive()
        assert run_called["n"] == 0

    def test_ctrl_c_aborts_cleanly(self, monkeypatch, tmp_path, capsys):
        """交互阶段 Ctrl+C → 退出码 130,不调 _run,提示已取消。"""
        self._stub_clean_state(monkeypatch, tmp_path)
        run_called = {"n": 0}
        monkeypatch.setattr(
            rel, "_run", lambda *a, **k: run_called.__setitem__("n", run_called["n"] + 1)
        )
        # prompt 抛 KeyboardInterrupt(模拟用户在选版本时 Ctrl+C)
        def raise_kb(*a, **k):
            raise KeyboardInterrupt

        monkeypatch.setattr(rel.typer, "prompt", raise_kb)

        with pytest.raises(typer.Exit) as exc:
            rel.run_interactive()
        assert exc.value.exit_code == 130
        assert run_called["n"] == 0
        out = capsys.readouterr().out
        assert "取消" in out
