"""sync_mirrors.py 测试:纯函数 + 网络 mock + 端到端桩测。"""

import sys
from pathlib import Path

# 让 tests 能 import scripts 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from scripts.sync_mirrors import parse_owner_repo  # noqa: E402


class TestParseOwnerRepo:
    def test_gitee_with_git_suffix(self):
        url = "https://gitee.com/felixjii/file-toolbox.git"
        assert parse_owner_repo(url) == ("felixjii", "file-toolbox")

    def test_cnb_without_git_suffix(self):
        url = "https://cnb.cool/feljii/file-toolbox"
        assert parse_owner_repo(url) == ("feljii", "file-toolbox")

    def test_github_with_git_suffix(self):
        url = "https://github.com/FelixJI/file-toolbox.git"
        assert parse_owner_repo(url) == ("FelixJI", "file-toolbox")

    def test_strips_trailing_slash(self):
        url = "https://gitee.com/felixjii/file-toolbox/"
        assert parse_owner_repo(url) == ("felixjii", "file-toolbox")

    def test_unparseable_raises(self):
        with pytest.raises(ValueError):
            parse_owner_repo("not-a-url")


from scripts.sync_mirrors import version_to_tag, build_push_url  # noqa: E402


class TestVersionToTag:
    def test_plain_release(self):
        assert version_to_tag("1.2.3") == "v1.2.3"

    def test_prerelease(self):
        assert version_to_tag("1.2.3a1") == "v1.2.3a1"


class TestBuildPushUrl:
    def test_gitee_url(self):
        url = build_push_url("https://gitee.com/felixjii/file-toolbox.git", "TOK", "gitee")
        assert url == "https://TOK@gitee.com/felixjii/file-toolbox.git"

    def test_cnb_url(self):
        url = build_push_url("https://cnb.cool/feljii/file-toolbox", "TOK", "cnb")
        # CNB 用户名固定为 cnb
        assert url == "https://cnb:TOK@cnb.cool/feljii/file-toolbox"

    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError):
            build_push_url("https://example.com/a/b", "TOK", "weird")


from scripts.sync_mirrors import releases_to_delete  # noqa: E402


class TestReleasesToDelete:
    def _rel(self, rid, created_at):
        return {"id": rid, "created_at": created_at}

    def test_keeps_latest_five(self):
        """7 个 release,保留最近 5 个(created_at 降序),删 2 个最旧。"""
        rels = [
            self._rel(1, "2026-01-01T00:00:00Z"),
            self._rel(2, "2026-02-01T00:00:00Z"),
            self._rel(3, "2026-03-01T00:00:00Z"),
            self._rel(4, "2026-04-01T00:00:00Z"),
            self._rel(5, "2026-05-01T00:00:00Z"),
            self._rel(6, "2026-06-01T00:00:00Z"),
            self._rel(7, "2026-07-01T00:00:00Z"),
        ]
        to_delete = releases_to_delete(rels, keep=5)
        # 保留 7,6,5,4,3;删 1,2
        assert set(to_delete) == {1, 2}

    def test_under_five_deletes_none(self):
        rels = [self._rel(1, "2026-01-01T00:00:00Z"), self._rel(2, "2026-02-01T00:00:00Z")]
        assert releases_to_delete(rels, keep=5) == []

    def test_exactly_five_deletes_none(self):
        rels = [self._rel(i, f"2026-0{i}-01T00:00:00Z") for i in range(1, 6)]
        assert releases_to_delete(rels, keep=5) == []

    def test_empty_list(self):
        assert releases_to_delete([], keep=5) == []

    def test_includes_prereleases(self):
        """预发布版同样计入保留窗口(按 created_at 排序,不区分类型)。"""
        rels = [
            self._rel(1, "2026-01-01T00:00:00Z"),
            self._rel(2, "2026-02-01T00:00:00Z"),
            self._rel(3, "2026-03-01T00:00:00Z"),
            self._rel(4, "2026-04-01T00:00:00Z"),
            self._rel(5, "2026-05-01T00:00:00Z"),
            self._rel(6, "2026-06-01T00:00:00Z"),
        ]
        assert releases_to_delete(rels, keep=5) == [1]

    def test_custom_keep(self):
        rels = [self._rel(i, f"2026-0{i}-01T00:00:00Z") for i in range(1, 5)]
        assert releases_to_delete(rels, keep=2) == [1, 2]


