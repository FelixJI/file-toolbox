"""PR 标题约定测试。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_pr_title import main, title_error  # noqa: E402


@pytest.mark.parametrize(
    "title",
    [
        "feat: 添加批量重命名",
        "fix(release): 修复发布竞态",
        "feat(core)!: 调整配置格式",
        "chore(main): release 0.2.0",
        "deps: update pyside6",
    ],
)
def test_accepts_conventional_titles(title: str) -> None:
    assert title_error(title) is None


@pytest.mark.parametrize(
    "title",
    [
        "",
        "更新发布流程",
        "Fix: uppercase type",
        "fix missing colon",
        "fix(): empty scope",
        "unknown: unsupported type",
    ],
)
def test_rejects_non_conventional_titles(title: str) -> None:
    assert title_error(title) is not None


def test_main_reads_title_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("PR_TITLE", "fix: 修复错误")
    assert main() == 0


def test_main_fails_without_title(monkeypatch) -> None:
    monkeypatch.delenv("PR_TITLE", raising=False)
    assert main() == 1
