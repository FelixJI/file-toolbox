"""GitHub 代理 URL 变换器(前缀拼接)。

支持主流 GitHub 代理(ghproxy/gh-proxy 等)的通用形式:
  <代理基址> + "/" + <原始完整 URL>
  如 https://ghproxy.com/https://github.com/a/b.zip

代理来源优先级:环境变量 FILE_TOOLBOX_GH_PROXY > settings["gh_proxies"] 列表
> settings["gh_proxy"](旧单值,向后兼容)> 空(无代理)。
非 GitHub 域名 / 代理为空 → URL 原样返回。

候选列表与回退:get_fetch_candidates() 返回去尝试的代理序列(环境变量代理 →
用户启用的代理列表 → 末尾 "" 直连兜底),检查更新/下载按序逐个尝试,全部失败
才整体失败(程序内部自动回退,无需用户干预)。

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

# 预置的公共 GitHub 加速代理候选(关于页"默认"项来源)。
# 这些代理可用性不稳定,故仅作候选;运行时配合 get_fetch_candidates() 末尾的
# 直连兜底自动回退,单个代理不可用不影响功能。
#
# 实测行为(2026-08):多数公共镜像只代理 github.com 下载资源,不代理 api.github.com。
# 故这些镜像主要在"下载 zip/checksums"阶段生效;检查更新(API 端点)多由末尾直连兜底。
# ghfast.top / ghproxy.net 实测对下载资源有效但对 API 返回 403 —— 属预期,
# get_fetch_candidates() 会自动跳过失败候选继续尝试下一个 + 直连。
DEFAULT_PROXIES: tuple[str, ...] = (
    "https://ghproxy.com",
    "https://gh-proxy.com",
    "https://ghfast.top",
    "https://ghproxy.net",
)


def _normalize(raw: str) -> str:
    """归一化代理基址:无 scheme 补 https://;去尾斜杠。空串原样返回。"""
    s = raw.strip()
    if not s:
        return ""
    if "://" not in s:
        s = "https://" + s
    return s.rstrip("/")


def _dedup_preserve_order(items: list[str]) -> list[str]:
    """去重并保持首次出现顺序。"""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def get_proxy() -> str:
    """当前生效的单个代理基址(首个启用代理)。

    优先级:环境变量 > settings["gh_proxies"][0] > settings["gh_proxy"](旧)> ""。
    供向后兼容的 apply_proxy(url) 默认行为使用。
    """
    candidates = get_fetch_candidates()
    return candidates[0] if candidates else ""


def get_enabled_proxies() -> list[str]:
    """用户启用的代理列表(settings["gh_proxies"]),归一化 + 去重 + 保序。

    向后兼容:若 gh_proxies 不存在或损坏(非 list)且旧 gh_proxy 非空,
    迁移旧单值为单元素列表。
    """
    raw_list = settings.get("gh_proxies", None)
    items: list[str] = []
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, str):
                items.append(_normalize(item))
    else:
        # 未设置或损坏(非 list)→ 尝试迁移旧单值 gh_proxy
        legacy = settings.get("gh_proxy", "")
        if legacy:
            items.append(_normalize(legacy))
    return _dedup_preserve_order([i for i in items if i])


def get_fetch_candidates() -> list[str]:
    """按序尝试的代理候选序列(程序内部回退用)。

    顺序:环境变量代理 → 用户启用的代理列表 → ""(直连,总在末尾兜底)。
    过滤空串后去重保序,末尾追加唯一一个 "" 兜底。
    至少返回 [""](仅直连),保证总有兜底路径。
    """
    env_raw = os.environ.get(ENV_VAR, "")
    env_proxy = _normalize(env_raw) if env_raw else ""
    # 合并 env + enabled,过滤空串后去重保序
    items = _dedup_preserve_order([p for p in [env_proxy] + get_enabled_proxies() if p])
    # 末尾总追加直连("")兜底(此时 items 内无空串,确保直连唯一在末尾)
    items.append("")
    return items


def _is_github(url: str) -> bool:
    """URL 的 host 是否为 GitHub 域名。"""
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    return host in _GITHUB_HOSTS if host else False


def apply_proxy(url: str, proxy: str | None = None) -> str:
    """对 GitHub 域名 URL 前缀拼接代理基址。

    proxy=None → 用 get_proxy()(向后兼容默认行为);
    proxy 显式给定(含 "")→ 用该值:"" 表示显式直连(不拼接)。
    代理为空 / 非 GitHub 域名 → URL 原样返回。
    """
    base = get_proxy() if proxy is None else proxy
    if not base or not _is_github(url):
        return url
    return f"{base}/{url}"
