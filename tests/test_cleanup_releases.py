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


from scripts.cleanup_releases import (  # noqa: E402
    delete_release,
    list_releases,
)

# ---- IO 层:用 monkeypatch 桩掉 _api,只测调用契约,不连真实 GitHub ----


class TestListReleases:
    def test_parses_minimal_payload(self, monkeypatch):
        # 单页 2 个 release
        payload = [
            {"id": 11, "tag_name": "v0.2.0", "prerelease": False},
            {"id": 10, "tag_name": "v0.1.9", "prerelease": False},
        ]
        calls = []

        def fake_api(method, url, token, *, expect=200):
            calls.append((method, url))
            return payload if url.endswith("page=1") else []

        monkeypatch.setattr("scripts.cleanup_releases._api", fake_api)
        releases = list_releases("o/r", "tok")
        assert [r.id for r in releases] == [11, 10]
        assert releases[0].version == "0.2.0"
        # 第一页就该停了(返回 < 100)
        assert len(calls) == 1

    def test_paginates_until_empty(self, monkeypatch):
        # 第一页满 100,第二页空 → 停
        page1 = [{"id": i, "tag_name": f"v0.0.{i}", "prerelease": False} for i in range(100)]
        monkeypatch.setattr(
            "scripts.cleanup_releases._api",
            lambda method, url, token, *, expect=200: page1 if url.endswith("page=1") else [],
        )
        releases = list_releases("o/r", "tok")
        assert len(releases) == 100

    def test_skips_unparseable_version(self, monkeypatch, capsys):
        payload = [
            {"id": 11, "tag_name": "v0.2.0", "prerelease": False},
            {"id": 12, "tag_name": "weird-tag", "prerelease": False},  # 无法解析
        ]
        monkeypatch.setattr(
            "scripts.cleanup_releases._api",
            lambda method, url, token, *, expect=200: payload if url.endswith("page=1") else [],
        )
        releases = list_releases("o/r", "tok")
        assert [r.id for r in releases] == [11]  # 只留可解析的
        out = capsys.readouterr().out
        assert "weird-tag" in out  # 有告警


class TestDeleteRelease:
    def test_calls_delete_endpoint(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "scripts.cleanup_releases._api",
            lambda method, url, token, *, expect=204: calls.append((method, url, token, expect)) or None,
        )
        delete_release("o/r", "tok", 42, tag="v0.1.0")
        assert calls == [("DELETE", "https://api.github.com/repos/o/r/releases/42", "tok", 204)]

    def test_404_is_idempotent(self, monkeypatch):
        # _api 对 404 返回 None,delete_release 不应抛错
        monkeypatch.setattr(
            "scripts.cleanup_releases._api",
            lambda method, url, token, *, expect=204: None,
        )
        delete_release("o/r", "tok", 42, tag="v0.1.0")  # 不抛

    def test_non_2xx_raises(self, monkeypatch):
        def boom(method, url, token, *, expect=204):
            raise RuntimeError("403 Forbidden")

        monkeypatch.setattr("scripts.cleanup_releases._api", boom)
        with pytest.raises(RuntimeError, match="403"):
            delete_release("o/r", "tok", 42, tag="v0.1.0")
