"""操作失败仍携带已经完成的业务结果,由调用方决定如何呈现。"""

from collections.abc import Iterator
from contextlib import contextmanager


class OperationResultError[T](RuntimeError):
    def __init__(self, result: T, message: str) -> None:
        super().__init__(message)
        self.result = result


class HistorySaveError[T](OperationResultError[T]):
    def __init__(self, result: T, error: Exception) -> None:
        super().__init__(result, f"历史保存失败:{error}")


@contextmanager
def preserve_history_result[T](result: T) -> Iterator[None]:
    """仅包围历史写入;不把处理失败或已写出的文件伪装成回滚。"""
    try:
        yield
    except Exception as error:
        raise HistorySaveError(result, error) from error
