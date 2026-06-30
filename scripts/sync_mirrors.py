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
import os
import re
import subprocess
import uuid
from pathlib import Path
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
    """列出某平台全部 Release,归一化为 [{id, created_at}, ...]。

    分页拉取(per_page=100),直到某页返回不足 100 个为止。
    Gitee/GitHub 默认每页 20/30,不翻页会漏掉旧 Release 导致清理失效。
    """
    base = _releases_endpoint(platform, owner, repo)
    out: list[dict] = []
    page = 1
    per_page = 100
    while True:
        sep = "&" if "?" in base else "?"
        url = f"{base}{sep}page={page}&per_page={per_page}"
        _, data = _http("GET", url, token=token)
        if not isinstance(data, list) or not data:
            break
        out.extend({"id": r["id"], "created_at": r["created_at"]} for r in data)
        if len(data) < per_page:
            break
        page += 1
    return out


def delete_release(token: str, platform: str, owner: str, repo: str, release_id: int) -> None:
    """删除单个 Release。失败抛 RuntimeError(由调用方决定是否继续)。"""
    url = f"{_releases_endpoint(platform, owner, repo)}/{release_id}"
    _http("DELETE", url, token=token)


def create_gitee_release(
    token: str, owner: str, repo: str, tag: str, name: str, body: str
) -> int | None:
    """在 Gitee 创建 Release。已存在(同 tag)→ 返回 None(幂等跳过)。成功 → 返回 release_id。"""
    # 先查重(幂等):GET 该 tag 的 release;404(不存在)→ RuntimeError,视作可创建。
    check_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases/tags/{tag}"
    try:
        _, existing = _http("GET", check_url, token=token)
    except RuntimeError:
        existing = None
    if existing:
        return None
    _, data = _http(
        "POST",
        _releases_endpoint("gitee", owner, repo),
        token=token,
        data={"tag_name": tag, "name": name, "body": body, "target_commitish": "main"},
    )
    return data["id"] if isinstance(data, dict) else None


def upload_gitee_asset(
    token: str, owner: str, repo: str, release_id: int, file_path: Path
) -> None:
    """上传单个文件到 Gitee Release 附件。"""
    content = file_path.read_bytes()
    url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases/{release_id}/attach_files"
    _http("POST", url, token=token, files={"file": (file_path.name, content)})


def cleanup_old_releases(
    token: str, platform: str, owner: str, repo: str, keep: int = 5
) -> None:
    """列出某平台 Release,删除超出 keep 的旧版(单删失败仅警告)。"""
    rels = list_releases(token, platform, owner, repo)
    to_delete = releases_to_delete(rels, keep=keep)
    if not to_delete:
        return
    print(f"[cleanup] {platform} 待删 {len(to_delete)} 个旧 Release(保留最近 {keep})")
    for rid in to_delete:
        try:
            delete_release(token, platform, owner, repo, rid)
            print(f"  ✓ 删除 {platform} release {rid}")
        except RuntimeError as e:
            print(f"  警告:删除 {platform} release {rid} 失败: {e}")


def push_to_remote(remote_url_with_auth: str, refspecs: list[str]) -> None:
    """git push <url> <refspecs>。失败抛 RuntimeError(stderr 不含明文 url 之外的敏感信息)。"""
    cmd = ["git", "push", remote_url_with_auth, *refspecs]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if res.returncode != 0:
        # 不打印 url(含 token),只报失败
        raise RuntimeError(f"git push 失败(returncode={res.returncode}): {res.stderr.strip()}")


