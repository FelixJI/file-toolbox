"""pdf-sort 命令:按文字层排序 PDF 页面。默认预览,--yes 执行。"""

from collections.abc import Iterable
from pathlib import Path

import typer

from file_toolbox.common.file_utils import expand_files
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.pdf_sort import (
    ORDER_ASC,
    SORTED_MARKER,
    SUPPORTED_ORDERS,
    SUPPORTED_SUFFIXES,
    SUPPORTED_UNMATCHED,
    UNMATCHED_LAST,
    PagePlan,
    PdfSortService,
    SortOptions,
)


def _print_plan_pages(plans_pages: Iterable[PagePlan], file_label: str, order_desc: str) -> None:
    """打印一个文件每页的 原页码 -> 新位置(或未匹配)明细。"""
    typer.echo(f"  {file_label}:")
    for p in plans_pages:
        key_desc = f'"{p.key}"' if p.matched else "[未匹配]" + (f"({p.note})" if p.note else "")
        if p.new_index >= 0:
            typer.echo(f"    第{p.page + 1}页 -> 第{p.new_index + 1}位  {key_desc}")
        else:
            typer.echo(f"    第{p.page + 1}页  {key_desc}")
    if order_desc:
        typer.echo(f"    {order_desc}")


def pdf_sort(
    files: list[Path] = typer.Argument(None, help="要排序的 PDF 文件"),
    pattern: str = typer.Option(
        ...,
        "--pattern",
        "-p",
        help="匹配正则表达式;首个捕获组作为排序文字,如 出库日期[:：]\\s*([0-9-]+)",
    ),
    directory: Path | None = typer.Option(None, "--dir", help="目录批量加入"),
    recursive: bool = typer.Option(False, "--recursive", help="递归子目录"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="输出文件(单文件)或输出目录(多文件);缺省写源文件旁"
    ),
    order: str = typer.Option(ORDER_ASC, "--order", help="asc|desc"),
    unmatched: str = typer.Option(UNMATCHED_LAST, "--unmatched", help="first|last|fail"),
    yes: bool = typer.Option(False, "--yes", help="跳过预览直接执行(默认仅预览)"),
) -> None:
    """按文字层匹配的排序键(日期/流水号等)重排 PDF 页面,写出新文件。"""
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
        typer.secho("错误:未选择任何 PDF 文件", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if order not in SUPPORTED_ORDERS:
        typer.secho(
            f"错误:无效的 --order: {order}(可选: {'/'.join(SUPPORTED_ORDERS)})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    if unmatched not in SUPPORTED_UNMATCHED:
        typer.secho(
            f"错误:无效的 --unmatched: {unmatched}(可选: {'/'.join(SUPPORTED_UNMATCHED)})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    if output is not None and len(sources) > 1 and output.suffix.lower() == ".pdf":
        typer.secho(
            "错误:多个文件时 --output 应为输出目录(或不指定,写在源文件旁)",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    options = SortOptions(pattern=pattern, order=order, unmatched=unmatched)
    svc = PdfSortService(history_store=JsonHistoryStore())

    if not yes:
        try:
            plans, failed = svc.plan_pages(sources, options)
        except ValueError as e:
            typer.secho(f"错误:{e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from e
        typer.echo("预览:")
        for plan in plans:
            label = f"{plan.file}({len(plan.pages)} 页)"
            if plan.order is None:
                _print_plan_pages(plan.pages, f"{label} [不会排序]", plan.note)
            else:
                _print_plan_pages(plan.pages, label, "")
        for f in failed:
            typer.secho(f"  {f.file} [失败] {f.error}", fg=typer.colors.YELLOW)
        sortable = sum(1 for p in plans if p.order is not None)
        typer.echo(
            f"\n共 {len(sources)} 个文件: 可排序 {sortable}, 失败 {len(failed)}"
            f" -> 输出为源主名+{SORTED_MARKER}.pdf(已存在时自动加序号)"
        )
        typer.echo("(预览模式,加 --yes 执行;输出永不覆盖已有文件,源文件不被修改)")
        return

    try:
        result = svc.sort(sources, options, output=output)
    except ValueError as e:
        typer.secho(f"错误:{e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    for s in result.sorted_files:
        if s.output is not None:
            typer.echo(f"  OK {s.file} -> {s.output}")
        else:
            typer.echo(f"  OK {s.file} {s.note}")
    for f in result.failed:
        typer.secho(f"  失败: {f.file} - {f.error}", fg=typer.colors.YELLOW)
    if result.success:
        typer.secho(
            f"\n完成: 处理 {len(result.sorted_files)} 个文件, 写出 {result.written_count} 个输出",
            fg=typer.colors.GREEN,
        )
    else:
        reason = "已取消" if result.cancelled else result.error_message
        typer.secho(f"\n失败: {reason}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
