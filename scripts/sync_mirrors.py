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

import re
from urllib.parse import urlparse

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
