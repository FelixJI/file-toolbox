"""settings 轻量 JSON 设置存储测试。"""

import json

import pytest

from file_toolbox.common import settings
from file_toolbox.common.settings import _settings_path


@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    """隔离 cwd,使 settings 落到临时目录。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestSettingsPath:
    def test_path_under_data_dir(self, isolated_cwd):
        """settings 路径 = .file_toolbox/settings.json。"""
        p = _settings_path()
        assert p.name == "settings.json"
        assert p.parent.name == ".file_toolbox"


class TestGetSet:
    def test_get_missing_returns_default(self, isolated_cwd):
        assert settings.get("nope") is None
        assert settings.get("nope", "fallback") == "fallback"

    def test_set_then_get(self, isolated_cwd):
        settings.set("gh_proxy", "https://ghproxy.com")
        assert settings.get("gh_proxy") == "https://ghproxy.com"

    def test_overwrite(self, isolated_cwd):
        settings.set("k", 1)
        settings.set("k", 2)
        assert settings.get("k") == 2

    def test_other_keys_preserved(self, isolated_cwd):
        settings.set("a", 1)
        settings.set("b", 2)
        assert settings.get("a") == 1
        assert settings.get("b") == 2

    def test_persists_to_file(self, isolated_cwd):
        settings.set("gh_proxy", "https://x.com")
        data = json.loads((_settings_path()).read_text(encoding="utf-8"))
        assert data["gh_proxy"] == "https://x.com"


class TestCorruptionTolerance:
    def test_corrupt_json_returns_default(self, isolated_cwd):
        """settings.json 损坏 → get 返回 default 不抛。"""
        _settings_path().parent.mkdir(parents=True, exist_ok=True)
        _settings_path().write_text("{not valid json", encoding="utf-8")
        assert settings.get("anything", "d") == "d"

    def test_set_after_corruption_rewrites_clean(self, isolated_cwd):
        _settings_path().parent.mkdir(parents=True, exist_ok=True)
        _settings_path().write_text("garbage", encoding="utf-8")
        settings.set("k", "v")
        assert settings.get("k") == "v"

    @pytest.mark.parametrize("payload", ["[1, 2, 3]", '"a string"', "42", "true", "null"])
    def test_non_dict_valid_json_returns_default(self, isolated_cwd, payload):
        """合法但非 dict 的 JSON(列表/字符串/数字/布尔/null)→ _load 回退 {},get 返回 default。

        回归保护:isinstance(data, dict) 守卫若被移除,后续 .get 会 AttributeError。
        """
        _settings_path().parent.mkdir(parents=True, exist_ok=True)
        _settings_path().write_text(payload, encoding="utf-8")
        assert settings.get("anything", "d") == "d"
