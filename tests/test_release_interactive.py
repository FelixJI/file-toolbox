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
