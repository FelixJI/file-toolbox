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