def _git_remote_url(name: str = "origin") -> str:
    """读取某 remote 的 URL。失败返回空串。"""
    res = subprocess.run(
        ["git", "remote", "get-url", name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return res.stdout.strip()


def resolve_github_repo() -> tuple[str, str]:
    """解析 GitHub owner/repo:优先 GITHUB_REPOSITORY 环境变量,否则 git remote。"""
    env = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in env:
        owner, repo = env.split("/", 1)
        return (owner, repo)
    url = _git_remote_url("origin")
    return parse_owner_repo(url)


# ---------------------------------------------------------------------------
# typer CLI
# ---------------------------------------------------------------------------

import typer  # noqa: E402

cli = typer.Typer(add_completion=False, help="镜像同步与 Release 清理")


def _read_notes(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _artifact_files(artifacts_dir: Path) -> list[Path]:
    """收集 artifacts 目录下的 zip + checksums.txt。"""
    if not artifacts_dir.exists():
        return []
    files = sorted(artifacts_dir.glob("*.zip"))
    cs = artifacts_dir / "checksums.txt"
    if cs.exists():
        files.append(cs)
    return files


@cli.command()
def sync(
    version: str = typer.Option(..., "--version", help="版本号(不带 v)"),
    notes_file: Path = typer.Option(..., "--notes-file", help="Release notes 文件"),
    artifacts_dir: Path = typer.Option(..., "--artifacts-dir", help="产物目录(zip+checksums)"),
    keep: int = typer.Option(5, "--keep", help="保留最近 N 个 Release"),
) -> None:
    """同步代码到 gitee/cnb(仅镜像,不建 Release)+ Gitee 建 Release + 清理旧 Release(GitHub+Gitee)。"""
    tag = version_to_tag(version)
    body = _read_notes(notes_file)
    arts = _artifact_files(artifacts_dir)
    refspecs = ["main", f"refs/tags/{tag}"]

    gitee_token = os.environ.get("GITEE_TOKEN", "")
    cnb_token = os.environ.get("CNB_TOKEN", "")
    gh_token = os.environ.get("GH_TOKEN", "")
    gitee_url = _git_remote_url("gitee")
    cnb_url = _git_remote_url("cnb")
    gh_owner, gh_repo = resolve_github_repo()

    # ---- 1. 推送 gitee ----
    if gitee_token and gitee_url:
        try:
            push_to_remote(build_push_url(gitee_url, gitee_token, "gitee"), refspecs)
            typer.secho("✓ 推送 gitee", fg=typer.colors.GREEN)
        except RuntimeError as e:
            typer.secho(f"✗ 推送 gitee 失败: {e}", fg=typer.colors.RED, err=True)
    elif not gitee_token:
        typer.secho("⚠ GITEE_TOKEN 未配置,跳过 gitee 同步", fg=typer.colors.YELLOW)
    elif not gitee_url:
        # token 在但没 gitee remote → CI checkout 缺 remote 时会落到这里(本次 bug 根因)
        typer.secho(
            "⚠ GITEE_TOKEN 已配置但未找到 gitee remote(git remote add gitee <url>?)"
            ",跳过 gitee 同步",
            fg=typer.colors.YELLOW,
        )

    # ---- 2. 推送 cnb ----
    if cnb_token and cnb_url:
        try:
            push_to_remote(build_push_url(cnb_url, cnb_token, "cnb"), refspecs)
            typer.secho("✓ 推送 cnb", fg=typer.colors.GREEN)
        except RuntimeError as e:
            typer.secho(f"✗ 推送 cnb 失败: {e}", fg=typer.colors.RED, err=True)
    elif not cnb_token:
        typer.secho("⚠ CNB_TOKEN 未配置,跳过 cnb 同步", fg=typer.colors.YELLOW)
    elif not cnb_url:
        typer.secho(
            "⚠ CNB_TOKEN 已配置但未找到 cnb remote(git remote add cnb <url>?)"
            ",跳过 cnb 同步",
            fg=typer.colors.YELLOW,
        )

    # ---- 3. Gitee 创建 Release + 上传产物 ----
    if gitee_token and gitee_url:
        try:
            owner, repo = parse_owner_repo(gitee_url)
            rid = create_gitee_release(gitee_token, owner, repo, tag, tag, body)
            if rid is not None:
                typer.secho(f"✓ 创建 Gitee Release {tag}(id={rid})", fg=typer.colors.GREEN)
                for f in arts:
                    upload_gitee_asset(gitee_token, owner, repo, rid, f)
                typer.secho(f"✓ 上传 {len(arts)} 个产物到 Gitee", fg=typer.colors.GREEN)
            else:
                typer.secho(f"⚠ Gitee Release {tag} 已存在,跳过创建", fg=typer.colors.YELLOW)
        except RuntimeError as e:
            typer.secho(f"✗ Gitee Release 操作失败: {e}", fg=typer.colors.RED, err=True)

    # ---- 4. 清理旧 Release ----
    if gh_token:
        try:
            cleanup_old_releases(gh_token, "github", gh_owner, gh_repo, keep=keep)
        except RuntimeError as e:
            typer.secho(f"✗ 清理 GitHub Release 失败: {e}", fg=typer.colors.RED, err=True)
    else:
        typer.secho("⚠ GH_TOKEN 未配置,跳过 GitHub Release 清理", fg=typer.colors.YELLOW)

    if gitee_token and gitee_url:
        try:
            owner, repo = parse_owner_repo(gitee_url)
            cleanup_old_releases(gitee_token, "gitee", owner, repo, keep=keep)
        except RuntimeError as e:
            typer.secho(f"✗ 清理 Gitee Release 失败: {e}", fg=typer.colors.RED, err=True)

    typer.secho("✓ sync 完成", fg=typer.colors.GREEN)


if __name__ == "__main__":
    cli()
