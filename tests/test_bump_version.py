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


class TestUpdateUvLock:
    """update_uv_lock_version: 文本替换 uv.lock 中 file-toolbox 段的 version 行。

    本项目 editable 安装,改自身版本号只需替换 lockfile 的 version 行,与 uv lock 等价。
    关键不变量:只改 file-toolbox 段,绝不误伤其他包(即使别处也有相同版本字符串)。
    """

    _LOCK_HEAD = """version = 1

[[package]]
name = "other-pkg"
version = "0.1.2"
source = { registry = "..." }

[[package]]
name = "file-toolbox"
version = "0.1.1"
source = { editable = "." }
dependencies = [
    { name = "typer" },
]

[package.optional-dependencies]
dev = []

[package.metadata]

[[package]]
name = "yet-another"
version = "0.1.2"
source = { registry = "..." }
"""

    def test_replaces_file_toolbox_version(self, tmp_path):
        from scripts.bump_version import update_uv_lock_version

        (tmp_path / "uv.lock").write_text(self._LOCK_HEAD, encoding="utf-8")
        update_uv_lock_version(tmp_path, "1.2.3")
        text = (tmp_path / "uv.lock").read_text(encoding="utf-8")
        # file-toolbox 段已更新
        assert 'name = "file-toolbox"\nversion = "1.2.3"' in text

    def test_does_not_touch_other_packages(self, tmp_path):
        """other-pkg / yet-another 的 version 行(同为 0.1.2)必须原样保留。"""
        from scripts.bump_version import update_uv_lock_version

        (tmp_path / "uv.lock").write_text(self._LOCK_HEAD, encoding="utf-8")
        update_uv_lock_version(tmp_path, "9.9.9")
        text = (tmp_path / "uv.lock").read_text(encoding="utf-8")
        # 其余段的 0.1.2 不应被改成 9.9.9(段内 version 行已被 file-toolbox 消耗)
        assert text.count('version = "9.9.9"') == 1
        assert text.count('version = "0.1.2"') == 2  # other-pkg + yet-another

    def test_missing_file_toolbox_raises(self, tmp_path):
        import pytest

        from scripts.bump_version import update_uv_lock_version

        (tmp_path / "uv.lock").write_text(
            '[[package]]\nname = "other"\nversion = "1.0"\n', encoding="utf-8"
        )
        with pytest.raises(ValueError):
            update_uv_lock_version(tmp_path, "2.0")

    def test_missing_uv_lock_raises(self, tmp_path):
        # 目录里没有 uv.lock → OSError(读失败),而非静默通过
        import pytest

        from scripts.bump_version import update_uv_lock_version

        with pytest.raises(OSError):
            update_uv_lock_version(tmp_path, "2.0")


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
        assert "新功能 A" in result[result.index("## 0.2.0") : result.index("## 0.1.0")]

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


class TestPyprojectVersionIO:
    def test_read_current_version(self, tmp_path):
        from scripts.bump_version import read_pyproject_version

        pj = tmp_path / "pyproject.toml"
        pj.write_text('[project]\nname = "file-toolbox"\nversion = "0.3.7"\n', encoding="utf-8")
        assert read_pyproject_version(pj) == "0.3.7"

    def test_write_version_preserves_rest(self, tmp_path):
        from scripts.bump_version import read_pyproject_version, write_pyproject_version

        original = (
            '[project]\nname = "file-toolbox"\nversion = "0.3.7"\nrequires-python = ">=3.11"\n'
        )
        pj = tmp_path / "pyproject.toml"
        pj.write_text(original, encoding="utf-8")
        write_pyproject_version(pj, "0.4.0")
        new = pj.read_text(encoding="utf-8")
        assert read_pyproject_version(pj) == "0.4.0"
        # 其他行保持不变
        assert 'name = "file-toolbox"' in new
        assert 'requires-python = ">=3.11"' in new
        # 只有一处 version 行
        assert new.count("version =") == 1


class TestExtractChangelog:
    def test_extract_existing_version(self):
        from scripts.extract_changelog import extract_version_notes

        content = """# Changelog

## [Unreleased]

## 0.2.0 - 2026-06-26

### Added
- 新功能 A

### Fixed
- bug X

## 0.1.0 - 2026-06-25

### Added
- 初始
"""
        notes = extract_version_notes(content, "0.2.0")
        assert "新功能 A" in notes
        assert "bug X" in notes
        assert "初始" not in notes  # 不含旧版本

    def test_version_not_found_raises(self):
        import pytest

        from scripts.extract_changelog import extract_version_notes

        with pytest.raises(ValueError):
            extract_version_notes("# Changelog\n## 0.1.0\n\n- x\n", "9.9.9")
