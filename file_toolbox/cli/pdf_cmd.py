"""pdf 命令:批量生成 PDF。"""

from pathlib import Path

import typer

from file_toolbox.core.batch_pdf import PDFGeneratorService
from file_toolbox.core.batch_pdf.constants import (
    DPI_DEFAULT,
    OUTPUT_SEPARATE,
    PDF_TYPE_EDITABLE,
    PRINT_MODE_SINGLE,
)


def pdf(
    files: list[Path] = typer.Argument(None, help="源文件"),
    output_mode: str = typer.Option(OUTPUT_SEPARATE, "--output-mode", help="separate|merge"),
    merge_name: str = typer.Option("合并文档.pdf", "--merge-name", help="合并文件名"),
    pdf_type: str = typer.Option(PDF_TYPE_EDITABLE, "--pdf-type", help="editable|image"),
    dpi: int = typer.Option(DPI_DEFAULT, "--dpi", help="图片型 DPI"),
    paper: str = typer.Option("auto", "--paper", help="auto|A3|A4|A5|Letter|Legal"),
    orientation: str = typer.Option("auto", "--orientation", help="auto|portrait|landscape"),
    engine: str = typer.Option("auto", "--engine", help="auto|office|wps"),
) -> None:
    """批量生成 PDF(Word/Excel/PPT/图片/PDF)。"""
    if not files:
        typer.secho("错误:未提供文件", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    svc = PDFGeneratorService()
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

    results = svc.batch_generate(files, config, progress)
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
    svc.close()