from scripts.sync_mirrors import _http, _build_multipart  # noqa: E402


class TestBuildMultipart:
    def test_boundary_present(self):
        body, content_type = _build_multipart({"name": ("f.zip", b"DATA")})
        assert content_type.startswith("multipart/form-data; boundary=")
        # body 含文件名与内容
        assert b"f.zip" in body
        assert b"DATA" in body

    def test_multiple_files(self):
        body, content_type = _build_multipart(
            {"a": ("a.txt", b"AAA"), "b": ("b.txt", b"BBB")}
        )
        assert b"AAA" in body and b"BBB" in body


class TestHttp:
    def test_get_returns_json(self, monkeypatch):
        """桩 urlopen,验证 GET 返回解析后的 JSON + 状态码。"""
        import io

        captured = {}

        class FakeResp:
            def __init__(self):
                self._buf = io.BytesIO(b'{"ok": true}')

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return self._buf.read()

            @property
            def status(self):
                return 200

        def fake_urlopen(req, timeout=None):
            captured["method"] = req.get_method()
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            return FakeResp()

        monkeypatch.setattr("scripts.sync_mirrors._urlopen", fake_urlopen)
        status, data = _http("GET", "https://example.com/api", token="TOK")
        assert status == 200
        assert data == {"ok": True}
        assert captured["method"] == "GET"
        # token 应出现在 Authorization header
        assert any("token" in v.lower() or "bearer" in v.lower() for v in captured["headers"].values())

    def test_post_with_form_data(self, monkeypatch):
        import io

        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return io.BytesIO(b'{"id": 42}').read()

            @property
            def status(self):
                return 201

        def fake_urlopen(req, timeout=None):
            captured["method"] = req.get_method()
            captured["data"] = req.data
            return FakeResp()

        monkeypatch.setattr("scripts.sync_mirrors._urlopen", fake_urlopen)
        status, data = _http("POST", "https://example.com/api", token="TOK", data={"name": "v1"})
        assert status == 201
        assert data == {"id": 42}
        assert captured["method"] == "POST"
        assert captured["data"] is not None  # 有 body

    def test_delete(self, monkeypatch):
        import io

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return io.BytesIO(b"").read()

            @property
            def status(self):
                return 204

        monkeypatch.setattr(
            "scripts.sync_mirrors._urlopen",
            lambda req, timeout=None: FakeResp(),
        )
        status, data = _http("DELETE", "https://example.com/api/1", token="TOK")
        assert status == 204

    def test_http_error_raises(self, monkeypatch):
        import io
        import urllib.error

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"message": "nope"}')
            )

        monkeypatch.setattr("scripts.sync_mirrors._urlopen", fake_urlopen)
        with pytest.raises(RuntimeError) as exc:
            _http("GET", "https://example.com/api", token="TOK")
        assert "404" in str(exc.value)


import scripts.sync_mirrors as sm  # noqa: E402
from scripts.sync_mirrors import list_releases, delete_release  # noqa: E402


class TestListReleases:
    def test_gitee_normalizes_fields(self, monkeypatch):
        """Gitee 返回的 created_at → 统一 {id, created_at} 字典。"""
        captured = {}

        def fake_http(method, url, token=None, **kw):
            captured["url"] = url
            captured["method"] = method
            return 200, [
                {"id": 11, "tag_name": "v1", "created_at": "2026-01-01T00:00:00+08:00"},
                {"id": 22, "tag_name": "v2", "created_at": "2026-02-01T00:00:00+08:00"},
            ]

        monkeypatch.setattr(sm, "_http", fake_http)
        rels = list_releases("TOK", "gitee", "felixjii", "file-toolbox")
        assert rels == [
            {"id": 11, "created_at": "2026-01-01T00:00:00+08:00"},
            {"id": 22, "created_at": "2026-02-01T00:00:00+08:00"},
        ]
        assert "gitee.com/api/v5/repos/felixjii/file-toolbox/releases" in captured["url"]

    def test_github_normalizes_fields(self, monkeypatch):
        def fake_http(method, url, token=None, **kw):
            assert "api.github.com/repos/felixjii/file-toolbox/releases" in url
            return 200, [
                {"id": 9, "created_at": "2026-01-01T00:00:00Z"},
            ]

        monkeypatch.setattr(sm, "_http", fake_http)
        rels = list_releases("TOK", "github", "felixjii", "file-toolbox")
        assert rels == [{"id": 9, "created_at": "2026-01-01T00:00:00Z"}]

    def test_empty_list(self, monkeypatch):
        monkeypatch.setattr(sm, "_http", lambda *a, **k: (200, []))
        assert list_releases("TOK", "github", "o", "r") == []


