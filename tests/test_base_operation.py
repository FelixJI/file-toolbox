"""BaseOperationService 基类测试:验证 validate_operations 通用逻辑。

注:13/18 行为抽象方法体 `pass`,正常子类实例化后调用不会执行(子类覆写)。
本测试用一个最小具体子类覆盖 validate_operations 的真实分支:
- 空列表 → (False, "至少需要一个操作")
- 非法操作类型 → (False, "操作 N: 无效的操作类型")
- 参数校验失败 → 透传子类返回的 msg
- 全部通过 → (True, "")
"""

import pytest

from file_toolbox.common.base_operation import BaseOperationService


class _StubService(BaseOperationService):
    """最小具体子类:get_operation_types 固定返回 ['rename'],
    _validate_params 仅在 operation['params'] 不含 'rename_map' 时失败。"""

    def get_operation_types(self) -> list[str]:
        return ["rename"]

    def _validate_params(self, operation, index):
        if "rename_map" not in operation.get("params", {}):
            return False, f"操作 {index + 1}: 缺少 rename_map"
        return True, ""


def test_cannot_instantiate_abstract_base():
    """基类含未实现的抽象方法,直接实例化应抛 TypeError。"""
    with pytest.raises(TypeError):
        BaseOperationService()  # type: ignore[abstract]


def test_validate_operations_empty_list():
    """空操作列表 → (False, '至少需要一个操作')。"""
    svc = _StubService()
    valid, msg = svc.validate_operations([])
    assert valid is False
    assert msg == "至少需要一个操作"


def test_validate_operations_invalid_type():
    """非法操作类型 → (False, '操作 N: 无效的操作类型')。"""
    svc = _StubService()
    valid, msg = svc.validate_operations([{"type": "unknown"}])
    assert valid is False
    assert msg == "操作 1: 无效的操作类型"


def test_validate_operations_param_failure():
    """操作类型合法但参数校验失败 → 透传子类的 msg。"""
    svc = _StubService()
    valid, msg = svc.validate_operations([{"type": "rename", "params": {}}])
    assert valid is False
    assert msg == "操作 1: 缺少 rename_map"


def test_validate_operations_all_pass():
    """操作类型与参数均合法 → (True, '')。"""
    svc = _StubService()
    valid, msg = svc.validate_operations([{"type": "rename", "params": {"rename_map": {"a": "b"}}}])
    assert valid is True
    assert msg == ""


def test_validate_operations_reports_correct_index_in_multi_op_message():
    """多操作列表中第 2 个非法 → 错误消息索引为 N+1。"""
    svc = _StubService()
    valid, msg = svc.validate_operations(
        [
            {"type": "rename", "params": {"rename_map": {"a": "b"}}},
            {"type": "rename", "params": {}},  # 第 2 个缺参数
        ]
    )
    assert valid is False
    assert msg == "操作 2: 缺少 rename_map"
