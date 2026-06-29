"""updater 异常体系测试。"""

import pytest

from file_toolbox.updater.errors import (
    ChecksumMismatchError,
    NetworkError,
    ReplaceError,
    UpdateError,
)


def test_all_subclass_update_error():
    """所有更新异常必须继承 UpdateError(便于调用方一处 catch)。"""
    assert issubclass(NetworkError, UpdateError)
    assert issubclass(ChecksumMismatchError, UpdateError)
    assert issubclass(ReplaceError, UpdateError)


def test_raise_and_catch_as_base():
    """子异常能被 UpdateError 统一捕获。"""
    with pytest.raises(UpdateError):
        raise NetworkError("timeout")
    with pytest.raises(UpdateError):
        raise ChecksumMismatchError("sha mismatch")
    with pytest.raises(UpdateError):
        raise ReplaceError("move failed")


def test_message_preserved():
    err = NetworkError("conn refused")
    assert str(err) == "conn refused"
