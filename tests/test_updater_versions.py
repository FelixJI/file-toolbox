"""updater 版本来源层测试。"""

import pytest

from file_toolbox.updater.versions import (
    GITHUB_REPO,
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
    @pytest.mark.parametrize(
        "v", ["1.2.3a1", "1.2.3b2", "1.2.3rc1", "1.2.3.dev0", "1.2.3alpha1", "1.2.3beta1"]
    )
    def test_prerelease_versions(self, v):
        assert _is_prerelease(v) is True

    @pytest.mark.parametrize("v", ["1.2.3", "0.1.0", "1.0.0", "2.0", "1.2.3.post1"])
    def test_stable_versions(self, v):
        assert _is_prerelease(v) is False

    def test_invalid_version_is_rejected(self):
        assert _is_prerelease("not-a-version") is True


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

    def test_post_release_is_newer(self):
        assert is_newer("1.2.3.post1", "1.2.3") is True

    @pytest.mark.parametrize("remote,local", [("bad", "1.0"), ("1.0", "bad")])
    def test_invalid_version_is_not_newer(self, remote, local):
        assert is_newer(remote, local) is False


class TestRepoConstants:
    def test_github_repo(self):
        assert GITHUB_REPO == ("FelixJI", "file-toolbox")


class TestRemoteRelease:
    def test_is_frozen(self):
        rel = RemoteRelease("1.0.0", "http://x/a.zip", "http://x/checksums.txt", "github")
        # frozen dataclass 不可变
        with pytest.raises(Exception):
            rel.version = "2.0.0"  # type: ignore[misc]


import json as _json  # noqa: E402
from urllib import error as urlerror  # noqa: E402
from urllib.parse import urlparse  # noqa: E402

from file_toolbox.updater import versions as vmod  # noqa: E402


def _host_is(url: object, host: str) -> bool:
    """精确判断 URL 的 hostname 是否等于 host(避免子串误匹配)。

    CodeQL 会把 `"github.com" in url` 这种子串校验标记为 Incomplete URL
    substring sanitization:host 为 notgithub.com 或 github.com.evil 等也能命中。
    这里用 urlparse().hostname 做权威比对,与生产代码 proxy._is_github 一致。
    """
    raw = url.full_url if hasattr(url, "full_url") else str(url)
    return urlparse(raw).hostname == host


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


class TestFetchLatest:
    def test_returns_first_available(self, monkeypatch):
        """GitHub 返回有效 Release 时,fetch_latest 返回正确结果(版本/URL)。"""

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if _host_is(url, "api.github.com"):
                return _FakeResp(_make_github_payload("v2.0.0"))
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        rel = vmod.fetch_latest()
        assert rel is not None
        assert rel.version == "2.0.0"
        assert rel.source == "github"
        assert rel.zip_url.endswith("-win64.zip")
        assert rel.checksum_url.endswith("checksums.txt")

    def test_source_fails_returns_none(self, monkeypatch):
        """GitHub 抛异常时返回 None。"""

        def fake_urlopen(req, timeout=None):
            raise urlerror.URLError("conn refused")

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        assert vmod.fetch_latest() is None

    def test_prerelease_filtered(self, monkeypatch):
        """GitHub 返回 prerelease → 过滤后返回 None。"""

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if _host_is(url, "api.github.com"):
                return _FakeResp(_make_github_payload("v2.0.0a1"))
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        assert vmod.fetch_latest() is None

    def test_missing_zip_asset_returns_none(self, monkeypatch):
        """Release 没有 zip asset → 该源视为无效。"""

        def fake_urlopen(req, timeout=None):
            return _FakeResp(_json.dumps({"tag_name": "v2.0.0", "assets": []}).encode())

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        assert vmod.fetch_latest() is None


import file_toolbox.updater as upkg  # noqa: E402
from file_toolbox.updater import is_portable_exe  # noqa: E402


class TestIsPortableExe:
    def test_returns_bool(self):
        assert isinstance(is_portable_exe(), bool)

    def test_dev_env_is_false(self, monkeypatch, tmp_path):
        """开发环境(非打包形态,可执行名非 FileToolbox.exe)→ False。"""
        monkeypatch.setattr(upkg.sys, "executable", str(tmp_path / "python.exe"))
        monkeypatch.delattr(upkg.sys, "frozen", raising=False)
        monkeypatch.delattr(upkg.sys, "_MEIPASS", raising=False)
        assert is_portable_exe() is False

    def test_portable_layout_detected(self, monkeypatch, tmp_path):
        """PyInstaller onedir 运行时标记指向 _internal → True。"""
        exe = tmp_path / "FileToolbox.exe"
        exe.touch()
        bundle_dir = tmp_path / "_internal"
        bundle_dir.mkdir()
        (bundle_dir / "python3.dll").touch()
        monkeypatch.setattr(upkg.sys, "executable", str(exe))
        monkeypatch.setattr(upkg.sys, "frozen", True, raising=False)
        monkeypatch.setattr(upkg.sys, "_MEIPASS", str(bundle_dir), raising=False)
        assert is_portable_exe() is True

    def test_exe_name_without_pyinstaller_marker_returns_false(self, monkeypatch, tmp_path):
        """仅伪装 exe 名、没有 PyInstaller 运行时标记 → False。"""
        exe = tmp_path / "FileToolbox.exe"
        exe.touch()
        monkeypatch.setattr(upkg.sys, "executable", str(exe))
        monkeypatch.delattr(upkg.sys, "frozen", raising=False)
        monkeypatch.delattr(upkg.sys, "_MEIPASS", raising=False)
        assert is_portable_exe() is False

    def test_onefile_bundle_outside_install_dir_returns_false(self, monkeypatch, tmp_path):
        """onefile 临时 bundle 不在安装目录内,不能执行整目录替换。"""
        install_dir = tmp_path / "install"
        install_dir.mkdir()
        exe = install_dir / "FileToolbox.exe"
        exe.touch()
        bundle_dir = tmp_path / "_MEI12345"
        bundle_dir.mkdir()
        monkeypatch.setattr(upkg.sys, "executable", str(exe))
        monkeypatch.setattr(upkg.sys, "frozen", True, raising=False)
        monkeypatch.setattr(upkg.sys, "_MEIPASS", str(bundle_dir), raising=False)
        assert is_portable_exe() is False


class TestProxyApplied:
    """_fetch 经代理:GitHub URL 前缀拼接。"""

    def test_fetch_url_is_proxied(self, monkeypatch, tmp_path):
        from file_toolbox.updater import proxy

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(proxy.ENV_VAR, "https://ghproxy.example")

        captured_urls: list[str] = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
            return _FakeResp(_make_github_payload("v2.0.0"))

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        vmod.fetch_latest()
        assert captured_urls, "urlopen 未被调用"
        assert captured_urls[0].startswith("https://ghproxy.example/https://api.github.com/")

    def test_fetch_no_proxy_unchanged(self, monkeypatch, tmp_path):
        from file_toolbox.updater import proxy

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv(proxy.ENV_VAR, raising=False)

        captured_urls: list[str] = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
            return _FakeResp(_make_github_payload("v2.0.0"))

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        vmod.fetch_latest()
        assert captured_urls[0].startswith("https://api.github.com/")


class TestFetchLatestFallback:
    """fetch_latest 遍历代理候选回退:首个失败则试下一个,直到直连兜底。"""

    def test_first_proxy_fails_second_succeeds(self, monkeypatch, tmp_path):
        """候选1(坏代理)失败 → 候选2(好代理)成功。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://bad-proxy.example", "https://good-proxy.example"])
        attempted: list[str] = []

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            attempted.append(url)
            if url.startswith("https://bad-proxy.example/"):
                raise urlerror.URLError("bad proxy down")
            if url.startswith("https://good-proxy.example/"):
                return _FakeResp(_make_github_payload("v2.0.0"))
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        rel = vmod.fetch_latest()
        assert rel is not None
        assert rel.version == "2.0.0"
        # 第一个候选失败,第二个候选成功(中间应有两次 urlopen 调用)
        assert any("bad-proxy.example" in u for u in attempted)
        assert any("good-proxy.example" in u for u in attempted)

    def test_all_proxies_fail_then_direct_succeeds(self, monkeypatch, tmp_path):
        """所有代理失败 → 末尾直连兜底成功。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://bad-proxy.example"])
        attempted: list[str] = []

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            attempted.append(url)
            if url.startswith("https://bad-proxy.example/"):
                raise urlerror.URLError("bad proxy down")
            # 直连(api.github.com 原样)
            if _host_is(url, "api.github.com"):
                return _FakeResp(_make_github_payload("v2.0.0"))
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        rel = vmod.fetch_latest()
        assert rel is not None
        assert rel.version == "2.0.0"
        # 代理失败后走到了直连(api.github.com 无前缀)
        assert any(_host_is(u, "api.github.com") for u in attempted)

    def test_all_candidates_fail_returns_none(self, monkeypatch, tmp_path):
        """代理 + 直连全部失败 → None。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://bad-proxy.example"])

        def fake_urlopen(req, timeout=None):
            raise urlerror.URLError("all down")

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        assert vmod.fetch_latest() is None

    def test_default_direct_only_works(self, monkeypatch, tmp_path):
        """无任何配置时仅直连候选,直连成功即返回。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.updater import proxy

        monkeypatch.delenv(proxy.ENV_VAR, raising=False)

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if _host_is(url, "api.github.com"):
                return _FakeResp(_make_github_payload("v2.0.0"))
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        rel = vmod.fetch_latest()
        assert rel is not None
        assert rel.version == "2.0.0"

    def test_env_proxy_tried_before_settings(self, monkeypatch, tmp_path):
        """环境变量代理排在 settings 代理之前优先尝试。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://settings-proxy.example"])
        monkeypatch.setenv("FILE_TOOLBOX_GH_PROXY", "https://env-proxy.example")
        attempted: list[str] = []

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            attempted.append(url)
            if url.startswith("https://env-proxy.example/"):
                return _FakeResp(_make_github_payload("v3.0.0"))
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr(vmod, "_urlopen", fake_urlopen)
        rel = vmod.fetch_latest()
        assert rel is not None
        assert rel.version == "3.0.0"
        # 第一个尝试的是 env 代理
        assert attempted[0].startswith("https://env-proxy.example/")


class TestBuildReleaseUrl:
    """覆盖 _build_release_url 未知 platform raise(missing 96)。"""

    def test_github_url(self):
        url = vmod._build_release_url("github")
        assert url == "https://api.github.com/repos/FelixJI/file-toolbox/releases/latest"

    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError):
            vmod._build_release_url("unknown")


class TestParseRelease:
    """覆盖 _parse_release 各 None 分支(missing 103-104, 106, 110)。"""

    def test_invalid_json_returns_none(self):
        """非 JSON 字节(UnicodeDecode/ValueError)→ None(missing 103-104)。"""
        assert vmod._parse_release(b"not json", "github") is None

    def test_non_dict_payload_returns_none(self):
        """JSON 解析出 list(非 dict)→ None(missing 106)。"""
        assert vmod._parse_release(_json.dumps([1, 2]).encode(), "github") is None

    def test_missing_tag_returns_none(self):
        """dict 无 tag_name → None(missing 110)。"""
        assert vmod._parse_release(_json.dumps({"assets": []}).encode(), "github") is None

    def test_tag_without_checksum_asset_returns_none(self):
        """有 tag 但无 checksum asset(或 zip)→ None。"""
        payload = _json.dumps({"tag_name": "v1.0.0", "assets": []}).encode()
        assert vmod._parse_release(payload, "github") is None

    def test_full_valid_payload_returns_release(self):
        """完整有效 payload → RemoteRelease。"""
        payload = _json.dumps(
            {
                "tag_name": "v1.0.0",
                "assets": [
                    {
                        "name": "FileToolbox-1.0.0-win64.zip",
                        "browser_download_url": "http://x/a.zip",
                    },
                    {"name": "checksums.txt", "browser_download_url": "http://x/checksums.txt"},
                ],
            }
        ).encode()
        rel = vmod._parse_release(payload, "github")
        assert isinstance(rel, RemoteRelease)
        assert rel.version == "1.0.0"
        assert rel.zip_url == "http://x/a.zip"
        assert rel.checksum_url == "http://x/checksums.txt"
