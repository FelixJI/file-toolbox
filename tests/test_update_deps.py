"""update_deps.py 的 lockfile diff 解析测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.update_deps import diff_upgrades, parse_lock_versions  # noqa: E402


def _lock_snippet(packages: dict[str, str]) -> str:
    """生成 uv.lock 片段(只含 package 段的 name/version)。"""
    blocks = []
    for name, ver in packages.items():
        blocks.append(f'name = "{name}"\nversion = "{ver}"\nsdist = {{ }}\n')
    return "\n".join(blocks)


def test_parse_lock_versions():
    text = _lock_snippet({"pdfplumber": "0.11.0", "openpyxl": "3.1.2"})
    versions = parse_lock_versions(text)
    assert versions == {"pdfplumber": "0.11.0", "openpyxl": "3.1.2"}


def test_diff_upgrades():
    before = {"pdfplumber": "0.11.0", "openpyxl": "3.1.2", "PySide6": "6.5.0"}
    after = {"pdfplumber": "0.11.3", "openpyxl": "3.1.2", "PySide6": "6.7.2"}
    upgrades = diff_upgrades(before, after)
    # 只列变化的包
    assert upgrades == {"pdfplumber": ("0.11.0", "0.11.3"), "PySide6": ("6.5.0", "6.7.2")}


def test_diff_no_change():
    before = {"a": "1.0.0"}
    after = {"a": "1.0.0"}
    assert diff_upgrades(before, after) == {}


def test_diff_new_package_ignored():
    # 新增包不算"升级"
    before = {"a": "1.0.0"}
    after = {"a": "1.0.0", "b": "2.0.0"}
    assert diff_upgrades(before, after) == {}
