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
