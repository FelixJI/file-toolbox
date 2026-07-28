"""cleanup_releases.py 纯函数 + IO 层测试。"""

import sys
from pathlib import Path

# 让 tests 能 import scripts 包(沿用 test_bump_version.py 的做法)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402, F401

from scripts.cleanup_releases import (  # noqa: E402
    Release,
    select_releases_to_delete,
)


def _r(tag: str, *, rid: int = 0, pre: bool = False) -> Release:
    """构造 Release 的便捷工厂:tag="v0.2.0" → version="0.2.0"。"""
    return Release(id=rid, tag=tag, version=tag.lstrip("v"), is_prerelease=pre)


class TestSelectReleasesToDelete:
    def test_keeps_newest_five_deletes_rest(self):
        releases = [_r(f"v0.1.{i}") for i in range(1, 8)]  # v0.1.1 .. v0.1.7
        to_delete = select_releases_to_delete(releases, keep=5)
        # 降序:0.1.7,0.1.6,...,0.1.3 保留;删 0.1.2,0.1.1
        assert {r.version for r in to_delete} == {"0.1.1", "0.1.2"}

    def test_unsorted_input_still_sorted_correctly(self):
        # 输入乱序,结果应按版本号降序判定
        releases = [_r("v0.1.3"), _r("v0.1.1"), _r("v0.1.2")]
        to_delete = select_releases_to_delete(releases, keep=2)
        assert {r.version for r in to_delete} == {"0.1.1"}

    def test_count_le_keep_returns_empty(self):
        releases = [_r("v0.1.1"), _r("v0.1.2")]
        assert select_releases_to_delete(releases, keep=5) == []

    def test_keep_zero_returns_all(self):
        releases = [_r("v0.1.1"), _r("v0.1.2")]
        assert len(select_releases_to_delete(releases, keep=0)) == 2

    def test_prerelease_ranks_below_release_same_number(self):
        # 0.2.0a1 < 0.2.0(packaging.Version 语义),二者统一计入 keep
        releases = [_r("v0.2.0"), _r("v0.2.0a1", pre=True), _r("v0.1.9")]
        to_delete = select_releases_to_delete(releases, keep=2)
        # 降序:0.2.0,0.2.0a1 保留;删 0.1.9
        assert {r.version for r in to_delete} == {"0.1.9"}

    def test_prerelease_counts_toward_keep_total(self):
        # 共 3 个,keep=2 → 删最旧一个(预发布版也参与计数)
        releases = [_r("v0.2.0"), _r("v0.2.0a1", pre=True), _r("v0.1.9")]
        kept = select_releases_to_delete(releases, keep=2)
        assert len(kept) == 1  # 只删 1 个,总数 3 - keep 2 = 1

    def test_empty_input(self):
        assert select_releases_to_delete([], keep=5) == []
