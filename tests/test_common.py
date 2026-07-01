import logging

from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.common.base_operation import BaseOperationService


class _FakeOp(BaseOperationService):
    def get_operation_types(self):
        return ["a"]

    def _validate_params(self, operation, index):
        return True, ""


class _Logged(LoggableMixin):
    pass


def test_base_operation_validates_empty():
    ok, msg = _FakeOp().validate_operations([])
    assert ok is False
    assert "至少需要一个操作" in msg


def test_base_operation_rejects_unknown_type():
    ok, msg = _FakeOp().validate_operations([{"type": "unknown", "params": {}}])
    assert ok is False


def test_base_operation_accepts_known_type():
    ok, msg = _FakeOp().validate_operations([{"type": "a", "params": {}}])
    assert ok is True


def test_loggable_gives_logger():
    obj = _Logged()
    assert obj.logger.name == _Logged.__module__


def test_loggable_logger_cached():
    """logger 属性应延迟初始化并缓存:多次访问返回同一 Logger 实例(而非每次新建)。"""
    obj = _Logged()
    first = obj.logger
    # 缓存对象应已落在本实例上(而非每次重新计算)
    assert getattr(obj, "_logger", None) is first
    assert isinstance(first, logging.Logger)
    # 多次访问保持同一对象
    assert obj.logger is first is obj.logger
