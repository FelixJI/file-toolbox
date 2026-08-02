"""校验 squash 后会进入 main 的 PR 标题符合 Conventional Commits。"""

from __future__ import annotations

import os
import re

ALLOWED_TYPES = (
    "feat",
    "fix",
    "perf",
    "deps",
    "revert",
    "docs",
    "style",
    "chore",
    "refactor",
    "test",
    "build",
    "ci",
)

_TITLE = re.compile(rf"^(?:{'|'.join(ALLOWED_TYPES)})(?:\([a-z0-9][a-z0-9._/-]*\))?!?: \S.*$")


def title_error(title: str) -> str | None:
    """返回标题错误；符合约定时返回 ``None``。"""
    if _TITLE.fullmatch(title):
        return None
    types = ", ".join(ALLOWED_TYPES)
    return (
        "PR 标题必须使用 Conventional Commits："
        "type(scope): description 或 type!: description；"
        f"允许的 type：{types}。当前标题：{title!r}"
    )


def main() -> int:
    title = os.environ.get("PR_TITLE", "")
    error = title_error(title)
    if error:
        print(f"::error::{error}")
        return 1
    print(f"PR title is conventional: {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
