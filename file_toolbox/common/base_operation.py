"""操作服务基类 - 提供通用的操作验证逻辑。"""

from abc import ABC, abstractmethod


class BaseOperationService(ABC):
    """操作服务抽象基类。"""

    @abstractmethod
    def get_operation_types(self) -> list[str]:
        """获取支持的操作类型列表。"""
        pass

    @abstractmethod
    def _validate_params(self, operation: dict, index: int) -> tuple[bool, str]:
        """验证操作参数（子类实现）。"""
        pass

    def validate_operations(self, operations: list[dict]) -> tuple[bool, str]:
        """
        验证操作列表。

        Args:
            operations: 操作列表

        Returns:
            (是否有效, 错误消息)
        """
        if not operations:
            return False, "至少需要一个操作"

        for idx, operation in enumerate(operations):
            op_type = operation.get("type")
            if op_type not in self.get_operation_types():
                return False, f"操作 {idx + 1}: 无效的操作类型"

            valid, msg = self._validate_params(operation, idx)
            if not valid:
                return False, msg

        return True, ""
