"""下载与校验层:流式下载便携 zip + 强制 SHA256 校验。

不判断要不要更新(那是 versions 层的事),不替换(那是 replacer 层)。
用标准库 urllib,不引入 requests/httpx,保持便携包零额外依赖。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

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
