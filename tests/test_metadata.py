"""metadata 模块测试:元信息常量与 CHANGELOG 读取。"""

import file_toolbox
from file_toolbox.common import metadata


def test_version_matches_package():
    assert metadata.VERSION == file_toolbox.__version__


def test_app_name_is_file_toolbox():
    assert metadata.APP_NAME == "File Toolbox"


def test_repo_url_is_https():
    assert metadata.REPO_URL.startswith("https://")


def test_license_is_mit():
    assert metadata.LICENSE == "MIT"


def test_tech_stack_is_list_of_tuples():
    assert isinstance(metadata.TECH_STACK, list)
    assert len(metadata.TECH_STACK) > 0
    for item in metadata.TECH_STACK:
        assert isinstance(item, tuple)
        assert len(item) == 2
        assert isinstance(item[0], str)
        assert isinstance(item[1], str)


def test_python_requirement_string():
    assert "3.11" in metadata.PYTHON_REQUIREMENT


def test_get_changelog_finds_repo_root():
    """开发环境:CHANGELOG.md 在仓库根,应返回完整内容。"""
    text = metadata.get_changelog()
    assert isinstance(text, str)
    assert "Changelog" in text or "changelog" in text.lower()


def test_get_changelog_fallback_when_missing(tmp_path, monkeypatch):
    """模拟找不到 CHANGELOG.md:切到空目录,断言返回兜底字符串(含版本号),不抛异常。"""
    monkeypatch.chdir(tmp_path)
    # 同时屏蔽仓库根查找:让 _repo_root_changelog_path 指向不存在的地方
    monkeypatch.setattr(
        metadata, "_repo_root_changelog_path", lambda: tmp_path / "nope.md"
    )
    text = metadata.get_changelog()
    assert isinstance(text, str)
    assert file_toolbox.__version__ in text  # 兜底文本含版本号