class TestDeleteRelease:
    def test_gitee_delete(self, monkeypatch):
        captured = {}

        def fake_http(method, url, token=None, **kw):
            captured["method"] = method
            captured["url"] = url
            return 204, None

        monkeypatch.setattr(sm, "_http", fake_http)
        delete_release("TOK", "gitee", "felixjii", "file-toolbox", 99)
        assert captured["method"] == "DELETE"
        assert "gitee.com/api/v5/repos/felixjii/file-toolbox/releases/99" in captured["url"]

    def test_github_delete(self, monkeypatch):
        captured = {}

        def fake_http(method, url, token=None, **kw):
            captured["url"] = url
            return 204, None

        monkeypatch.setattr(sm, "_http", fake_http)
        delete_release("TOK", "github", "felixjii", "file-toolbox", 7)
        assert "api.github.com/repos/felixjii/file-toolbox/releases/7" in captured["url"]


from scripts.sync_mirrors import (  # noqa: E402
    create_gitee_release,
    upload_gitee_asset,
    cleanup_old_releases,
)


class TestCreateGiteeRelease:
    def test_creates_and_returns_id(self, monkeypatch):
        captured = {}

        def fake_http(method, url, token=None, data=None, **kw):
            captured["method"] = method
            captured["url"] = url
            captured["data"] = data
            if method == "GET":
                # 查重:该 tag 不存在 → Gitee 返回 404,经 _http 转为 RuntimeError
                raise RuntimeError("HTTP 404 ...: b''")
            return 201, {"id": 555}

        monkeypatch.setattr(sm, "_http", fake_http)
        rid = create_gitee_release("TOK", "felixjii", "file-toolbox", "v1.2.3", "v1.2.3", "notes")
        assert rid == 555
        assert captured["method"] == "POST"
        assert captured["data"]["tag_name"] == "v1.2.3"
        assert captured["data"]["body"] == "notes"

    def test_returns_none_if_already_exists(self, monkeypatch):
        """重跑:Gitee 该 tag 已有 Release → 查重返回 None(跳过创建)。"""
        calls = []

        def fake_http(method, url, token=None, data=None, **kw):
            calls.append((method, url))
            # 第一次 GET 查重返回已存在
            if method == "GET":
                return 200, {"id": 7, "tag_name": "v1.2.3"}
            return 201, {"id": 99}

        monkeypatch.setattr(sm, "_http", fake_http)
        rid = create_gitee_release("TOK", "felixjii", "file-toolbox", "v1.2.3", "v1.2.3", "notes")
        assert rid is None
        # 只 GET 查重,未 POST 创建
        assert all(m == "GET" for m, _ in calls)


class TestUploadGiteeAsset:
    def test_uploads_file(self, monkeypatch, tmp_path):
        captured = {}

        def fake_http(method, url, token=None, files=None, **kw):
            captured["url"] = url
            captured["files"] = files
            return 201, {"name": "x"}

        monkeypatch.setattr(sm, "_http", fake_http)
        f = tmp_path / "checksums.txt"
        f.write_text("abc123  pkg.zip", encoding="utf-8")
        upload_gitee_asset("TOK", "felixjii", "file-toolbox", 555, f)
        assert "releases/555/attach_files" in captured["url"]
        assert "checksums.txt" in captured["files"]["file"][0]


