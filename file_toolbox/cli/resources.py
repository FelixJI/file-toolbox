"""CLI 所有者在每条退出路径释放服务,保留原始处理异常。"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import typer


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
        close()
