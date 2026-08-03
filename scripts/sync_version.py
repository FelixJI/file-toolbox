"""把 pyproject.toml 的发布版本派生到 uv.lock。"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


def sync_version(root: Path, version: str) -> None:
    """只更新派生锁文件；版本的唯一写入点是 pyproject.toml。"""
    pyproject = root / "pyproject.toml"
    source = pyproject.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(?m)^(version\s*=\s*")[^"]+("\s*)$',
        rf"\g<1>{version}\g<2>",
        source,
        count=1,
    )
    if count != 1:
        raise ValueError("pyproject.toml must contain exactly one project.version")
    pyproject.write_text(updated, encoding="utf-8")

    lock = root / "uv.lock"
    lock_source = lock.read_text(encoding="utf-8")
    lock_updated, lock_count = re.subn(
        r'(name = "file-toolbox"\s*\nversion = ")[^"]+("[^\n]*\nsource = \{ editable = "\." \})',
        rf"\g<1>{version}\g<2>",
        lock_source,
        count=1,
    )
    if lock_count != 1:
        raise ValueError("uv.lock must contain one editable file-toolbox package")
    lock.write_text(lock_updated, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--project-root",
        default=None,
        help="默认使用 AUTOMATION_PROJECT_ROOT，再回退为脚本所在仓库。",
    )
    args = parser.parse_args()
    root = Path(
        args.project_root or os.environ.get("AUTOMATION_PROJECT_ROOT", Path(__file__).parents[1])
    )
    sync_version(root.resolve(), args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
