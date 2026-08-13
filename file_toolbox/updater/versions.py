"""版本来源层:从 GitHub 获取最新正式版 Release。

本模块只负责"拿版本信息 + 比对版本号",不下载、不替换。
版本号遵循 PEP 440，由 packaging 统一解析和比较。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib import request as urlrequest

from packaging.version import InvalidVersion, Version

from file_toolbox.updater.proxy import apply_proxy, get_fetch_candidates

_logger = logging.getLogger(__name__)

# owner/repo 硬编码常量(与 git remote 一致,不引入配置真相源)
GITHUB_REPO = ("FelixJI", "file-toolbox")

# 检查超时(秒):双源并发取版本信息,给 10s 足够
_FETCH_TIMEOUT = 10


@dataclass(frozen=True)
class RemoteRelease:
    """远程最新 Release 信息。"""

    version: str  # PEP 440 正式版号,如 "1.2.0"(无 v 前缀)
    zip_url: str  # 便携 zip 下载地址
    checksum_url: str  # checksums.txt 地址
    source: str  # "github",用于日志/排错


def strip_v_prefix(version: str) -> str:
    """去掉版本号前的 v 前缀(若有)。"""
    return version[1:] if version.startswith("v") else version


def _is_prerelease(version: str) -> bool:
    """是否为预发布版本；非法版本按不可信候选处理。"""
    try:
        return Version(version).is_prerelease
    except InvalidVersion:
        return True


def is_newer(remote: str, local: str) -> bool:
    """remote 版本号是否比 local 新；非法版本安全地视为不可更新。"""
    try:
        return Version(remote) > Version(local)
    except InvalidVersion:
        return False


# ---------------------------------------------------------------------------
# HTTP 取数(模块级别名,便于测试 monkeypatch)
# ---------------------------------------------------------------------------
_urlopen = urlrequest.urlopen


def _build_release_url(platform: str) -> str:
    """构造某平台 releases/latest API URL。"""
    if platform == "github":
        owner, repo = GITHUB_REPO
        return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    raise ValueError(f"不支持的 platform: {platform!r}")


def _parse_release(payload: bytes, platform: str) -> RemoteRelease | None:
    """从 API JSON 解析出 RemoteRelease。无效(无 zip asset)→ None。"""
    try:
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    tag = data.get("tag_name")
    if not tag:
        return None
    version = strip_v_prefix(tag)

    zip_url = ""
    checksum_url = ""
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        if name.endswith("-win64.zip"):
            zip_url = url
        elif name == "checksums.txt":
            checksum_url = url

    if not zip_url or not checksum_url:
        return None
    return RemoteRelease(
        version=version, zip_url=zip_url, checksum_url=checksum_url, source=platform
    )


def _fetch(platform: str, proxy: str = "") -> RemoteRelease | None:
    """从单个平台拉取并解析最新 Release。失败返回 None(不抛)。

    proxy: 显式代理基址("" = 直连不拼接)。
    """
    url = apply_proxy(_build_release_url(platform), proxy=proxy)
    req = urlrequest.Request(url, headers={"Accept": "application/json"})
    try:
        with _urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            payload = resp.read()
    except Exception as e:
        # 网络/超时/HTTP 错误统一视为该源无结果;记录便于排错(此前静默吞掉)
        _logger.debug("GitHub 取版本失败 proxy=%s: %s", proxy or "(直连)", e)
        return None
    return _parse_release(payload, platform)


def fetch_latest() -> RemoteRelease | None:
    """从 GitHub 取最新正式版 Release。

    按 get_fetch_candidates() 的代理候选顺序逐个尝试(含末尾直连兜底),
    首个成功的候选即返回。仅返回正式版(过滤 prerelease)。
    全部候选失败/为 prerelease/无 zip asset → 返回 None。
    """
    for proxy in get_fetch_candidates():
        rel = _fetch("github", proxy=proxy)
        if rel and not _is_prerelease(rel.version):
            _logger.debug("取得最新版本 %s via %s", rel.version, proxy or "(直连)")
            return rel
    _logger.debug("所有代理候选与直连均未取得有效版本")
    return None
