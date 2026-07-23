"""rename 命令:批量重命名,默认预览,--yes 执行。"""

from pathlib import Path

import typer

from file_toolbox.cli.op_parser import parse_ops
from file_toolbox.core.batch_rename import FileRenameService


def _expand(files: list[Path], directory: Path | None, recursive: bool) -> list[Path]:
    result: list[Path] = []
    result.extend(files)
    if directory:
        if recursive:
            result.extend(p for p in directory.rglob("*") if p.is_file())
        else:
            result.extend(p for p in directory.iterdir() if p.is_file())
    # 去重,保持顺序
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in result:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def rename(
    files: list[Path] = typer.Argument(None, help="要重命名的文件"),
    op: list[str] = typer.Option([], "--op", help="操作,格式 type:key=value,可多次"),
    directory: Path | None = typer.Option(None, "--dir", help="目录(批量加入)"),
    recursive: bool = typer.Option(False, "--recursive", help="递归子目录"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认直接执行(默认仅预览)"),
) -> None:
    """批量重命名文件。"""
    operations = parse_ops(op)
    if not operations:
        typer.secho("错误:至少需要一个 --op 操作", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    all_files = _expand(files or [], directory, recursive)
    if not all_files:
        typer.secho("错误:未选择任何文件", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    svc = FileRenameService()
    valid, msg = svc.validate_operations(operations)
    if not valid:
        typer.secho(f"错误:{msg}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    result = svc.apply_operations(all_files, operations)

    typer.echo("预览:")
    for old, (new, status) in result.items():
        typer.echo(f"  {old.name}  ->  {new.name}   [{status}]")

    ready = sum(1 for _, s in result.values() if "准备" in s)
    conflict = sum(1 for _, s in result.values() if "冲突" in s)
    error = sum(1 for _, s in result.values() if "错误" in s)
    typer.echo(f"\n共 {len(result)} 个文件: 就绪 {ready}, 冲突 {conflict}, 错误 {error}")

    if not yes:
        typer.echo("\n(预览模式,加 --yes 执行)")
        return

    rename_map = {old: new for old, (new, s) in result.items() if "准备" in s}
    count, errors = svc.execute_rename(rename_map)
    typer.secho(f"\n已重命名 {count} 个文件", fg=typer.colors.GREEN)
    for e in errors:
        typer.secho(f"  失败: {e}", fg=typer.colors.YELLOW)
