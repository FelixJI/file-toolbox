"""replace 命令:批量内容替换。"""

from pathlib import Path

import typer

from file_toolbox.cli.op_parser import parse_ops
from file_toolbox.core.batch_replace import ContentReplaceService


def replace(
    files: list[Path] = typer.Argument(None, help="要处理的文件"),
    op: list[str] = typer.Option([], "--op", help="操作,格式 type:key=value,可多次"),
    yes: bool = typer.Option(False, "--yes", help="跳过预览直接执行"),
    keep_backup: bool = typer.Option(True, "--keep-backup/--no-backup", help="保留备份"),
):
    """批量替换 Word/Excel/txt 文档内容。"""
    operations = parse_ops(op)
    if not operations:
        typer.secho("错误:至少需要一个 --op 操作", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if not files:
        typer.secho("错误:未提供文件", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    svc = ContentReplaceService()
    valid, msg = svc.validate_operations(operations)
    if not valid:
        typer.secho(f"错误:{msg}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if not yes:
        typer.echo("预览匹配数:")
        result = svc.preview_replace(files, operations)
        matched = 0
        for f, info in result.items():
            typer.echo(f"  {f.name}: {info['match_count']} 处匹配  [{info['status']}]")
            matched += info["match_count"]
        typer.echo(f"\n总匹配 {matched} 处。(加 --yes 执行,执行前自动备份)")
        svc.close()
        return

    success, total, errors = svc.execute_replace(files, operations)
    typer.secho(f"\n完成: 处理 {success} 个文件, 替换 {total} 处", fg=typer.colors.GREEN)
    for e in errors:
        typer.secho(f"  失败: {e}", fg=typer.colors.YELLOW)
    svc.close()
