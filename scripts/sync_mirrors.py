"""镜像同步与 Release 清理(CI 发版后同步到 gitee/cnb + 清理旧 Release)。

用法(CI 内,由 release.yml 的 sync job 调用):
    uv run --extra dev python scripts/sync_mirrors.py sync \\
        --version 1.2.3 --notes-file release_notes.md --artifacts-dir artifacts

环境变量(从 GitHub Secrets 注入,缺失则跳过对应平台):
    GITEE_TOKEN  — Gitee 访问令牌(push + Release API)
    CNB_TOKEN    — CNB 访问令牌(仅 push;CNB 用户名固定为 cnb)
    GH_TOKEN     — GitHub Token(用 Actions 内置 GITHUB_TOKEN,清理 Release)
    GITHUB_REPOSITORY — "owner/repo"(CI 内置,缺省时从 git remote 解析)
"""

from __future__ import annotations

import json as _json
import mimetypes
import re
import uuid
from urllib import error as _urlerror
from urllib import request as _urlrequest
from urllib.parse import urlencode, urlparse

# 匹配 https://host/owner/repo(.git)(/),取最后两段路径。
_OWNER_REPO_RE = re.compile(r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")


def parse_owner_repo(remote_url: str) -> tuple[str, str]:
    """从远程 URL 解析 (owner, repo)。

    支持 gitee / cnb / github 的 https URL,可带或不带 .git 后缀。
    解析失败抛 ValueError。
    """
    parsed = urlparse(remote_url)
    if not parsed.netloc or not parsed.path:
        raise ValueError(f"无法解析 owner/repo: {remote_url!r}")
    m = _OWNER_REPO_RE.match(parsed.path)
    if not m:
        raise ValueError(f"无法解析 owner/repo: {remote_url!r}")
    return (m.group("owner"), m.group("repo"))


def version_to_tag(version: str) -> str:
    """版本号 → tag(加 v 前缀)。"""
    return f"v{version}"


def build_push_url(remote_url: str, token: str, platform: str) -> str:
    """构造带认证的 HTTPS 推送 URL。

    platform:
      - 'gitee': https://{token}@gitee.com/{owner}/{repo}.git
      - 'cnb':   https://cnb:{token}@cnb.cool/{owner}/{repo}(用户名固定 cnb)
    """
    owner, repo = parse_owner_repo(remote_url)
    if platform == "gitee":
        return f"https://{token}@gitee.com/{owner}/{repo}.git"
    if platform == "cnb":
        return f"https://cnb:{token}@cnb.cool/{owner}/{repo}"
    raise ValueError(f"不支持的 platform: {platform!r}")


def releases_to_delete(releases: list[dict], keep: int = 5) -> list[int]:
    """计算需要删除的 release id(保留最近 keep 个,删其余)。

    按 created_at 升序(最旧在前)排,删掉前 (len - keep) 个;返回待删 id 列表。
    不区分正式版/预发布版(均按时间计入)。空输入或不足 keep 个 → 返回 []。
    """
    if len(releases) <= keep:
        return []
    # 升序排(最旧在前),删前 (len - keep) 个
    ordered = sorted(releases, key=lambda r: r["created_at"])
    return [r["id"] for r in ordered[: len(releases) - keep]]


# 模块级别名:便于测试 monkeypatch 桩掉(同 release.py 的 _run 风格)。
_urlopen = _urlrequest.urlopen


def _build_multipart(files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    """构造 multipart/form-data body。

    files: {field_name: (filename, content_bytes)}
    返回 (body_bytes, content_type_header)。
    """
    boundary = "----sync" + uuid.uuid4().hex
    lines: list[bytes] = []
    for field_name, (filename, content) in files.items():
        lines.append(f"--{boundary}".encode())
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        lines.append(
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"'.encode()
        )
        lines.append(f"Content-Type: {mime}".encode())
        lines.append(b"")
        lines.append(content)
    lines.append(f"--{boundary}--".encode())
    lines.append(b"")
    body = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def _http(
    method: str,
    url: str,
    token: str | None = None,
    data: dict | None = None,
    files: dict | None = None,
    timeout: int = 60,
) -> tuple[int, object]:
    """urllib 封装。返回 (status, parsed_json_or_text)。

    - token: 非 None 时加 `Authorization: token <token>` header(gitee/Gitee 兼容)。
    - data: form data(普通表单字段),URL-encoded。
    - files: multipart 上传 {field: (filename, bytes)},与 data 互斥。
    """
    headers: dict[str, str] = {}
    body: bytes | None = None
    if token:
        headers["Authorization"] = f"token {token}"
    if files:
        body, ct = _build_multipart(files)
        headers["Content-Type"] = ct
    elif data:
        body = urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = _urlrequest.Request(url, data=body, headers=headers, method=method)
    try:
        with _urlopen(req, timeout=timeout) as resp:
            status = resp.status if hasattr(resp, "status") else resp.getcode()
            raw = resp.read()
    except _urlerror.HTTPError as e:
        raw = e.read()
        raise RuntimeError(f"HTTP {e.code} {url}: {raw[:500]!r}") from e

    text = raw.decode("utf-8", errors="replace") if raw else ""
    try:
        parsed = _json.loads(text) if text else None
    except ValueError:
        parsed = text
    return status, parsed


def _releases_endpoint(platform: str, owner: str, repo: str) -> str:
    if platform == "gitee":
        return f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases"
    if platform == "github":
        return f"https://api.github.com/repos/{owner}/{repo}/releases"
    raise ValueError(f"不支持的 platform: {platform!r}")


def list_releases(token: str, platform: str, owner: str, repo: str) -> list[dict]:
    """列出某平台全部 Release,归一化为 [{id, created_at}, ...]。"""
    _, data = _http("GET", _releases_endpoint(platform, owner, repo), token=token)
    if not isinstance(data, list):
        return []
    return [{"id": r["id"], "created_at": r["created_at"]} for r in data]


def delete_release(token: str, platform: str, owner: str, repo: str, release_id: int) -> None:
    """删除单个 Release。失败抛 RuntimeError(由调用方决定是否继续)。"""
    url = f"{_releases_endpoint(platform, owner, repo)}/{release_id}"
    _http("DELETE", url, token=token)
