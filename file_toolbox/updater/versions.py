"""版本来源层:从 Gitee+GitHub 并发获取最新正式版 Release。

本模块只负责"拿版本信息 + 比对版本号",不下载、不替换。
零第三方依赖:版本号解析与比对用轻量正则 + 数字比较,
不引入 packaging(便携 exe 运行时不带 dev extra)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# owner/repo 硬编码常量(与 git remote 一致,不引入配置真相源)
GITHUB_REPO = ("FelixJI", "file-toolbox")
GITEE_REPO = ("felixjii", "file-toolbox")

# 预发布后缀(PEP 440 prerelease 段)
_PRERELEASE_RE = re.compile(r"(a|b|rc|dev|alpha|beta)\d*$", re.IGNORECASE)


@dataclass(frozen=True)
class RemoteRelease:
    """远程最新 Release 信息。"""

    version: str          # PEP 440 正式版号,如 "1.2.0"(无 v 前缀)
    zip_url: str          # 便携 zip 下载地址
    checksum_url: str     # checksums.txt 地址
    source: str           # "gitee" | "github",用于日志/排错


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
    """
    base = version.split("+", 1)[0]  # 去掉 +local
    segs: list[int] = []
    for part in base.split("."):
        try:
            segs.append(int(part))
        except ValueError:
            # 非数字段(如 prerelease 段)忽略
            break
    return segs


def is_newer(remote: str, local: str) -> bool:
    """remote 版本号是否比 local 新(逐段数字比较)。

    段数不同时短的补 0(1.2 视作 1.2.0)。
    """
    r = _normalize_segments(remote)
    l = _normalize_segments(local)
    n = max(len(r), len(l))
    r += [0] * (n - len(r))
    l += [0] * (n - len(l))
    return r > l
