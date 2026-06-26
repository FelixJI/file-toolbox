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


class TestMigrateChangelog:
    def _sample(self) -> str:
        return """# Changelog

## [Unreleased]

### Added
- 新功能 A
- 新功能 B

### Fixed
- 修 bug X

## 0.1.0 - 2026-06-25

### Added
- 初始功能
"""

    def test_moves_unreleased_to_new_version(self):
        from scripts.bump_version import migrate_changelog

        result = migrate_changelog(self._sample(), "0.2.0", "2026-06-26")
        # 新版本段在 Unreleased 之后
        assert "## [Unreleased]" in result
        assert "## 0.2.0 - 2026-06-26" in result
        # 新功能 A/B 移到了 0.2.0 段
        idx_unreleased = result.index("## [Unreleased]")
        idx_new = result.index("## 0.2.0 - 2026-06-26")
        idx_old = result.index("## 0.1.0")
        assert idx_unreleased < idx_new < idx_old
        assert "新功能 A" in result[result.index("## 0.2.0"):result.index("## 0.1.0")]

    def test_empty_unreleased_still_emits_new_section(self):
        from scripts.bump_version import migrate_changelog

        empty = """# Changelog

## [Unreleased]

## 0.1.0 - 2026-06-25

### Added
- 初始
"""
        result = migrate_changelog(empty, "0.2.0", "2026-06-26")
        assert "## 0.2.0 - 2026-06-26" in result
        # Unreleased 段保留(可能为空)
        assert "## [Unreleased]" in result

    def test_markdown_blank_lines_preserved(self):
        """标题行之间必须有空行(整洁 Markdown)。"""
        from scripts.bump_version import migrate_changelog

        result = migrate_changelog(self._sample(), "0.2.0", "2026-06-26")
        # 新版本标题后应紧跟空行再接子标题
        assert "## 0.2.0 - 2026-06-26\n\n### Added" in result
