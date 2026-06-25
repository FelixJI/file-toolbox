"""mkdir 命令:批量创建文件夹层级。"""

from pathlib import Path

import typer

from file_toolbox.core.batch_mkdir import ConflictStrategy, FolderCreatorService

_STRATEGY_MAP = {"skip": ConflictStrategy.SKIP, "merge": ConflictStrategy.MERGE}


def mkdir(
    root: Path = typer.Option(Path("."), "--root", help="根目录"),
    levels: list[str] = typer.Option([], "--levels", help='层级,用 / 分隔,如 "部门A/项目1"'),
    from_table: Path | None = typer.Option(None, "--from-table", help="从 Tab 分隔文件读结构"),
    on_conflict: str = typer.Option("merge", "--on-conflict", help="skip|merge"),
):
    """批量创建文件夹。"""
    strategy = _STRATEGY_MAP.get(on_conflict, ConflictStrategy.MERGE)
    svc = FolderCreatorService()
    structures: list[tuple[str, ...]] = []

    if from_table:
        text = from_table.read_text(encoding="utf-8")
        vr = svc.parse_excel_table_data(text)
        if not vr.valid:
            typer.secho(f"错误:{vr.error_message}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        typer.echo(f"检测到无效字符 {len(vr.invalid_folders)} 处(将被替换为 _)")
        structures = [tuple(svc.replace_special_chars(p) for p in s) for s in vr.folder_structure]
    else:
        for lv in levels:
            parts = tuple(svc.replace_special_chars(p) for p in lv.split("/"))
            structures.append(parts)

    if not structures:
        typer.secho("错误:未提供层级(--levels 或 --from-table)", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    items = svc.build_folder_paths(root, structures)
    typer.echo(f"将创建 {len(items)} 个文件夹于 {root}:")
    for it in items:
        mark = "[已存在]" if it.exists else "[新建]"
        typer.echo(f"  {mark} {it.path}")

    result = svc.create_folders(items, strategy)
    typer.secho(
        f"\n完成: 新建 {result.created_count}, 跳过 {result.skipped_count}, 共 {result.total_count}",
        fg=typer.colors.GREEN if result.success else typer.colors.RED,
    )
    if not result.success:
        typer.secho(result.error_message, fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
