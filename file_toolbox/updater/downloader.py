"""下载与校验层:流式下载便携 zip + 强制 SHA256 校验。

不判断要不要更新(那是 versions 层的事),不替换(那是 replacer 层)。
用标准库 urllib,不引入 requests/httpx,保持便携包零额外依赖。
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import urllib.request
from pathlib import Path

from file_toolbox.updater.errors import ChecksumMismatchError, NetworkError
from file_toolbox.updater.versions import RemoteRelease

# 下载超时(秒):便携包几十 MB,给足
_DOWNLOAD_TIMEOUT = 60
# 流式读块大小
_CHUNK = 65536


def parse_checksums(content: str, zip_name: str) -> str | None:
    """从 checksums.txt 内容解析指定 zip 的 SHA256。

    checksums.txt 行格式: "<sha256>  <filename>"(两个空格分隔)。
    匹配不到返回 None。
    """
    for line in content.splitlines():
        # sha256 是 64 位十六进制
        m = re.match(r"^\s*([0-9a-fA-F]{64})\s+(\S+)\s*$", line)
        if m and m.group(2) == zip_name:
            return m.group(1).lower()
    return None


def sha256_file(path: Path) -> str:
    """计算文件的 SHA256(分块读,避免大文件占内存)。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# 模块级别名,便于测试 monkeypatch
_urlopen = urllib.request.urlopen
_mkdtemp = tempfile.mkdtemp


def _download_bytes(url: str) -> bytes:
    """从单 URL 下载全部字节。失败抛异常(由调用方处理)。"""
    req = urllib.request.Request(url)
    with _urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
        return resp.read()


def _download_streaming(url: str, dest: Path, on_progress=None) -> int:
    """流式下载到 dest。返回 content_length(total=-1 表未知)。

    on_progress(downloaded, total): 每 chunk 回调一次。
    """
    req = urllib.request.Request(url)
    with _urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
        cl = resp.headers.get("Content-Length")
        total = int(cl) if cl else -1
        downloaded = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if on_progress:
                    on_progress(downloaded, total)
    return total


def _fetch_checksum(release: RemoteRelease) -> tuple[str, str] | None:
    """获取 checksums 并解析出 expected sha + zip 文件名。

    用 release 自身的 checksum_url 拉取 checksums.txt 并解析。
    解析失败返回 None。

    返回 (expected_sha_lowercased, zip_name)。
    """
    zip_name = release.zip_url.rsplit("/", 1)[-1]

    try:
        data = _download_bytes(release.checksum_url)
        text = data.decode("utf-8", errors="replace")
        sha = parse_checksums(text, zip_name)
        if sha:
            return (sha, zip_name)
    except Exception:
        pass
    return None


def download_and_verify(
    release: RemoteRelease,
    on_progress=None,
) -> Path:
    """下载便携 zip + 强制 SHA256 校验。返回已校验的本地 zip 路径。

    流程:
      1. 拉取 checksums → 解析 expected sha
      2. 流式下载 zip 到临时目录,边写边校验
      3. 实际 sha == expected?匹配返回路径;不匹配删 zip 抛 ChecksumMismatchError

    checksum 拿不到 → NetworkError。
    """
    got = _fetch_checksum(release)
    if got is None:
        raise NetworkError("无法获取 checksums")
    expected_sha, zip_name = got

    tmp_dir = Path(_mkdtemp(prefix="ftb_update_"))
    dest = tmp_dir / zip_name
    try:
        _download_streaming(release.zip_url, dest, on_progress=on_progress)
    except Exception as e:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise NetworkError(f"下载失败: {e}") from e

    actual_sha = sha256_file(dest)
    if actual_sha != expected_sha:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise ChecksumMismatchError(
            f"SHA256 校验不匹配: expected {expected_sha}, got {actual_sha}"
        )
    return dest
