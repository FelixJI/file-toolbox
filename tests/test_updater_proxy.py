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
