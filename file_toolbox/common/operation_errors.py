"""历史保存失败仍携带已经完成的业务结果,由调用方决定如何呈现。"""

from collections.abc import Iterator
from contextlib import contextmanager


class HistorySaveError[T](RuntimeError):
    def __init__(self, result: T, error: Exception) -> None:
        super().__init__(f"历史保存失败:{error}")
        self.result = result


@contextmanager
def preserve_history_result[T](result: T) -> Iterator[None]:
    """仅包围历史写入;不把处理失败或已写出的文件伪装成回滚。"""
    try:
        yield
    except Exception as error:
        raise HistorySaveError(result, error) from error
