"""GitHub 代理 URL 变换器测试。"""

import pytest

from file_toolbox.updater import proxy


@pytest.fixture
def no_env(monkeypatch):
    """清掉环境变量,隔离测试。"""
    monkeypatch.delenv(proxy.ENV_VAR, raising=False)
    return monkeypatch


class TestEnvVar:
    def test_env_var_name(self):
        assert proxy.ENV_VAR == "FILE_TOOLBOX_GH_PROXY"


class TestGetProxy:
    def test_empty_when_nothing_set(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert proxy.get_proxy() == ""

    def test_env_overrides_settings(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxy", "https://from-settings.com")
        no_env.setenv(proxy.ENV_VAR, "https://from-env.com")
        assert proxy.get_proxy() == "https://from-env.com"

    def test_settings_used_when_no_env(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxy", "https://from-settings.com")
        assert proxy.get_proxy() == "https://from-settings.com"

    def test_normalizes_trailing_slash(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://ghproxy.com/")
        assert proxy.get_proxy() == "https://ghproxy.com"

    def test_normalizes_missing_scheme(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "ghproxy.com")
        assert proxy.get_proxy() == "https://ghproxy.com"

    def test_empty_string_env_means_none(self, no_env, tmp_path, monkeypatch):
        """空串环境变量视为未设置(回退到 settings/空)。"""
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "")
        assert proxy.get_proxy() == ""

    def test_settings_returns_empty_short_circuits(self, no_env, tmp_path, monkeypatch):
        """settings["gh_proxy"] 显式返回空 → get_proxy() 返回 ""(覆盖 line 41 短路)。

        raw 经 os.environ/settings 取得空串时 `if raw else ""` 直接返回 "",
        不进入 _normalize(line 52 的短路)。显式 monkeypatch settings.get 返回 ""。
        """
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        monkeypatch.setattr(settings, "get", lambda key, default="": "")
        assert proxy.get_proxy() == ""

    def test_whitespace_only_raw_returns_empty(self, no_env, tmp_path, monkeypatch):
        """raw 为纯空白串(truthy 但 strip() 后为空)→ _normalize 返回 ""(覆盖 line 41)。

        env var 设为 "   "(truthy,绕过 line 52 的 `if raw else ""` 短路,进入 _normalize;
        _normalize 内 s=raw.strip() 为空 → line 41 `return ""`)。
        """
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "   ")
        assert proxy.get_proxy() == ""
        # _normalize 直接验证 line 41
        assert proxy._normalize("   ") == ""


class TestIsGithub:
    """覆盖 _is_github 的异常/无 host 分支(missing 59-60)。"""

    def test_urlparse_value_error_returns_false(self):
        """让 urlparse 抛 ValueError(畸形 IPv6 括号)→ 返回 False(不向上抛)。"""
        # "http://[::1" 触发 urlparse 的 "Invalid IPv6 URL" ValueError
        assert proxy._is_github("http://[::1") is False

    def test_host_none_returns_false(self):
        """非 URL(无 host)→ hostname 为 None → False。"""
        assert proxy._is_github("not-a-url") is False


class TestApplyProxy:
    def test_no_proxy_returns_unchanged(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        url = "https://github.com/a/b.zip"
        assert proxy.apply_proxy(url) == url

    def test_github_com_prefixed(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://ghproxy.com")
        assert (
            proxy.apply_proxy("https://github.com/a/b.zip")
            == "https://ghproxy.com/https://github.com/a/b.zip"
        )

    def test_api_github_com_prefixed(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://ghproxy.com")
        assert (
            proxy.apply_proxy("https://api.github.com/repos/x/y/releases/latest")
            == "https://ghproxy.com/https://api.github.com/repos/x/y/releases/latest"
        )

    def test_objects_githubusercontent_prefixed(self, no_env, tmp_path, monkeypatch):
        """下载重定向域名也走代理。"""
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://ghproxy.com")
        assert (
            proxy.apply_proxy(
                "https://objects.githubusercontent.com/github-production-release-asset"
            )
            == "https://ghproxy.com/https://objects.githubusercontent.com/github-production-release-asset"
        )

    def test_codeload_github_com_prefixed(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://ghproxy.com")
        assert (
            proxy.apply_proxy("https://codeload.github.com/x/y/zip/refs/tags/v1")
            == "https://ghproxy.com/https://codeload.github.com/x/y/zip/refs/tags/v1"
        )

    def test_raw_githubusercontent_prefixed(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://ghproxy.com")
        assert (
            proxy.apply_proxy("https://raw.githubusercontent.com/x/y/main/f")
            == "https://ghproxy.com/https://raw.githubusercontent.com/x/y/main/f"
        )

    def test_non_github_url_unchanged(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://ghproxy.com")
        assert proxy.apply_proxy("https://example.com/file.zip") == "https://example.com/file.zip"


class TestDefaultProxies:
    """预置默认代理候选常量。"""

    def test_default_proxies_nonempty(self):
        assert len(proxy.DEFAULT_PROXIES) >= 1

    def test_default_proxies_all_https_normalized(self):
        for p in proxy.DEFAULT_PROXIES:
            assert p.startswith("https://")
            assert not p.endswith("/")  # 归一化无尾斜杠


class TestGetEnabledProxies:
    """get_enabled_proxies:读 gh_proxies 列表 + 旧 gh_proxy 迁移 + 归一化去重。"""

    def test_empty_when_nothing_set(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert proxy.get_enabled_proxies() == []

    def test_reads_gh_proxies_list(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://a.com", "https://b.com"])
        assert proxy.get_enabled_proxies() == ["https://a.com", "https://b.com"]

    def test_normalizes_and_dedups(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set(
            "gh_proxies",
            ["https://a.com/", "a.com", "https://b.com", "  ", "b.com"],  # 含尾斜杠/无scheme/重复
        )
        # a.com 无 scheme → https://a.com;https://a.com/ → https://a.com;去重保序
        assert proxy.get_enabled_proxies() == ["https://a.com", "https://b.com"]

    def test_legacy_gh_proxy_migrated_when_no_list(self, no_env, tmp_path, monkeypatch):
        """未设 gh_proxies 但有旧 gh_proxy → 迁移为单元素列表(向后兼容)。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxy", "https://legacy.com")
        assert proxy.get_enabled_proxies() == ["https://legacy.com"]

    def test_gh_proxies_takes_precedence_over_legacy(self, no_env, tmp_path, monkeypatch):
        """同时有 gh_proxies(空列表)和 gh_proxy → 不迁移旧值(列表优先)。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", [])
        settings.set("gh_proxy", "https://legacy.com")
        assert proxy.get_enabled_proxies() == []

    def test_non_list_gh_proxies_ignored(self, no_env, tmp_path, monkeypatch):
        """gh_proxies 为非 list(损坏)→ 视为未设置,迁移旧 gh_proxy。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", "not-a-list")
        settings.set("gh_proxy", "https://legacy.com")
        assert proxy.get_enabled_proxies() == ["https://legacy.com"]


class TestGetFetchCandidates:
    """get_fetch_candidates:env + enabled + 直连兜底,去重保序。"""

    def test_default_only_direct(self, no_env, tmp_path, monkeypatch):
        """无任何配置 → 仅直连 [""]。"""
        monkeypatch.chdir(tmp_path)
        assert proxy.get_fetch_candidates() == [""]

    def test_env_first_then_direct(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://env-proxy.com")
        assert proxy.get_fetch_candidates() == ["https://env-proxy.com", ""]

    def test_env_enabled_then_direct(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://env-proxy.com")
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://a.com", "https://b.com"])
        assert proxy.get_fetch_candidates() == [
            "https://env-proxy.com",
            "https://a.com",
            "https://b.com",
            "",
        ]

    def test_dedup_keeps_order(self, no_env, tmp_path, monkeypatch):
        """env 与 enabled 重复 → 去重保序;末尾总直连。"""
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://a.com")
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://a.com", "https://b.com", "a.com"])
        assert proxy.get_fetch_candidates() == ["https://a.com", "https://b.com", ""]

    def test_direct_always_last(self, no_env, tmp_path, monkeypatch):
        """直连("")总在末尾(即便 enabled 列表很长)。"""
        monkeypatch.chdir(tmp_path)
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://x.com", "https://y.com"])
        cands = proxy.get_fetch_candidates()
        assert cands[-1] == ""  # 末尾直连
        assert "" not in cands[:-1]  # 直连只在末尾出现一次


class TestApplyProxyExplicitProxy:
    """apply_proxy(url, proxy=...):显式 proxy 参数。"""

    def test_explicit_proxy_prefixes(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        url = "https://github.com/a/b.zip"
        assert proxy.apply_proxy(url, proxy="https://explicit.com") == (
            "https://explicit.com/https://github.com/a/b.zip"
        )

    def test_explicit_empty_string_is_direct(self, no_env, tmp_path, monkeypatch):
        """显式 proxy='' → 直连(不拼接),即使 get_proxy() 非空。"""
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://should-be-ignored.com")
        url = "https://github.com/a/b.zip"
        assert proxy.apply_proxy(url, proxy="") == url

    def test_none_uses_get_proxy(self, no_env, tmp_path, monkeypatch):
        """proxy=None → 用 get_proxy()(向后兼容默认行为)。"""
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://auto.com")
        url = "https://github.com/a/b.zip"
        assert proxy.apply_proxy(url) == "https://auto.com/https://github.com/a/b.zip"
        assert proxy.apply_proxy(url, proxy=None) == "https://auto.com/https://github.com/a/b.zip"

    def test_explicit_proxy_non_github_unchanged(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert (
            proxy.apply_proxy("https://example.com/x", proxy="https://p.com")
            == "https://example.com/x"
        )


class TestGetProxyBackwardCompat:
    """get_proxy:首个候选,向后兼容旧测试。"""

    def test_returns_first_candidate(self, no_env, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        no_env.setenv(proxy.ENV_VAR, "https://first.com")
        from file_toolbox.common import settings

        settings.set("gh_proxies", ["https://second.com"])
        assert proxy.get_proxy() == "https://first.com"

    def test_returns_empty_when_all_empty(self, no_env, tmp_path, monkeypatch):
        """get_proxy 现在基于 candidates,candidates 至少含 [""]→ get_proxy 返回 ""。"""
        monkeypatch.chdir(tmp_path)
        assert proxy.get_proxy() == ""
