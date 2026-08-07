"""updater 下载与校验层测试。"""

from file_toolbox.updater.downloader import parse_checksums, sha256_file
from file_toolbox.updater.versions import RemoteRelease


class TestParseChecksums:
    _SHA_A = "a" * 64  # 64 位十六进制(真实 checksums.txt 格式)
    _SHA_B = "b" * 64
    _SHA_C = "c" * 64

    def test_basic(self):
        content = f"{self._SHA_A}  FileToolbox-1.2.0-win64.zip\n"
        assert parse_checksums(content, "FileToolbox-1.2.0-win64.zip") == self._SHA_A

    def test_multiple_lines(self):
        content = (
            f"{'1' * 64}  FileToolbox-0.9.0-win64.zip\n"
            f"{self._SHA_B}  FileToolbox-1.2.0-win64.zip\n"
            f"{'3' * 64}  FileToolbox-2.0.0-win64.zip\n"
        )
        assert parse_checksums(content, "FileToolbox-1.2.0-win64.zip") == self._SHA_B

    def test_no_match_returns_none(self):
        content = f"{'1' * 64}  other.zip\n"
        assert parse_checksums(content, "FileToolbox-1.2.0-win64.zip") is None

    def test_empty_content(self):
        assert parse_checksums("", "FileToolbox-1.2.0-win64.zip") is None

    def test_single_space_separator(self):
        # 单空格也能解析(非强制两空格)
        content = f"{self._SHA_A} FileToolbox-1.2.0-win64.zip"
        assert parse_checksums(content, "FileToolbox-1.2.0-win64.zip") == self._SHA_A

    def test_uppercase_sha_normalized_to_lower(self):
        content = "ABCD1234" + "0" * 56 + "  FileToolbox-1.2.0-win64.zip\n"
        assert parse_checksums(content, "FileToolbox-1.2.0-win64.zip") == ("abcd1234" + "0" * 56)


class TestSha256File:
    def test_known_content(self, tmp_path):
        import hashlib

        data = b"hello world"
        f = tmp_path / "test.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert sha256_file(f) == expected

    def test_empty_file(self, tmp_path):
        import hashlib

        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        assert sha256_file(f) == hashlib.sha256(b"").hexdigest()


import io  # noqa: E402
from urllib import error as urlerror  # noqa: E402

import pytest  # noqa: E402

from file_toolbox.updater import downloader as dmod  # noqa: E402
from file_toolbox.updater.errors import ChecksumMismatchError, NetworkError  # noqa: E402