class TestCleanupOldReleases:
    def test_deletes_old_keeps_recent(self, monkeypatch, capsys):
        rels = [
            {"id": i, "created_at": f"2026-0{i}-01T00:00:00Z"} for i in range(1, 8)
        ]
        deleted = []

        def fake_list(token, platform, owner, repo):
            return rels

        def fake_delete(token, platform, owner, repo, rid):
            deleted.append(rid)

        monkeypatch.setattr(sm, "list_releases", fake_list)
        monkeypatch.setattr(sm, "delete_release", fake_delete)
        cleanup_old_releases("TOK", "github", "o", "r", keep=5)
        # 7 个 → 删最旧 2 个(id 1,2)
        assert set(deleted) == {1, 2}

    def test_delete_failure_warns_not_raises(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sm, "list_releases", lambda *a: [{"id": i, "created_at": f"2026-0{i}-01"} for i in range(1, 8)]
        )

        def fake_delete(*a):
            raise RuntimeError("boom")

        monkeypatch.setattr(sm, "delete_release", fake_delete)
        # 不抛
        cleanup_old_releases("TOK", "github", "o", "r", keep=5)
        out = capsys.readouterr().out
        assert "警告" in out or "失败" in out

    def test_nothing_to_delete(self, monkeypatch):
        called = {"delete": 0}
        monkeypatch.setattr(sm, "list_releases", lambda *a: [])
        monkeypatch.setattr(
            sm, "delete_release", lambda *a: called.__setitem__("delete", called["delete"] + 1)
        )
        cleanup_old_releases("TOK", "github", "o", "r", keep=5)
        assert called["delete"] == 0


from scripts.sync_mirrors import push_to_remote, resolve_github_repo  # noqa: E402


class TestPushToRemote:
    def test_pushes_branch_and_tag(self, monkeypatch):
        """验证推送 main 分支 + tag,且 url 带认证(不含 token 泄漏到 stderr)。"""
        calls = []

        def fake_run(cmd, cwd=None, check=True, capture_output=True, text=True):
            calls.append(cmd)
            import subprocess

            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(sm.subprocess, "run", fake_run)
        push_to_remote(
            "https://TOK@gitee.com/felixjii/file-toolbox.git",
            ["main", "refs/tags/v1.2.3"],
        )
        # 一次 push,目标 url 带认证,refspec 含 main + tag
        assert len(calls) == 1
        git_cmd = calls[0]
        assert git_cmd[0] == "git"
        assert git_cmd[1] == "push"
        assert "https://TOK@gitee.com/felixjii/file-toolbox.git" in git_cmd
        assert "main" in git_cmd
        assert "refs/tags/v1.2.3" in git_cmd

    def test_push_failure_raises(self, monkeypatch):
        import subprocess

        def fake_run(cmd, cwd=None, check=True, capture_output=True, text=True):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="denied")

        monkeypatch.setattr(sm.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError):
            push_to_remote("https://x@y/z.git", ["main"])


