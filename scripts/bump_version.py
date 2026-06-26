"""版本号管理:bump / current / validate。

单一真相源:pyproject.toml [project] version。
运行方式:uv run --extra dev python scripts/bump_version.py <command>
"""

from __future__ import annotations

import re
from pathlib import Path

from packaging.version import InvalidVersion, Version

PARTS = ("major", "minor", "patch", "prerelease")

_VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


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


_UNRELEASED_HEADER = "## [Unreleased]"
_NEXT_HEADER_RE = re.compile(r"\n## ")


def migrate_changelog(content: str, new_version: str, date: str) -> str:
    """把 [Unreleased] 段的条目迁移到新版本段下,并重开空 Unreleased。

    迁移后结构:
        ...(标题行 # Changelog 等)

        ## [Unreleased]

        ## <new_version> - <date>
        ...(原 Unreleased 的条目)

        ## <older versions...>
    """
    if _UNRELEASED_HEADER not in content:
        raise ValueError("CHANGELOG.md 缺少 '## [Unreleased]' 段")

    unreleased_idx = content.index(_UNRELEASED_HEADER)
    # Unreleased 标题之后的内容
    after_unreleased = content[unreleased_idx + len(_UNRELEASED_HEADER):]
    # 下一个 "## " 标题之前 = Unreleased 条目体
    next_header_match = _NEXT_HEADER_RE.search(after_unreleased)
    if next_header_match:
        unreleased_body = after_unreleased[: next_header_match.start()]
        rest = after_unreleased[next_header_match.start():]  # 含前导 "\n## "
    else:
        unreleased_body = after_unreleased
        rest = ""

    # 新版本段:标题 + 空行 + 条目体(strip 去掉首尾多余空行)
    body = unreleased_body.strip()
    new_section = f"## {new_version} - {date}\n"
    if body:
        new_section += f"\n{body}\n"
    # 保留 content 中 Unreleased 标题之前的全部内容,然后接空 Unreleased + 新版本段 + 旧版本
    rebuilt = (
        content[:unreleased_idx]
        + f"{_UNRELEASED_HEADER}\n\n"
        + new_section
        + ("\n" + rest.lstrip("\n") if rest.strip() else "")
    )
    return rebuilt


def read_pyproject_version(path: Path) -> str:
    """从 pyproject.toml 读 [project] version。"""
    text = path.read_text(encoding="utf-8")
    m = _VERSION_LINE.search(text)
    if not m:
        raise ValueError(f'{path} 中未找到 version = "..." 行')
    return m.group(1)


def write_pyproject_version(path: Path, new_version: str) -> None:
    """把新版本写回 pyproject.toml,只替换 version 行,保留其余内容。"""
    if not validate_pep440(new_version):
        raise ValueError(f"新版本不符合 PEP 440: {new_version!r}")
    text = path.read_text(encoding="utf-8")
    new_text, n = _VERSION_LINE.subn(f'version = "{new_version}"', text, count=1)
    if n == 0:
        raise ValueError(f'{path} 中未找到 version = "..." 行')
    path.write_text(new_text, encoding="utf-8")
