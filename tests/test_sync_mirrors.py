"""sync_mirrors.py 测试:纯函数 + 网络 mock + 端到端桩测。"""

import sys
from pathlib import Path

# 让 tests 能 import scripts 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from scripts.sync_mirrors import parse_owner_repo  # noqa: E402


class TestParseOwnerRepo:
    def test_gitee_with_git_suffix(self):
        url = "https://gitee.com/felixjii/file-toolbox.git"
        assert parse_owner_repo(url) == ("felixjii", "file-toolbox")

    def test_cnb_without_git_suffix(self):
        url = "https://cnb.cool/feljii/file-toolbox"
        assert parse_owner_repo(url) == ("feljii", "file-toolbox")

    def test_github_with_git_suffix(self):
        url = "https://github.com/FelixJI/file-toolbox.git"
        assert parse_owner_repo(url) == ("FelixJI", "file-toolbox")

    def test_strips_trailing_slash(self):
        url = "https://gitee.com/felixjii/file-toolbox/"
        assert parse_owner_repo(url) == ("felixjii", "file-toolbox")

    def test_unparseable_raises(self):
        with pytest.raises(ValueError):
            parse_owner_repo("not-a-url")


from scripts.sync_mirrors import version_to_tag, build_push_url  # noqa: E402


class TestVersionToTag:
    def test_plain_release(self):
        assert version_to_tag("1.2.3") == "v1.2.3"

    def test_prerelease(self):
        assert version_to_tag("1.2.3a1") == "v1.2.3a1"


class TestBuildPushUrl:
    def test_gitee_url(self):
        url = build_push_url("https://gitee.com/felixjii/file-toolbox.git", "TOK", "gitee")
        assert url == "https://TOK@gitee.com/felixjii/file-toolbox.git"

    def test_cnb_url(self):
        url = build_push_url("https://cnb.cool/feljii/file-toolbox", "TOK", "cnb")
        # CNB 用户名固定为 cnb
        assert url == "https://cnb:TOK@cnb.cool/feljii/file-toolbox"

    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError):
            build_push_url("https://example.com/a/b", "TOK", "weird")


from scripts.sync_mirrors import releases_to_delete  # noqa: E402


class TestReleasesToDelete:
    def _rel(self, rid, created_at):
        return {"id": rid, "created_at": created_at}

    def test_keeps_latest_five(self):
        """7 个 release,保留最近 5 个(created_at 降序),删 2 个最旧。"""
        rels = [
            self._rel(1, "2026-01-01T00:00:00Z"),
            self._rel(2, "2026-02-01T00:00:00Z"),
            self._rel(3, "2026-03-01T00:00:00Z"),
            self._rel(4, "2026-04-01T00:00:00Z"),
            self._rel(5, "2026-05-01T00:00:00Z"),
            self._rel(6, "2026-06-01T00:00:00Z"),
            self._rel(7, "2026-07-01T00:00:00Z"),
        ]
        to_delete = releases_to_delete(rels, keep=5)
        # 保留 7,6,5,4,3;删 1,2
        assert set(to_delete) == {1, 2}

    def test_under_five_deletes_none(self):
        rels = [self._rel(1, "2026-01-01T00:00:00Z"), self._rel(2, "2026-02-01T00:00:00Z")]
        assert releases_to_delete(rels, keep=5) == []

    def test_exactly_five_deletes_none(self):
        rels = [self._rel(i, f"2026-0{i}-01T00:00:00Z") for i in range(1, 6)]
        assert releases_to_delete(rels, keep=5) == []

    def test_empty_list(self):
        assert releases_to_delete([], keep=5) == []

    def test_includes_prereleases(self):
        """预发布版同样计入保留窗口(按 created_at 排序,不区分类型)。"""
        rels = [
            self._rel(1, "2026-01-01T00:00:00Z"),
            self._rel(2, "2026-02-01T00:00:00Z"),
            self._rel(3, "2026-03-01T00:00:00Z"),
            self._rel(4, "2026-04-01T00:00:00Z"),
            self._rel(5, "2026-05-01T00:00:00Z"),
            self._rel(6, "2026-06-01T00:00:00Z"),
        ]
        assert releases_to_delete(rels, keep=5) == [1]

    def test_custom_keep(self):
        rels = [self._rel(i, f"2026-0{i}-01T00:00:00Z") for i in range(1, 5)]
        assert releases_to_delete(rels, keep=2) == [1, 2]
