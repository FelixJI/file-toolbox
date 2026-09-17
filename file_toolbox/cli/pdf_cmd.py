"""pdf 命令:批量生成 PDF,默认预览,--yes 执行。"""

from pathlib import Path

import typer

from file_toolbox.cli.resources import close_on_exit, run_reported
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_pdf import PDFGeneratorService
from file_toolbox.core.batch_pdf.constants import (
    DPI_DEFAULT,
    OUTPUT_SEPARATE,
    PAPER_SIZES,
    PDF_TYPE_EDITABLE,
    PRINT_MODE_SINGLE,
)


def pdf(
    files: list[Path] = typer.Argument(None, help="源文件"),
    output_mode: str = typer.Option(OUTPUT_SEPARATE, "--output-mode", help="separate|merge"),
    merge_name: str = typer.Option("合并文档.pdf", "--merge-name", help="合并文件名"),
    pdf_type: str = typer.Option(PDF_TYPE_EDITABLE, "--pdf-type", help="editable|image"),
    dpi: int = typer.Option(DPI_DEFAULT, "--dpi", min=1, help="图片型 DPI"),
    paper: str = typer.Option("auto", "--paper", help="auto|A3|A4|A5|Letter|Legal"),
    orientation: str = typer.Option("auto", "--orientation", help="auto|portrait|landscape"),
    engine: str = typer.Option("auto", "--engine", help="auto|office|wps"),
    yes: bool = typer.Option(False, "--yes", help="确认生成 PDF(默认仅预览)"),
) -> None:
    """批量生成 PDF(Word/Excel/PPT/图片/PDF)。"""
    if not files:
        typer.secho("错误:未提供文件", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    for flag, value, choices in (
        ("--output-mode", output_mode, ("separate", "merge")),
        ("--pdf-type", pdf_type, ("editable", "image")),
        ("--paper", paper, ("auto", *PAPER_SIZES)),
        ("--orientation", orientation, ("auto", "auto_detect", "portrait", "landscape")),
        ("--engine", engine, ("auto", "office", "wps")),
    ):
        if value not in choices:
            raise typer.BadParameter(f"可选值: {', '.join(choices)}", param_hint=flag)
    for source in files:
        if not source.is_file():
            raise typer.BadParameter(f"不是文件: {source}", param_hint="files")
    if not yes:
        typer.echo(f"预览: {len(files)} 个源文件, 输出模式 {output_mode}, PDF 类型 {pdf_type}")
        for source in files:
            typer.echo(f"  {source}")
        typer.echo("(加 --yes 生成 PDF;输出在源文件旁,同名时自动加序号;此预览不运行转换)")
        return

    config = {
        "pdf_type": pdf_type,
        "dpi": dpi,
        "paper_size": paper,
        "orientation": orientation,
        "engine": engine,
        "output_mode": output_mode,
        "same_as_source": True,
        "print_mode": PRINT_MODE_SINGLE,
        "merge_filename": merge_name,
    }

    def progress(cur: int, total: int, msg: str) -> None:
        typer.echo(f"  [{cur}/{total}] {msg}")

    svc = PDFGeneratorService(history_store=JsonHistoryStore())
    with close_on_exit(lambda: svc.close(strict=True)):
        results, history_failed = run_reported(lambda: svc.batch_generate(files, config, progress))
        ok = sum(1 for r in results if r["success"])
        fail = sum(1 for r in results if not r["success"])
        for r in results:
            mark = "OK" if r["success"] else "FAIL"
            typer.echo(f"  {mark} {r['source'].name} -> {r['output'].name}")
            if not r["success"]:
                typer.secho(f"      {r['error']}", fg=typer.colors.YELLOW)
        typer.secho(
            f"\n完成: 成功 {ok}, 失败 {fail}",
            fg=typer.colors.GREEN if fail == 0 else typer.colors.YELLOW,
        )
        if fail or history_failed:
            raise typer.Exit(1)
