"""sync_mirrors.py 测试:纯函数 + 网络 mock + 端到端桩测。"""

import sys
from pathlib import Path

# 让 tests 能 import scripts 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from scripts.sync_mirrors import parse_owner_repo  # noqa: E402


class TestParseOwnerRepo:
    def test_gitee_with_git_suffix(self):
        url = "https://gitee.com/felixjii/file-toolbox.git"
        assert parse_owner_repo(url) == ("felixjii", "file-toolbox")

    def test_cnb_without_git_suffix(self):
        url = "https://cnb.cool/feljii/file-toolbox"
        assert parse_owner_repo(url) == ("feljii", "file-toolbox")

    def test_github_with_git_suffix(self):
        url = "https://github.com/FelixJI/file-toolbox.git"
        assert parse_owner_repo(url) == ("FelixJI", "file-toolbox")

    def test_strips_trailing_slash(self):
        url = "https://gitee.com/felixjii/file-toolbox/"
        assert parse_owner_repo(url) == ("felixjii", "file-toolbox")

    def test_unparseable_raises(self):
        with pytest.raises(ValueError):
            parse_owner_repo("not-a-url")