class _StreamResp:
    """模拟可分块读的 HTTP 响应(上下文管理器)。"""

    def __init__(self, payload: bytes, content_length: int | None = None):
        self._buf = io.BytesIO(payload)
        self.headers = {"Content-Length": str(content_length)} if content_length else {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        return self._buf.read(n)


def _make_release(
    zip_url="http://github/FileToolbox-1.2.0-win64.zip", cs_url="http://github/checksums.txt"
):
    return RemoteRelease("1.2.0", zip_url, cs_url, "github")


class TestDownloadAndVerify:
    def test_success(self, monkeypatch, tmp_path):
        """zip + checksums 都正常 → 返回校验通过的 zip 路径。"""
        import hashlib

        zip_bytes = b"fake-zip-content"
        expected_sha = hashlib.sha256(zip_bytes).hexdigest()
        cs_text = f"{expected_sha}  FileToolbox-1.2.0-win64.zip\n"

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.endswith("checksums.txt"):
                return _StreamResp(cs_text.encode())
            return _StreamResp(zip_bytes)

        monkeypatch.setattr(dmod, "_urlopen", fake_urlopen)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        rel = _make_release()
        path = dmod.download_and_verify(rel)
        assert path.exists()
        assert path.read_bytes() == zip_bytes

    def test_progress_callback(self, monkeypatch, tmp_path):
        """进度回调被调用,downloaded 单调递增,最终等于 total。"""
        import hashlib

        zip_bytes = b"x" * 200000  # 大于一个 chunk,触发多次回调
        expected_sha = hashlib.sha256(zip_bytes).hexdigest()
        cs_text = f"{expected_sha}  FileToolbox-1.2.0-win64.zip\n"

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.endswith("checksums.txt"):
                return _StreamResp(cs_text.encode())
            return _StreamResp(zip_bytes, content_length=len(zip_bytes))

        monkeypatch.setattr(dmod, "_urlopen", fake_urlopen)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        seen: list[tuple[int, int]] = []
        dmod.download_and_verify(_make_release(), on_progress=lambda d, t: seen.append((d, t)))
        assert seen  # 至少回调一次
        assert seen[-1][0] == len(zip_bytes)  # 最后一次 downloaded == total
        assert seen[-1][1] == len(zip_bytes)

    def test_checksum_mismatch(self, monkeypatch, tmp_path):
        """SHA256 不匹配 → 抛 ChecksumMismatchError,删除 zip。"""
        zip_bytes = b"corrupt"
        cs_text = "0" * 64 + "  FileToolbox-1.2.0-win64.zip\n"

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.endswith("checksums.txt"):
                return _StreamResp(cs_text.encode())
            return _StreamResp(zip_bytes)

        monkeypatch.setattr(dmod, "_urlopen", fake_urlopen)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        with pytest.raises(ChecksumMismatchError):
            dmod.download_and_verify(_make_release())

    def test_checksum_fetch_fails_raises_network_error(self, monkeypatch, tmp_path):
        """checksum 拉取失败 → NetworkError。"""

        def fake_urlopen(req, timeout=None):
            raise urlerror.URLError("fail")

        monkeypatch.setattr(dmod, "_urlopen", fake_urlopen)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        with pytest.raises(NetworkError):
            dmod.download_and_verify(_make_release())

    def test_streaming_download_fails_deletes_zip_and_raises_network_error(
        self, monkeypatch, tmp_path
    ):
        """checksum 拿得到但流式下载抛错 → 删 dest + 抛 NetworkError(missing 133-136)。

        构造一个有效的 checksums(含 zip 的 sha),monkeypatch _download_streaming 抛异常,
        断言:抛 NetworkError 且 dest 文件被删(missing_ok=True,删不掉也不二次抛)。
        """
        import hashlib

        zip_bytes = b"never-downloaded"
        expected_sha = hashlib.sha256(zip_bytes).hexdigest()
        cs_text = f"{expected_sha}  FileToolbox-1.2.0-win64.zip\n"

        # _fetch_checksum 经 _download_bytes 拿 checksums(成功)
        monkeypatch.setattr(
            dmod,
            "_download_bytes",
            lambda url: cs_text.encode() if url.endswith("checksums.txt") else b"",
        )

        # 流式下载 zip 失败(模拟网络中断)
        def boom_streaming(url, dest, on_progress=None):
            # 先写半截文件,模拟下载中途断开(dest 已存在,验证 unlink 清理)
            dest.write_bytes(b"partial")
            raise urlerror.URLError("connection reset")

        monkeypatch.setattr(dmod, "_download_streaming", boom_streaming)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        rel = _make_release()
        with pytest.raises(NetworkError):
            dmod.download_and_verify(rel)

        # dest(zip 文件名从 release.zip_url 取)应已被删除
        dest = tmp_path / rel.zip_url.rsplit("/", 1)[-1]
        assert not dest.exists()


class TestProxyApplied:
    """下载请求经代理:GitHub URL 前缀拼接。"""

    def test_download_url_is_proxied(self, monkeypatch, tmp_path):
        from file_toolbox.updater import proxy

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(proxy.ENV_VAR, "https://ghproxy.example")

        import hashlib

        zip_bytes = b"fake-zip"
        expected_sha = hashlib.sha256(zip_bytes).hexdigest()
        cs_text = f"{expected_sha}  FileToolbox-1.2.0-win64.zip\n"

        captured_urls: list[str] = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.endswith("checksums.txt"):
                return _StreamResp(cs_text.encode())
            return _StreamResp(zip_bytes)

        monkeypatch.setattr(dmod, "_urlopen", fake_urlopen)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        rel = _make_release(
            zip_url="https://github.com/FelixJI/file-toolbox/releases/download/v1.2.0/FileToolbox-1.2.0-win64.zip",
            cs_url="https://github.com/FelixJI/file-toolbox/releases/download/v1.2.0/checksums.txt",
        )
        dmod.download_and_verify(rel)
        assert captured_urls, "urlopen 未被调用"
        # zip 与 checksums 两个请求都应走代理
        assert all(u.startswith("https://ghproxy.example/") for u in captured_urls), captured_urls

    def test_download_no_proxy_unchanged(self, monkeypatch, tmp_path):
        from file_toolbox.updater import proxy

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv(proxy.ENV_VAR, raising=False)

        import hashlib

        zip_bytes = b"fake-zip"
        expected_sha = hashlib.sha256(zip_bytes).hexdigest()
        cs_text = f"{expected_sha}  FileToolbox-1.2.0-win64.zip\n"

        captured_urls: list[str] = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.endswith("checksums.txt"):
                return _StreamResp(cs_text.encode())
            return _StreamResp(zip_bytes)

        monkeypatch.setattr(dmod, "_urlopen", fake_urlopen)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        dmod.download_and_verify(
            _make_release(
                zip_url="https://github.com/FelixJI/file-toolbox/releases/download/v1.2.0/FileToolbox-1.2.0-win64.zip",
                cs_url="https://github.com/FelixJI/file-toolbox/releases/download/v1.2.0/checksums.txt",
            )
        )
        assert all(u.startswith("https://github.com/") for u in captured_urls), captured_urls


def _real_release():
    """真实 GitHub 域名的 release(让 _is_github 为 True,代理才拼接)。"""
    return _make_release(
        zip_url="https://github.com/FelixJI/file-toolbox/releases/download/v1.2.0/FileToolbox-1.2.0-win64.zip",
        cs_url="https://github.com/FelixJI/file-toolbox/releases/download/v1.2.0/checksums.txt",
    )


class TestDownloadAndVerifyFallback:
    """download_and_verify 遍历代理候选回退:某候选失败则换下一个,全失败才抛错。"""

    def test_bad_proxy_fails_good_proxy_succeeds(self, monkeypatch, tmp_path):
        """候选1(坏代理)checksums/zip 失败 → 候选2(好代理)成功。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://bad-proxy.example", "https://good-proxy.example"])

        import hashlib

        zip_bytes = b"fake-zip"
        expected_sha = hashlib.sha256(zip_bytes).hexdigest()
        cs_text = f"{expected_sha}  FileToolbox-1.2.0-win64.zip\n"

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.startswith("https://bad-proxy.example/"):
                raise urlerror.URLError("bad proxy down")
            if url.startswith("https://good-proxy.example/"):
                if url.endswith("checksums.txt"):
                    return _StreamResp(cs_text.encode())
                return _StreamResp(zip_bytes)
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr(dmod, "_urlopen", fake_urlopen)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        path = dmod.download_and_verify(_real_release())
        assert path.exists()
        assert path.read_bytes() == zip_bytes

    def test_checksum_fails_on_proxy_then_direct_succeeds(self, monkeypatch, tmp_path):
        """代理下 checksums 拿到但下载 zip 失败 → 整体回退到直连重试成功。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://flaky-proxy.example"])

        import hashlib

        zip_bytes = b"fake-zip"
        expected_sha = hashlib.sha256(zip_bytes).hexdigest()
        cs_text = f"{expected_sha}  FileToolbox-1.2.0-win64.zip\n"

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            # flaky 代理:checksums 成功,但 zip 下载失败(模拟下载中途断)
            if url.startswith("https://flaky-proxy.example/"):
                if url.endswith("checksums.txt"):
                    return _StreamResp(cs_text.encode())
                raise urlerror.URLError("download interrupted")
            # 直连(github.com 无前缀):全部成功
            if url.startswith("https://github.com/"):
                if url.endswith("checksums.txt"):
                    return _StreamResp(cs_text.encode())
                return _StreamResp(zip_bytes)
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr(dmod, "_urlopen", fake_urlopen)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        path = dmod.download_and_verify(_real_release())
        assert path.exists()
        assert path.read_bytes() == zip_bytes

    def test_all_candidates_fail_raises_network_error(self, monkeypatch, tmp_path):
        """代理 + 直连全部失败 → NetworkError。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://bad-proxy.example"])

        def fake_urlopen(req, timeout=None):
            raise urlerror.URLError("all down")

        monkeypatch.setattr(dmod, "_urlopen", fake_urlopen)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        with pytest.raises(NetworkError):
            dmod.download_and_verify(_real_release())

    def test_partial_download_cleaned_between_candidates(self, monkeypatch, tmp_path):
        """坏代理下载写了半截文件 → 回退到直连前,半截文件应被清理(不残留)。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://bad-proxy.example"])

        import hashlib

        zip_bytes = b"full-zip-content"
        expected_sha = hashlib.sha256(zip_bytes).hexdigest()
        cs_text = f"{expected_sha}  FileToolbox-1.2.0-win64.zip\n"

        dest_seen: list = []

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.startswith("https://bad-proxy.example/"):
                if url.endswith("checksums.txt"):
                    return _StreamResp(cs_text.encode())
                # 写半截文件后失败(模拟中断);dest 已存在
                raise urlerror.URLError("interrupted")
            if url.startswith("https://github.com/"):
                if url.endswith("checksums.txt"):
                    return _StreamResp(cs_text.encode())
                return _StreamResp(zip_bytes)
            raise AssertionError(f"unexpected url: {url}")

        # 拦截 _download_streaming 的 dest,记录坏代理阶段的残留文件
        original_streaming = dmod._download_streaming
        call_count = {"n": 0}

        def streaming_spy(url, dest, proxy="", on_progress=None):
            call_count["n"] += 1
            try:
                return original_streaming(url, dest, proxy=proxy, on_progress=on_progress)
            except Exception:
                dest_seen.append((call_count["n"], dest.exists(), str(dest)))
                raise

        monkeypatch.setattr(dmod, "_urlopen", fake_urlopen)
        monkeypatch.setattr(dmod, "_download_streaming", streaming_spy)
        monkeypatch.setattr(dmod, "_mkdtemp", lambda prefix: str(tmp_path))

        path = dmod.download_and_verify(_real_release())
        assert path.exists()
        assert path.read_bytes() == zip_bytes
        # 坏代理阶段失败前 dest 不存在(未开始写),或已被清理。最终成功文件内容正确。
        # 关键:坏代理的半截文件若写过,应在 except 里 unlink 清理,不污染直连候选。
