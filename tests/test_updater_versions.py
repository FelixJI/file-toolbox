"""updater 版本来源层测试。"""

import pytest

from file_toolbox.updater.versions import (
    GITHUB_REPO,
    GITEE_REPO,
    RemoteRelease,
    _is_prerelease,
    is_newer,
    strip_v_prefix,
)


class TestStripVPrefix:
    def test_with_v(self):
        assert strip_v_prefix("v1.2.0") == "1.2.0"

    def test_without_v(self):
        assert strip_v_prefix("1.2.0") == "1.2.0"


class TestIsPrerelease:
    @pytest.mark.parametrize("v", ["1.2.3a1", "1.2.3b2", "1.2.3rc1", "1.2.3.dev0", "1.2.3alpha1", "1.2.3beta1"])
    def test_prerelease_versions(self, v):
        assert _is_prerelease(v) is True

    @pytest.mark.parametrize("v", ["1.2.3", "0.1.0", "1.0.0", "2.0"])
    def test_stable_versions(self, v):
        assert _is_prerelease(v) is False


class TestIsNewer:
    def test_higher_patch(self):
        assert is_newer("1.2.3", "1.2.2") is True

    def test_lower_patch(self):
        assert is_newer("1.2.1", "1.2.2") is False

    def test_higher_minor(self):
        assert is_newer("1.3.0", "1.2.9") is True

    def test_higher_major(self):
        assert is_newer("2.0.0", "1.9.9") is True

    def test_equal(self):
        assert is_newer("1.2.3", "1.2.3") is False

    def test_fewer_segments(self):
        # 1.2 视作 1.2.0
        assert is_newer("1.2.1", "1.2") is True

    def test_local_version_suffix_ignored(self):
        # 带 +local 后缀的(开发态 0.0.0+unknown)不影响比对
        assert is_newer("1.2.3", "0.0.0+unknown") is True


class TestRepoConstants:
    def test_github_repo(self):
        assert GITHUB_REPO == ("FelixJI", "file-toolbox")

    def test_gitee_repo(self):
        assert GITEE_REPO == ("felixjii", "file-toolbox")


class TestRemoteRelease:
    def test_is_frozen(self):
        rel = RemoteRelease("1.0.0", "http://x/a.zip", "http://x/checksums.txt", "github")
        # frozen dataclass 不可变
        with pytest.raises(Exception):
            rel.version = "2.0.0"  # type: ignore[misc]
