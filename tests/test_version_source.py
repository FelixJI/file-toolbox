"""验证 __version__ 通过 importlib.metadata 读取,不硬编码。"""

import re
from pathlib import Path

import file_toolbox


def test_version_is_string():
    """__version__ 必须是字符串(无论安装与否都不报错)。"""
    assert isinstance(file_toolbox.__version__, str)
    assert file_toolbox.__version__  # 非空


def test_version_no_hardcoded_literal():
    """__init__.py 不应再出现 __version__ = "0.1.0" 这类硬编码。"""
    src = (Path(__file__).resolve().parents[1] / "file_toolbox" / "__init__.py").read_text(
        encoding="utf-8"
    )
    # 允许 importlib.metadata 读取,禁止直接赋值字面量版本号
    forbidden = re.compile(r'__version__\s*=\s*"\d+\.\d+\.\d+"')
    assert not forbidden.search(src), "__init__.py 仍硬编码 __version__,应改用 importlib.metadata"
