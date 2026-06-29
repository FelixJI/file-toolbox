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
