"""从 CHANGELOG.md 提取指定版本的 Release notes(CI 发版用)。

用法: python scripts/extract_changelog.py <version> [--out release_notes.md]
"""

from __future__ import annotations

import re
from pathlib import Path

import typer

_CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def extract_version_notes(content: str, version: str) -> str:
    """提取 CHANGELOG.md 中某版本段的内容(到下一个版本标题前)。"""
    # 匹配 ## <version> 或 ## <version> - <date>
    pattern = re.compile(
        rf"^## {re.escape(version)}(?:\s+-\s+\S+)?\s*\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(content)
    if not m:
        raise ValueError(f"CHANGELOG.md 中未找到版本 {version}")
    return m.group(1).strip()


cli = typer.Typer(add_completion=False, help="提取 CHANGELOG 指定版本 Release notes")


@cli.command()
def main(
    version: str = typer.Argument(..., help="版本号,如 0.2.0"),
    out: Path = typer.Option(Path("release_notes.md"), "--out", help="输出文件"),
) -> None:
    """提取并写入 Release notes 文件。"""
    content = _CHANGELOG.read_text(encoding="utf-8")
    notes = extract_version_notes(content, version)
    out.write_text(notes + "\n", encoding="utf-8")
    typer.echo(f"✓ Release notes 写入 {out}")


if __name__ == "__main__":
    cli()
