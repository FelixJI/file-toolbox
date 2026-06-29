"""updater 版本来源层测试。"""

import pytest

from file_toolbox.updater.versions import (
    GITHUB_REPO,
    GITEE_REPO,
    RemoteRelease,
    _is_prerelease,
    is_newer,
    strip_v_prefix,
)


class TestStripVPrefix:
    def test_with_v(self):
        assert strip_v_prefix("v1.2.0") == "1.2.0"

    def test_without_v(self):
        assert strip_v_prefix("1.2.0") == "1.2.0"


class TestIsPrerelease:
    @pytest.mark.parametrize("v", ["1.2.3a1", "1.2.3b2", "1.2.3rc1", "1.2.3.dev0", "1.2.3alpha1", "1.2.3beta1"])
    def test_prerelease_versions(self, v):
        assert _is_prerelease(v) is True

    @pytest.mark.parametrize("v", ["1.2.3", "0.1.0", "1.0.0", "2.0"])
    def test_stable_versions(self, v):
        assert _is_prerelease(v) is False


class TestIsNewer:
    def test_higher_patch(self):
        assert is_newer("1.2.3", "1.2.2") is True

    def test_lower_patch(self):
        assert is_newer("1.2.1", "1.2.2") is False

    def test_higher_minor(self):
        assert is_newer("1.3.0", "1.2.9") is True

    def test_higher_major(self):
        assert is_newer("2.0.0", "1.9.9") is True

    def test_equal(self):
        assert is_newer("1.2.3", "1.2.3") is False

    def test_fewer_segments(self):
        # 1.2 视作 1.2.0
        assert is_newer("1.2.1", "1.2") is True

    def test_local_version_suffix_ignored(self):
        # 带 +local 后缀的(开发态 0.0.0+unknown)不影响比对
        assert is_newer("1.2.3", "0.0.0+unknown") is True


class TestRepoConstants:
    def test_github_repo(self):
        assert GITHUB_REPO == ("FelixJI", "file-toolbox")

    def test_gitee_repo(self):
        assert GITEE_REPO == ("felixjii", "file-toolbox")


class TestRemoteRelease:
    def test_is_frozen(self):
        rel = RemoteRelease("1.0.0", "http://x/a.zip", "http://x/checksums.txt", "github")
        # frozen dataclass 不可变
        with pytest.raises(Exception):
            rel.version = "2.0.0"  # type: ignore[misc]


import json as _json  # noqa: E402
from urllib import error as urlerror  # noqa: E402

from file_toolbox.updater import versions as vmod  # noqa: E402


class _FakeResp:
    """模拟 urllib 响应上下文管理器。"""

    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._payload


def _make_github_payload(tag: str) -> bytes:
    """构造 GitHub releases/latest 的 JSON。"""
    return _json.dumps(
        {
            "tag_name": tag,
            "assets": [
                {
                    "name": f"FileToolbox-{tag.lstrip('v')}-win64.zip",
                    "browser_download_url": (
                        f"https://github.com/FelixJI/file-toolbox/releases/download/"
                        f"{tag}/FileToolbox-{tag.lstrip('v')}-win64.zip"
                    ),
                },
                {
                    "name": "checksums.txt",
                    "browser_download_url": (
                        "https://github.com/FelixJI/file-toolbox/releases/download/checksums.txt"
                    ),
                },
            ],
        }
    ).encode()


def _make_gitee_payload(tag: str) -> bytes:
    """构造 Gitee releases/latest 的 JSON(字段名与 GitHub 一致)。"""
    return _json.dumps(
        {
            "tag_name": tag,
            "assets": [
                {
                    "name": f"FileToolbox-{tag.lstrip('v')}-win64.zip",
                    "browser_download_url": (
                        f"https://gitee.com/felixjii/file-toolbox/releases/download/"
                        f"{tag}/FileToolbox-{tag.lstrip('v')}-win64.zip"
                    ),
                },
                {
                    "name": "checksums.txt",
                    "browser_download_url": (
                        "https://gitee.com/felixjii/file-toolbox/releases/download/checksums.txt"
                    ),
                },
            ],
        }
    ).encode()


class TestFetchLatest:
    def test_returns_first_available(self, monkeypatch):
        """两源都能返回时,fetch_latest 返回有效结果(版本/URL 正确)。"""
        calls: list[str] = []

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            calls.append(url)
            if "github.com" in url:
                return _FakeResp(_make_github_payload("v2.0.0"))
            if "gitee.com" in url:
                return _FakeResp(_make_gitee_payload("v2.0.0"))
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        rel = vmod.fetch_latest()
        assert rel is not None
        assert rel.version == "2.0.0"
        assert rel.source in ("github", "gitee")
        assert rel.zip_url.endswith("-win64.zip")
        assert rel.checksum_url.endswith("checksums.txt")

    def test_one_source_fails_other_succeeds(self, monkeypatch):
        """一源抛异常时,另一源仍能返回。"""

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "github.com" in url:
                raise urlerror.URLError("conn refused")
            return _FakeResp(_make_gitee_payload("v2.0.0"))

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        rel = vmod.fetch_latest()
        assert rel is not None
        assert rel.source == "gitee"

    def test_both_fail_returns_none(self, monkeypatch):
        def fake_urlopen(req, timeout=None):
            raise urlerror.URLError("no network")

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        assert vmod.fetch_latest() is None

    def test_prerelease_filtered(self, monkeypatch):
        """两源都返回 prerelease → 过滤后返回 None。"""

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "github.com" in url:
                return _FakeResp(_make_github_payload("v2.0.0a1"))
            return _FakeResp(_make_gitee_payload("v2.0.0b1"))

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        assert vmod.fetch_latest() is None

    def test_missing_zip_asset_returns_none(self, monkeypatch):
        """Release 没有 zip asset → 该源视为无效。"""

        def fake_urlopen(req, timeout=None):
            return _FakeResp(_json.dumps({"tag_name": "v2.0.0", "assets": []}).encode())

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        assert vmod.fetch_latest() is None
