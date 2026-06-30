"""版本来源层:从 GitHub 获取最新正式版 Release。

本模块只负责"拿版本信息 + 比对版本号",不下载、不替换。
零第三方依赖:版本号解析与比对用轻量正则 + 数字比较,
不引入 packaging(便携 exe 运行时不带 dev extra)。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib import request as urlrequest

# owner/repo 硬编码常量(与 git remote 一致,不引入配置真相源)
GITHUB_REPO = ("FelixJI", "file-toolbox")

# 预发布后缀(PEP 440 prerelease 段)
_PRERELEASE_RE = re.compile(r"(a|b|rc|dev|alpha|beta)\d*$", re.IGNORECASE)

# 检查超时(秒):双源并发取版本信息,给 10s 足够
_FETCH_TIMEOUT = 10


@dataclass(frozen=True)
class RemoteRelease:
    """远程最新 Release 信息。"""

    version: str          # PEP 440 正式版号,如 "1.2.0"(无 v 前缀)
    zip_url: str          # 便携 zip 下载地址
    checksum_url: str     # checksums.txt 地址
    source: str           # "github",用于日志/排错


def strip_v_prefix(version: str) -> str:
    """去掉版本号前的 v 前缀(若有)。"""
    return version[1:] if version.startswith("v") else version


def _is_prerelease(version: str) -> bool:
    """是否符合预发布后缀(a/b/rc/dev/alpha/beta)。"""
    return bool(_PRERELEASE_RE.search(version))


def _normalize_segments(version: str) -> list[int]:
    """把版本号切成数字段列表,忽略 +local 后缀。

    "1.2.3" → [1, 2, 3]
    "1.2"   → [1, 2]
    "1.0.0+unknown" → [1, 0, 0]  (+ 后整段丢弃)

    遇到第一个非数字段(如 prerelease 段 "3a1")即停止,后续段不解析。
    本函数仅供已过滤 prerelease 的正式版比对使用(见 is_newer 契约)。
    """
    base = version.split("+", 1)[0]  # 去掉 +local
    segs: list[int] = []
    for part in base.split("."):
        try:
            segs.append(int(part))
        except ValueError:
            # 非数字段(如 prerelease 段)→ 停止解析后续段
            break
    return segs


def is_newer(remote: str, local: str) -> bool:
    """remote 版本号是否比 local 新(逐段数字比较)。

    段数不同时短的补 0(1.2 视作 1.2.0)。

    契约:仅用于正式版比对(调用方应先用 _is_prerelease 过滤)。
    传入 prerelease 版本号(如 "1.2.3a1")时,非数字段会被截断,
    可能得出错误结论 —— 但自更新流程已在 fetch_latest 阶段过滤掉 prerelease。
    """
    r = _normalize_segments(remote)
    loc = _normalize_segments(local)
    n = max(len(r), len(loc))
    r += [0] * (n - len(r))
    loc += [0] * (n - len(loc))
    return r > loc


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


def _fetch(platform: str) -> RemoteRelease | None:
    """从单个平台拉取并解析最新 Release。失败返回 None(不抛)。"""
    url = _build_release_url(platform)
    req = urlrequest.Request(url, headers={"Accept": "application/json"})
    try:
        with _urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            payload = resp.read()
    except Exception:
        # 网络/超时/HTTP 错误统一视为该源无结果
        return None
    return _parse_release(payload, platform)


def fetch_latest() -> RemoteRelease | None:
    """从 GitHub 取最新正式版 Release。

    仅返回正式版(过滤 prerelease)。源失败/为 prerelease/无 zip asset → 返回 None。
    """
    rel = _fetch("github")
    if rel and not _is_prerelease(rel.version):
        return rel
    return None