class TestResolveGithubRepo:
    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REPOSITORY", "FelixJI/file-toolbox")
        assert resolve_github_repo() == ("FelixJI", "file-toolbox")

    def test_from_remote_fallback(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        # 桩 _git_remote_url
        monkeypatch.setattr(
            sm, "_git_remote_url", lambda name="origin": "https://github.com/FelixJI/file-toolbox.git"
        )
        assert resolve_github_repo() == ("FelixJI", "file-toolbox")


from typer.testing import CliRunner  # noqa: E402

from scripts.sync_mirrors import cli  # noqa: E402

runner = CliRunner()


class TestSyncCommand:
    """端到端桩测:桩掉所有网络/git,验证编排顺序、跳过逻辑、token 缺失处理。"""

    def _stubs(self, monkeypatch, tmp_path):
        calls = []

        def fake_push(url, refspecs):
            calls.append(("push", url, tuple(refspecs)))

        def fake_create(token, owner, repo, tag, name, body):
            calls.append(("create_gitee", tag))
            return 100

        def fake_upload(token, owner, repo, rid, fpath):
            calls.append(("upload", rid, str(fpath)))

        def fake_cleanup(token, platform, owner, repo, keep=5):
            calls.append(("cleanup", platform, keep))

        monkeypatch.setattr(sm, "push_to_remote", fake_push)
        monkeypatch.setattr(sm, "create_gitee_release", fake_create)
        monkeypatch.setattr(sm, "upload_gitee_asset", fake_upload)
        monkeypatch.setattr(sm, "cleanup_old_releases", fake_cleanup)
        monkeypatch.setattr(sm, "resolve_github_repo", lambda: ("FelixJI", "file-toolbox"))
        monkeypatch.setattr(sm, "_git_remote_url", lambda name: {
            "gitee": "https://gitee.com/felixjii/file-toolbox.git",
            "cnb": "https://cnb.cool/feljii/file-toolbox",
        }[name])
        # 造产物文件
        arts = tmp_path / "artifacts"
        arts.mkdir()
        (arts / "FileToolbox-1.2.3-win64.zip").write_bytes(b"ZIP")
        (arts / "checksums.txt").write_text("hash zip", encoding="utf-8")
        notes = tmp_path / "release_notes.md"
        notes.write_text("# v1.2.3\n- new", encoding="utf-8")
        monkeypatch.setenv("GITEE_TOKEN", "GTOK")
        monkeypatch.setenv("CNB_TOKEN", "CTOK")
        monkeypatch.setenv("GH_TOKEN", "GHTOK")
        return calls, arts, notes

    def test_full_sync_runs_all_steps(self, monkeypatch, tmp_path):
        calls, arts, notes = self._stubs(monkeypatch, tmp_path)
        r = runner.invoke(
            cli,
            ["--version", "1.2.3", "--notes-file", str(notes), "--artifacts-dir", str(arts)],
        )
        assert r.exit_code == 0, r.output
        # 推 gitee + 推 cnb(各含 main + tag)
        pushes = [c for c in calls if c[0] == "push"]
        assert len(pushes) == 2
        refspecs = {c[2] for c in pushes}
        assert ("main", "refs/tags/v1.2.3") in refspecs
        # 创建 gitee release
        assert ("create_gitee", "v1.2.3") in calls
        # 上传 2 个产物
        uploads = [c for c in calls if c[0] == "upload"]
        assert len(uploads) == 2
        # 清理 github + gitee
        cleanups = [c for c in calls if c[0] == "cleanup"]
        platforms = {c[1] for c in cleanups}
        assert platforms == {"github", "gitee"}

    def test_missing_gitee_token_skips_gitee(self, monkeypatch, tmp_path):
        calls, arts, notes = self._stubs(monkeypatch, tmp_path)
        monkeypatch.delenv("GITEE_TOKEN", raising=False)
        r = runner.invoke(
            cli, ["--version", "1.2.3", "--notes-file", str(notes), "--artifacts-dir", str(arts)]
        )
        assert r.exit_code == 0, r.output
        # 不创建 gitee release,不清理 gitee;但仍推 cnb、清理 github
        assert not any(c[0] == "create_gitee" for c in calls)
        assert not any(c[0] == "cleanup" and c[1] == "gitee" for c in calls)
        assert any(c[0] == "push" and "cnb" in c[1] for c in calls)

    def test_missing_cnb_token_skips_cnb_push(self, monkeypatch, tmp_path):
        calls, arts, notes = self._stubs(monkeypatch, tmp_path)
        monkeypatch.delenv("CNB_TOKEN", raising=False)
        r = runner.invoke(
            cli, ["--version", "1.2.3", "--notes-file", str(notes), "--artifacts-dir", str(arts)]
        )
        assert r.exit_code == 0, r.output
        # 推 gitee 但不推 cnb
        push_urls = [c[1] for c in calls if c[0] == "push"]
        assert any("gitee" in u for u in push_urls)
        assert not any("cnb" in u for u in push_urls)

    def test_missing_gh_token_skips_github_cleanup(self, monkeypatch, tmp_path):
        calls, arts, notes = self._stubs(monkeypatch, tmp_path)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        r = runner.invoke(
            cli, ["--version", "1.2.3", "--notes-file", str(notes), "--artifacts-dir", str(arts)]
        )
        assert r.exit_code == 0, r.output
        assert not any(c[0] == "cleanup" and c[1] == "github" for c in calls)
        # gitee 清理仍跑
        assert any(c[0] == "cleanup" and c[1] == "gitee" for c in calls)

    def test_push_failure_does_not_abort_others(self, monkeypatch, tmp_path):
        calls, arts, notes = self._stubs(monkeypatch, tmp_path)

        def fake_push(url, refspecs):
            if "cnb" in url:
                raise RuntimeError("cnb push failed")
            calls.append(("push", url, tuple(refspecs)))

        monkeypatch.setattr(sm, "push_to_remote", fake_push)
        r = runner.invoke(
            cli, ["--version", "1.2.3", "--notes-file", str(notes), "--artifacts-dir", str(arts)]
        )
        # 仍 exit 0(continue-on-error 语义:单步失败警告,不崩)
        assert r.exit_code == 0, r.output
        assert "cnb" in r.output  # 错误信息提到 cnb
        # gitee 推送/创建/清理仍执行
        assert any(c[0] == "push" and "gitee" in c[1] for c in calls)
