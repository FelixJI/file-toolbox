"""bump_version.py 纯函数逻辑测试。"""

import sys
from pathlib import Path

# 让 tests 能 import scripts 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bump_version import bump_version, validate_pep440  # noqa: E402


class TestBumpVersion:
    def test_patch(self):
        assert bump_version("1.2.3", "patch") == "1.2.4"

    def test_minor_resets_patch(self):
        assert bump_version("1.2.3", "minor") == "1.3.0"

    def test_major_resets_minor_patch(self):
        assert bump_version("1.2.3", "major") == "2.0.0"

    def test_prerelease_dev_to_release(self):
        # dev/prerelease → 去掉预发布后缀,成为正式版
        assert bump_version("1.2.3a1", "prerelease") == "1.2.3"

    def test_prerelease_release_to_alpha(self):
        # 正式版 → 加 a1 预发布
        assert bump_version("1.2.3", "prerelease") == "1.2.4a1"

    def test_invalid_part_raises(self):
        import pytest

        with pytest.raises(ValueError):
            bump_version("1.2.3", "bogus")


class TestValidatePEP440:
    def test_valid_release(self):
        assert validate_pep440("1.2.3") is True

    def test_valid_prerelease(self):
        assert validate_pep440("1.2.3a1") is True

    def test_invalid(self):
        # 注意:packaging 的 PEP 440 解析较宽松(允许 1.2、1.2.3.4 等),
        # 故只测真正非法的字符串。
        assert validate_pep440("not-a-version") is False
        assert validate_pep440("") is False
        assert validate_pep440("1.2.x") is False
        assert validate_pep440("1..2") is False
