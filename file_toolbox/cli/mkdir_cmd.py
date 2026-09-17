"""mkdir 命令:批量创建文件夹层级,默认预览,--yes 执行。"""

from pathlib import Path

import typer

from file_toolbox.cli.resources import run_reported
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_mkdir import ConflictStrategy, FolderCreatorService

_STRATEGY_MAP = {"skip": ConflictStrategy.SKIP, "merge": ConflictStrategy.MERGE}


def mkdir(
    root: Path = typer.Option(Path("."), "--root", help="根目录"),
    levels: list[str] = typer.Option([], "--levels", help='层级,用 / 分隔,如 "部门A/项目1"'),
    from_table: Path | None = typer.Option(None, "--from-table", help="从 Tab 分隔文件读结构"),
    on_conflict: str = typer.Option("merge", "--on-conflict", help="skip|merge"),
    yes: bool = typer.Option(False, "--yes", help="确认创建目录(默认仅预览)"),
) -> None:
    """批量创建文件夹。"""
    if on_conflict not in _STRATEGY_MAP:
        raise typer.BadParameter("必须为 skip 或 merge", param_hint="--on-conflict")
    strategy = _STRATEGY_MAP[on_conflict]
    svc = FolderCreatorService(history_store=JsonHistoryStore() if yes else None)
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

    if not yes:
        typer.echo("(预览模式,加 --yes 创建目录)")
        return

    result, history_failed = run_reported(
        lambda: svc.create_folders(items, strategy, root=str(root), structure_count=len(structures))
    )
    typer.secho(
        f"\n完成: 新建 {result.created_count}, 跳过 {result.skipped_count}, 共 {result.total_count}",
        fg=typer.colors.GREEN if result.success else typer.colors.RED,
    )
    if not result.success:
        typer.secho(result.error_message, fg=typer.colors.RED, err=True)
    if not result.success or history_failed:
        raise typer.Exit(1)
