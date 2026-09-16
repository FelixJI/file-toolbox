"""CLI 所有者在每条退出路径释放服务,保留原始处理异常。"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import cast

import typer

from file_toolbox.common.operation_errors import HistorySaveError


@contextmanager
def close_on_exit(close: Callable[[], None]) -> Iterator[None]:
    """已有异常时只报告收尾错误;正常路径的收尾失败继续作为失败传播。"""
    try:
        yield
    except BaseException:
        try:
            close()
        except Exception as error:
            typer.secho(f"资源释放失败:{error}", fg=typer.colors.RED, err=True)
        raise
    else:
        try:
            close()
        except Exception as error:
            typer.secho(f"资源释放失败:{error}", fg=typer.colors.RED, err=True)
            raise


def run_reported[T](operation: Callable[[], T]) -> tuple[T, bool]:
    """历史异常携带的结果与原调用返回类型相同;报告失败后仍供 CLI 汇总。"""
    try:
        return operation(), False
    except HistorySaveError as error:
        typer.secho(str(error), fg=typer.colors.RED, err=True)
        return cast(T, error.result), True
