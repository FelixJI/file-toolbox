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
        assert parse_checksums(content, "FileToolbox-1.2.0-win64.zip") == (
            "abcd1234" + "0" * 56
        )


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


def _make_release(zip_url="http://github/FileToolbox-1.2.0-win64.zip", cs_url="http://github/checksums.txt"):
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
