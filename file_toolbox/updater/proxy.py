"""GitHub 代理 URL 变换器(前缀拼接)。

支持主流 GitHub 代理(ghproxy/gh-proxy 等)的通用形式:
  <代理基址> + "/" + <原始完整 URL>
  如 https://ghproxy.com/https://github.com/a/b.zip

代理来源优先级:环境变量 FILE_TOOLBOX_GH_PROXY > settings["gh_proxy"] > 空(无代理)。
非 GitHub 域名 / 代理为空 → URL 原样返回。

兼容性:本变换为"前缀拼接"。GitHub release 下载会 302 重定向到 objects.githubusercontent.com,
urllib 默认重定向处理器原样跟随 Location,不对重定向目标再次拼接代理。故代理需为
"服务端跟随重定向并流式回传"型(如 ghproxy/gh-proxy 等主流前缀代理);对"把 302 原样
返回给客户端"型代理,资源下载会绕过代理直连对象存储。
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from file_toolbox.common import settings

ENV_VAR = "FILE_TOOLBOX_GH_PROXY"

# 走代理的 GitHub 域名(含下载重定向/源码/资源域名)
_GITHUB_HOSTS = frozenset(
    {
        "github.com",
        "api.github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
        "codeload.github.com",
    }
)


def _normalize(raw: str) -> str:
    """归一化代理基址:无 scheme 补 https://;去尾斜杠。空串原样返回。"""
    s = raw.strip()
    if not s:
        return ""
    if "://" not in s:
        s = "https://" + s
    return s.rstrip("/")


def get_proxy() -> str:
    """代理基址。优先级:环境变量 > settings["gh_proxy"] > ""。"""
    raw = os.environ.get(ENV_VAR, "")
    if not raw:
        raw = settings.get("gh_proxy", "")
    return _normalize(raw) if raw else ""


def _is_github(url: str) -> bool:
    """URL 的 host 是否为 GitHub 域名。"""
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    return host in _GITHUB_HOSTS if host else False


def apply_proxy(url: str) -> str:
    """对 GitHub 域名 URL 前缀拼接代理基址。

    代理为空 / 非 GitHub 域名 → 原样返回。
    """
    proxy = get_proxy()
    if not proxy or not _is_github(url):
        return url
    return f"{proxy}/{url}"
