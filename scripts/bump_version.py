"""版本号管理:bump / current / validate。

单一真相源:pyproject.toml [project] version。
运行方式:uv run --extra dev python scripts/bump_version.py <command>
"""

from __future__ import annotations

from packaging.version import InvalidVersion, Version

PARTS = ("major", "minor", "patch", "prerelease")


def validate_pep440(version: str) -> bool:
    """校验字符串是否符合 PEP 440。"""
    try:
        Version(version)
        return True
    except InvalidVersion:
        return False


def bump_version(current: str, part: str) -> str:
    """根据 part 计算下一个版本号(PEP 440)。

    part:
      - patch:   1.2.3   → 1.2.4
      - minor:   1.2.3   → 1.3.0
      - major:   1.2.3   → 2.0.0
      - prerelease:
          预发布版(1.2.3a1) → 1.2.3(转正)
          正式版(1.2.3)    → 1.2.4a1(开新预发布)
    """
    if part not in PARTS:
        raise ValueError(f"无效的 part: {part!r},应为 {PARTS}")
    if not validate_pep440(current):
        raise ValueError(f"当前版本不符合 PEP 440: {current!r}")

    v = Version(current)
    if part == "patch":
        return f"{v.major}.{v.minor}.{v.micro + 1}"
    if part == "minor":
        return f"{v.major}.{v.minor + 1}.0"
    if part == "major":
        return f"{v.major + 1}.0.0"
    # prerelease
    if v.is_prerelease:
        # 转正:去掉预发布后缀
        return f"{v.major}.{v.minor}.{v.micro}"
    # 正式版 → 开新预发布(patch+1 加 a1)
    return f"{v.major}.{v.minor}.{v.micro + 1}a1"
