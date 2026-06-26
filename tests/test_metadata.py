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
