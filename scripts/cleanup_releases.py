"""历史 GitHub Release 清理。

仅删 Release 记录及其附带产物(zip/checksums),保留全部 git tag。
运行方式:uv run --extra dev python scripts/cleanup_releases.py --keep 5 --repo <owner/repo> --token <token>
"""

from __future__ import annotations

from dataclasses import dataclass

from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class Release:
    """GitHub Release 的最小表示(只存 cleanup 关心的字段)。"""

    id: int
    tag: str  # 如 "v0.2.0"
    version: str  # 如 "0.2.0"(去 v 前缀,用于 PEP 440 排序)
    is_prerelease: bool


def select_releases_to_delete(releases: list[Release], keep: int) -> list[Release]:
    """按 PEP 440 版本号降序排序,返回应删除的(保留前 keep 个之外的)。

    输入保证所有 release.version 可被 packaging.Version 解析(过滤在上游 list_releases 完成)。
    预发布版(如 0.2.0a1)由 packaging.Version 自然排在同号正式版之后,与正式版统一计入 keep 总数。
    """
    if keep < 0:
        raise ValueError(f"keep 不能为负: {keep!r}")
    # 按 version(PEP 440)降序;Version 不可解析者不应出现(上游已过滤),防御性跳过
    valid = [r for r in releases if _is_valid_version(r.version)]
    valid.sort(key=lambda r: Version(r.version), reverse=True)
    return valid[keep:]


def _is_valid_version(version: str) -> bool:
    """版本号是否符合 PEP 440(防御性:上游已过滤,此为兜底)。"""
    try:
        Version(version)
        return True
    except InvalidVersion:
        return False
