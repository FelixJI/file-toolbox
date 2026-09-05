"""excel-merge 命令:合并多个 Excel 文件的工作表。默认预览,--yes 执行。"""

from pathlib import Path

import typer

from file_toolbox.common.file_utils import expand_files
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.excel_merge import (
    DEFAULT_OUTPUT_NAME,
    MODE_VALUES,
    NAMING_PREFIX,
    SUPPORTED_MODES,
    SUPPORTED_NAMING,
    SUPPORTED_SUFFIXES,
    ExcelMergeService,
    MergeOptions,
)


def excel_merge(
    files: list[Path] = typer.Argument(None, help="源 Excel 文件(.xlsx/.xlsm)"),
    directory: Path | None = typer.Option(None, "--dir", help="目录批量加入"),
    recursive: bool = typer.Option(False, "--recursive", help="递归子目录"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help=f"输出文件(默认:首个源文件目录下的 {DEFAULT_OUTPUT_NAME})"
    ),
    naming: str = typer.Option(NAMING_PREFIX, "--naming", help="prefix|keep"),
    mode: str = typer.Option(MODE_VALUES, "--mode", help="values|formulas"),
    include_hidden: bool = typer.Option(False, "--include-hidden", help="包含隐藏工作表"),
    yes: bool = typer.Option(False, "--yes", help="跳过预览直接执行(默认仅预览)"),
) -> None:
    """合并多个 Excel 的工作表为一个工作簿(纯 openpyxl,跨平台,不依赖 Office)。"""
    if directory is not None and not directory.is_dir():
        typer.secho(f"错误:--dir 不是目录: {directory}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    all_files = expand_files(files or [], directory, recursive)
    sources = [p for p in all_files if p.suffix.lower() in SUPPORTED_SUFFIXES]
    skipped = len(all_files) - len(sources)
    if skipped:
        typer.secho(
            f"已忽略 {skipped} 个不支持的文件(仅支持 {'/'.join(SUPPORTED_SUFFIXES)})",
            fg=typer.colors.YELLOW,
        )
    if not sources:
        typer.secho("错误:未选择任何受支持的 Excel 文件", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if naming not in SUPPORTED_NAMING:
        typer.secho(
            f"错误:无效的 --naming: {naming}(可选: {'/'.join(SUPPORTED_NAMING)})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    if mode not in SUPPORTED_MODES:
        typer.secho(
            f"错误:无效的 --mode: {mode}(可选: {'/'.join(SUPPORTED_MODES)})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    if output is None:
        output = sources[0].parent / DEFAULT_OUTPUT_NAME

    options = MergeOptions(naming=naming, mode=mode, include_hidden=include_hidden)
    svc = ExcelMergeService(history_store=JsonHistoryStore())

    if not yes:
        plans, failed = svc.plan_sheets(sources, options)
        typer.echo("预览:")
        for p in plans:
            if p.included:
                typer.echo(f"  {p.file} | {p.sheet} -> {p.target_name}")
            else:
                typer.echo(f"  {p.file} | {p.sheet} [跳过:{p.note}]")
        for f in failed:
            typer.secho(f"  {f.file} [失败] {f.error}", fg=typer.colors.YELLOW)
        n_merged = sum(1 for p in plans if p.included)
        typer.echo(
            f"\n共 {len(sources)} 个文件: 合并 {n_merged} 个工作表, "
            f"失败 {len(failed)} 个文件 -> {output}(已存在时自动加序号)"
        )
        typer.echo("(预览模式,加 --yes 执行;输出永不覆盖已有文件)")
        return

    result = svc.merge(
        sources, output, options, progress_callback=lambda c, t, m: typer.echo(f"  [{c}/{t}] {m}")
    )
    for f in result.failed:
        typer.secho(f"  失败: {f.file} - {f.error}", fg=typer.colors.YELLOW)
    if result.success:
        assert result.output is not None
        typer.secho(
            f"\n完成: {len(result.sheets)} 个工作表 -> {result.output}", fg=typer.colors.GREEN
        )
    else:
        reason = "已取消" if result.cancelled else result.error_message
        typer.secho(f"\n失败: {reason}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
