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


# ---------------------------------------------------------------------------
# GitHub API 交互层(标准库 urllib,避免引入 requests 依赖)
# ---------------------------------------------------------------------------

import json  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from typing import Any, cast  # noqa: E402

_API_BASE = "https://api.github.com"


def _api(
    method: str, url: str, token: str, *, expect: int = 200
) -> dict[str, Any] | list[Any] | None:
    """发 GitHub API 请求,返回解析后的 JSON。

    404 → 返回 None(资源不存在,调用方按幂等处理)。
    其余非 expect 状态码 → 抛 RuntimeError(含响应体便于排查)。
    """
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} → {e.code}: {detail}") from e


def list_releases(repo: str, token: str) -> list[Release]:
    """GET /repos/{repo}/releases,分页拉取全部 Release。

    版本号无法解析的 release(tag 非合法 PEP 440)跳过并告警,不计入结果。
    分页:per_page=100,page 自增直到返回空数组。
    """
    releases: list[Release] = []
    page = 1
    while True:
        url = f"{_API_BASE}/repos/{repo}/releases?per_page=100&page={page}"
        data = _api("GET", url, token)
        if not data:
            break
        # GET /releases 契约返回 list[dict];_api 返回联合类型,这里窄化为 list
        items: list[dict[str, Any]] = cast(list[dict[str, Any]], data)
        for item in items:
            tag = item.get("tag_name", "")
            version = tag.lstrip("v")
            if not _is_valid_version(version):
                # 防御性:跳过手工建的、命名不规范的 release,避免误删
                print(f"::warning::跳过无法解析版本号的 release: tag={tag!r}", flush=True)
                continue
            releases.append(
                Release(
                    id=item["id"],
                    tag=tag,
                    version=version,
                    is_prerelease=bool(item.get("prerelease", False)),
                )
            )
        if len(items) < 100:
            break  # 最后一页
        page += 1
    return releases


def delete_release(repo: str, token: str, release_id: int, *, tag: str) -> None:
    """DELETE /repos/{repo}/releases/{release_id}。

    仅删 Release + 其附带的资产(zip/checksums),不删 git tag(tag 删除是另一端点,不调用)。
    404 → 视为已删除(幂等);其余非 204 → _api 内部抛 RuntimeError。
    tag 仅用于错误信息上下文,不参与请求构造。
    """
    url = f"{_API_BASE}/repos/{repo}/releases/{release_id}"
    try:
        _api("DELETE", url, token, expect=204)
    except RuntimeError as e:
        # 附上 tag 上下文,让日志更可读
        raise RuntimeError(f"{e} (tag={tag})") from e
