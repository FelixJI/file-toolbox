"""invoice 命令:电子发票识别,导出 Excel/JSON。默认预览,--yes 执行。"""

from pathlib import Path

import typer

from file_toolbox.core.invoice.dedupe import KEEP_ALL
from file_toolbox.core.invoice.service import InvoiceService

_DEFAULT_OUTPUT = "发票结果.xlsx"


def _expand(files: list[Path], directory: Path | None, recursive: bool) -> list[Path]:
    """扩展文件列表(同 rename),去重保持顺序。"""
    result: list[Path] = list(files)
    if directory:
        if recursive:
            result.extend(p for p in directory.rglob("*") if p.is_file())
        else:
            result.extend(p for p in directory.iterdir() if p.is_file())
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in result:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def invoice(
    files: list[Path] = typer.Argument(None, help="发票文件(zip/xml/ofd/pdf)"),
    directory: Path | None = typer.Option(None, "--dir", help="目录批量加入"),
    recursive: bool = typer.Option(False, "--recursive", help="递归子目录"),
    fmt: str = typer.Option("excel", "--format", help="excel|json|both"),
    output: Path = typer.Option(_DEFAULT_OUTPUT, "--output", "-o", help="输出路径"),
    dedupe: str = typer.Option(KEEP_ALL, "--dedupe", help="keep_all|dedupe|mark"),
    yes: bool = typer.Option(False, "--yes", help="跳过预览直接导出(默认仅预览)"),
) -> None:
    """识别电子发票(PDF/OFD/XML),导出 Excel 或 JSON。"""
    all_files = _expand(files or [], directory, recursive)
    if not all_files:
        typer.secho("错误:未选择任何文件", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    valid_dedupe = InvoiceService.supported_dedupe_strategies()
    if dedupe not in valid_dedupe:
        typer.secho(
            f"错误:无效的 --dedupe 策略: {dedupe}(可选: {', '.join(valid_dedupe)})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    valid_fmt = InvoiceService.supported_formats()
    if fmt not in valid_fmt:
        typer.secho(
            f"错误:无效的 --format: {fmt}(可选: {', '.join(valid_fmt)})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    svc = InvoiceService()
    result = svc.parse_files(all_files, dedupe_strategy=dedupe)

    # 预览输出
    typer.echo("预览:")
    for inv in result.invoices:
        mark = " [重复]" if inv.is_duplicate else ""
        typer.echo(
            f"  {inv.invoice_number} | {inv.amount_with_tax} | "
            f"{inv.parse_method} | {inv.source_file}{mark}"
        )
    if result.duplicates:
        typer.echo(f"\n去重移除 {len(result.duplicates)} 条:")
        for d in result.duplicates:
            typer.echo(f"  {d.invoice_number} | {d.parse_method} | {d.source_file}")
    if result.failed:
        typer.echo(f"\n失败 {len(result.failed)} 条:")
        for f in result.failed:
            typer.secho(f"  {f.file}: {f.reason}", fg=typer.colors.YELLOW)
    typer.echo(
        f"\n共 {len(all_files)} 个文件: 成功 {len(result.invoices)}, "
        f"重复 {len(result.duplicates)}, 失败 {len(result.failed)}"
    )

    if not yes:
        typer.echo("(预览模式,加 --yes 导出)")
        return

    # 导出
    json_path = None
    if fmt == "both":
        json_path = output.with_suffix(".json")
    elif fmt == "json" and output.suffix.lower() == ".xlsx":
        output = output.with_suffix(".json")
    elif fmt == "excel" and output.suffix.lower() == ".json":
        output = output.with_suffix(".xlsx")

    written = svc.export(result, output, fmt=fmt, json_path=json_path, dedupe_strategy=dedupe)
    typer.secho(f"\n已导出 {len(written)} 个文件:", fg=typer.colors.GREEN)
    for w in written:
        typer.echo(f"  {w}")
