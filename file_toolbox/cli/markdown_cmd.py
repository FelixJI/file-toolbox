"""markdown-convert 命令:Markdown 批量转 Word/Excel。默认预览,--yes 执行。"""

from pathlib import Path

import typer

from file_toolbox.cli.resources import run_reported
from file_toolbox.common.file_utils import expand_files
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.markdown_convert import (
    EXCEL_MODE_TABLES,
    SUPPORTED_EXCEL_MODES,
    SUPPORTED_SUFFIXES,
    SUPPORTED_TARGETS,
    TARGET_DOCX,
    TARGET_XLSX,
    ConversionResult,
    MarkdownConvertService,
)


def markdown_convert(
    files: list[Path] = typer.Argument(None, help="源 Markdown 文件(.md/.markdown)"),
    directory: Path | None = typer.Option(None, "--dir", help="目录批量加入"),
    recursive: bool = typer.Option(False, "--recursive", help="递归子目录"),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="输出目录(默认:各源文件所在目录)"
    ),
    to: str = typer.Option(TARGET_DOCX, "--to", help="docx|xlsx"),
    excel_mode: str = typer.Option(
        EXCEL_MODE_TABLES, "--excel-mode", help="tables|document(仅 --to xlsx)"
    ),
    yes: bool = typer.Option(False, "--yes", help="跳过预览直接执行(默认仅预览)"),
) -> None:
    """把 Markdown 批量转换为 Word(Pandoc)或 Excel(openpyxl)(跨平台,不依赖 Office)。"""
    if directory is not None and not directory.is_dir():
        typer.secho(f"错误:--dir 不是目录: {directory}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    all_files = expand_files(files or [], directory, recursive)
    sources = [p for p in all_files if p.suffix.lower() in SUPPORTED_SUFFIXES]
    ignored = len(all_files) - len(sources)
    if ignored:
        typer.secho(
            f"已忽略 {ignored} 个不支持的文件(仅支持 {'/'.join(SUPPORTED_SUFFIXES)})",
            fg=typer.colors.YELLOW,
        )
    if not sources:
        typer.secho("错误:未选择任何受支持的 Markdown 文件", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if to not in SUPPORTED_TARGETS:
        typer.secho(
            f"错误:无效的 --to: {to}(可选: {'/'.join(SUPPORTED_TARGETS)})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    if excel_mode not in SUPPORTED_EXCEL_MODES:
        typer.secho(
            f"错误:无效的 --excel-mode: {excel_mode}(可选: {'/'.join(SUPPORTED_EXCEL_MODES)})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    if not yes:
        typer.echo("预览(路径计划,未解析内容):")
        for path in sources:
            base = output_dir if output_dir is not None else path.parent
            typer.echo(f"  {path} -> {base / f'{path.stem}.{to}'}")
        mode_note = f"(--excel-mode {excel_mode})" if to == TARGET_XLSX else ""
        typer.echo(f"\n共 {len(sources)} 个文件 -> {to}{mode_note}")
        if to == TARGET_XLSX and excel_mode == EXCEL_MODE_TABLES:
            typer.echo("(tables 模式仅提取表格;没有表格的文件会在执行时跳过)")
        typer.echo("(预览模式,加 --yes 执行;输出永不覆盖已有文件)")
        return

    svc = MarkdownConvertService(history_store=JsonHistoryStore())

    def run() -> ConversionResult:
        return svc.convert(
            sources,
            output_dir,
            target=to,
            excel_mode=excel_mode,
            progress_callback=lambda current, total, message: typer.echo(
                f"  [{current}/{total}] {message}"
            ),
        )

    try:
        result, history_failed = run_reported(run)
    except (ImportError, ValueError) as error:
        typer.secho(f"错误:{error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from error

    outputs = [item.output for item in result.items if item.output is not None]
    for item in result.items:
        if item.output is None:
            label = "跳过" if item.skipped else "失败"
            typer.secho(f"  {label}: {item.source.name} - {item.error}", fg=typer.colors.YELLOW)
    if result.cancelled:
        typer.secho(f"\n已取消:已完成 {len(outputs)} 个输出", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if not outputs:
        typer.secho("\n失败:没有写出任何输出", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.secho(f"\n完成: {len(outputs)} 个输出", fg=typer.colors.GREEN)
    for output in outputs:
        typer.echo(f"  {output}")
    if any(item.error and not item.skipped for item in result.items) or history_failed:
        raise typer.Exit(1)
