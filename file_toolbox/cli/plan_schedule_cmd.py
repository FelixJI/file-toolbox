"""plan-schedule 命令:项点清单生成按月排布表。默认预览,--yes 执行。"""

from pathlib import Path

import typer

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.plan_schedule import (
    DEFAULT_OUTPUT_NAME,
    SUPPORTED_SUFFIXES,
    InvalidRow,
    PlanScheduleService,
    ScheduleOptions,
)


def plan_schedule(
    input_path: Path = typer.Argument(
        None, help="项点清单 Excel(.xlsx/.xlsm),需含 项点名称/起始日期/终止日期 列"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help=f"输出文件(默认:输入文件目录下的 {DEFAULT_OUTPUT_NAME})"
    ),
    year: int | None = typer.Option(
        None, "--year", help="日期缺年份时使用的年份(如 9-17;默认取当前年份)"
    ),
    yes: bool = typer.Option(False, "--yes", help="跳过预览直接生成(默认仅预览)"),
) -> None:
    """按项点起止日期生成按月排布表(标记周末、项点内第几天、逐日并行数)。"""
    if input_path is None:
        typer.secho("错误:缺少项点清单文件参数", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if not input_path.is_file():
        typer.secho(f"错误:输入文件不存在:{input_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        typer.secho(
            f"错误:不支持的格式 {input_path.suffix or '(无后缀)'},"
            f"仅支持 {'/'.join(SUPPORTED_SUFFIXES)}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    if output is None:
        output = input_path.parent / DEFAULT_OUTPUT_NAME

    options = ScheduleOptions(default_year=year)
    svc = PlanScheduleService(history_store=JsonHistoryStore())
    try:
        items, invalid = svc.parse(input_path, options)
    except ValueError as e:
        typer.secho(f"错误:{e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e

    if not yes:
        if not items:
            _print_invalid(invalid)
            typer.secho("错误:没有可解析的项点", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        months = svc.plan(items)
        typer.echo(f"共 {len(items)} 个项点:")
        for it in items:
            typer.echo(f"  {it.name}  {it.start} ~ {it.end} ({it.days}天)")
        _print_invalid(invalid)
        if months:
            first, last = months[0], months[-1]
            typer.echo(
                f"覆盖 {first.year}年{first.month}月 ~ {last.year}年{last.month}月"
                f"({len(months)} 个月)"
            )
            peak = PlanScheduleService.peak_parallel(months)
            if peak is not None:
                typer.echo(f"最大并行 {peak[0]} 个项点({peak[1]})")
        typer.echo(f"\n预览模式,加 --yes 生成 -> {output}(已存在时自动加序号,永不覆盖)")
        return

    result = svc.generate(
        input_path,
        output,
        options,
        progress_callback=lambda c, t, m: typer.echo(f"  [{c}/{t}] {m}"),
    )
    _print_invalid(result.invalid)
    if result.success:
        assert result.output is not None
        typer.secho(f"\n完成: {len(result.items)} 个项点 -> {result.output}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"\n失败: {result.error_message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)


def _print_invalid(invalid: list[InvalidRow]) -> None:
    """预览/执行输出里标出无效行(黄色,不中断)。"""
    for inv in invalid:
        typer.secho(f"  第{inv.row}行 [无效] {inv.error}", fg=typer.colors.YELLOW)
