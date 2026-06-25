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
    obj = _Logged()
    assert obj.logger is obj.logger
