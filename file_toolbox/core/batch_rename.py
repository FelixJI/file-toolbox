"""批量文件重命名核心逻辑。支持 7 种操作组合,预览-执行两段式。"""

import re
from datetime import datetime
from enum import Enum
from pathlib import Path

from file_toolbox.common.base_operation import BaseOperationService
from file_toolbox.common.file_utils import get_file_info
from file_toolbox.common.op_schema import ParamRule, validate_params


class OperationType(Enum):
    """操作类型枚举"""

    ADD_PREFIX = "add_prefix"  # 添加前缀
    ADD_SUFFIX = "add_suffix"  # 添加后缀
    REPLACE_TEXT = "replace_text"  # 替换文本
    REGEX_REPLACE = "regex_replace"  # 正则替换
    ADD_NUMBER = "add_number"  # 添加序号
    DELETE_CHARS = "delete_chars"  # 删除字符
    ADD_DATE = "add_date"  # 添加日期


def _validate_add_number(operation: dict, index: int) -> tuple[bool, str]:
    """add_number 的自定义校验:位数>=1、custom 格式含 {n} 占位符。"""
    params = operation.get("params", {})
    n = index + 1
    try:
        int(params.get("start", 1))  # 验证参数有效性
        digits = int(params.get("digits", 3))
        if digits < 1:
            return False, f"操作 {n}: 序号位数必须大于0"

        if params.get("format", "bracket") == "custom":
            custom_template = params.get("custom_template", "")
            if not custom_template:
                return False, f"操作 {n}: 自定义格式模板不能为空"
            if "{n}" not in custom_template:
                return False, f"操作 {n}: 自定义格式必须包含 {{n}} 作为序号占位符"
    except ValueError:
        return False, f"操作 {n}: 序号参数必须是数字"
    return True, ""


# 参数校验规则表(声明式,由 FileRenameService._validate_params 复用)。
# 简单类型由通用规则覆盖;add_number 的复合校验通过 extra 委托。
RENAME_PARAM_RULES: dict[str, ParamRule] = {
    OperationType.ADD_PREFIX.value: ParamRule(
        required=("text",), empty_messages={"text": "前缀不能为空"}
    ),
    OperationType.ADD_SUFFIX.value: ParamRule(
        required=("text",), empty_messages={"text": "后缀不能为空"}
    ),
    OperationType.REPLACE_TEXT.value: ParamRule(
        required=("find",), empty_messages={"find": "查找文本不能为空"}
    ),
    OperationType.REGEX_REPLACE.value: ParamRule(
        required=("pattern",),
        empty_messages={"pattern": "正则表达式不能为空"},
        regex_key="pattern",
    ),
    OperationType.ADD_NUMBER.value: ParamRule(extra=_validate_add_number),
    OperationType.DELETE_CHARS.value: ParamRule(
        required=("value",), empty_messages={"value": "删除值不能为空"}
    ),
    # ADD_DATE 无强制必填字段(格式有默认值)
}


class FileRenameService(BaseOperationService):
    """文件重命名服务"""

    def get_operation_types(self) -> list[str]:
        """获取支持的操作类型列表"""
        return [t.value for t in OperationType]

    def _validate_params(self, operation: dict, index: int) -> tuple[bool, str]:
        """验证操作参数(委托给共享的声明式规则表)。"""
        return validate_params(operation, index, RENAME_PARAM_RULES)

    def apply_operations(
        self, files: list[Path], operations: list[dict]
    ) -> dict[Path, tuple[Path, str]]:
        """
        应用重命名操作

        Args:
            files: 文件路径列表
            operations: 操作列表，格式: [{"type": "add_prefix", "params": {...}}, ...]

        Returns:
            字典: {原路径: (新路径, 状态消息)}
        """
        result = {}

        for idx, file_path in enumerate(files):
            try:
                # 获取原始文件名和扩展名
                original_name = file_path.stem
                extension = file_path.suffix
                parent = file_path.parent

                # 依次应用所有操作
                new_name = original_name
                for operation in operations:
                    new_name = self._apply_single_operation(
                        new_name, extension, operation, idx, len(files), file_path
                    )

                # 构建新路径
                new_path = parent / (new_name + extension)

                # 检查冲突
                if new_path.exists() and new_path != file_path:
                    result[file_path] = (new_path, "⚠️ 文件名冲突")
                else:
                    result[file_path] = (new_path, "✓ 准备就绪")

            except Exception as e:
                result[file_path] = (file_path, f"❌ 错误: {e!s}")

        return result

    def _apply_single_operation(
        self,
        name: str,
        extension: str,
        operation: dict,
        index: int,
        total: int,
        file_path: Path | None = None,
    ) -> str:
        """
        应用单个操作

        Args:
            name: 当前文件名（不含扩展名）
            extension: 扩展名
            operation: 操作配置
            index: 当前文件索引
            total: 文件总数
            file_path: 文件路径（用于获取文件日期）

        Returns:
            新的文件名
        """
        op_type = operation.get("type")
        params = operation.get("params", {})

        if op_type == OperationType.ADD_PREFIX.value:
            return self._add_prefix(name, params)

        elif op_type == OperationType.ADD_SUFFIX.value:
            return self._add_suffix(name, params)

        elif op_type == OperationType.REPLACE_TEXT.value:
            return self._replace_text(name, params)

        elif op_type == OperationType.REGEX_REPLACE.value:
            return self._regex_replace(name, params)

        elif op_type == OperationType.ADD_NUMBER.value:
            return self._add_number(name, params, index)

        elif op_type == OperationType.DELETE_CHARS.value:
            return self._delete_chars(name, params)

        elif op_type == OperationType.ADD_DATE.value:
            return self._add_date(name, params, file_path)

        return name

    def _add_prefix(self, name: str, params: dict) -> str:
        """添加前缀"""
        prefix = params.get("text", "")
        return prefix + name

    def _add_suffix(self, name: str, params: dict) -> str:
        """添加后缀"""
        suffix = params.get("text", "")
        return name + suffix

    def _replace_text(self, name: str, params: dict) -> str:
        """替换文本"""
        find_text = params.get("find", "")
        replace_text = params.get("replace", "")
        case_sensitive = params.get("case_sensitive", False)

        if not find_text:
            return name

        if case_sensitive:
            return name.replace(find_text, replace_text)
        else:
            # 不区分大小写的替换
            pattern = re.compile(re.escape(find_text), re.IGNORECASE)
            return pattern.sub(replace_text, name)

    def _regex_replace(self, name: str, params: dict) -> str:
        """正则表达式替换"""
        pattern = params.get("pattern", "")
        replace = params.get("replace", "")
        ignore_case = params.get("ignore_case", False)

        if not pattern:
            return name

        try:
            flags = re.IGNORECASE if ignore_case else 0
            return re.sub(pattern, replace, name, flags=flags)
        except re.error:
            # 正则表达式错误，返回原名
            return name

    def _add_number(self, name: str, params: dict, index: int) -> str:
        """
        添加序号

        Args:
            name: 文件名
            params: 参数配置
            index: 当前索引
        """
        start = params.get("start", 1)
        digits = params.get("digits", 3)
        position = params.get("position", "end")  # start/end/before_ext
        format_type = params.get(
            "format", "bracket"
        )  # bracket/parenthesis/underscore/dash/none/custom

        # 计算序号
        number = start + index
        number_str = str(number).zfill(digits)

        # 格式化序号
        if format_type == "bracket":
            formatted = f"[{number_str}]"
        elif format_type == "parenthesis":
            formatted = f"({number_str})"
        elif format_type == "underscore":
            formatted = f"_{number_str}"
        elif format_type == "dash":
            formatted = f"-{number_str}"
        elif format_type == "none":
            formatted = number_str
        elif format_type == "custom":
            # 自定义格式：用序号替换 {n}
            custom_template = params.get("custom_template", "{n}")
            formatted = custom_template.replace("{n}", number_str)
        else:
            formatted = number_str

        # 插入位置
        if position == "start":
            return formatted + name
        else:  # end 和 before_ext 在这里都是在文件名末尾
            return name + formatted

    def _add_date(self, name: str, params: dict, file_path: Path | None = None) -> str:
        """添加日期"""
        date_format = params.get("format", "%Y%m%d")
        position = params.get("position", "end")
        source = params.get("source", "current")

        if source == "file" and file_path and file_path.exists():
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                date_str = mtime.strftime(date_format)
            except Exception:
                date_str = datetime.now().strftime(date_format)
        else:
            date_str = datetime.now().strftime(date_format)

        if position == "start":
            return date_str + name
        else:
            return name + date_str

    def _delete_chars(self, name: str, params: dict) -> str:
        """删除字符"""
        delete_type = params.get("delete_type", "prefix")  # prefix/suffix/text
        value = params.get("value", "")

        if delete_type == "prefix":
            # 删除前N个字符
            try:
                count = int(value)
                return name[count:]
            except (ValueError, IndexError):
                return name

        elif delete_type == "suffix":
            # 删除后N个字符
            try:
                count = int(value)
                return name[:-count] if count > 0 else name
            except (ValueError, IndexError):
                return name

        elif delete_type == "text":
            # 删除指定文本
            return name.replace(value, "")

        return name

    def execute_rename(self, rename_map: dict[Path, Path]) -> tuple[int, list[str]]:
        """
        执行实际的重命名操作

        Args:
            rename_map: {原路径: 新路径}

        Returns:
            (成功数量, 失败消息列表)
        """
        success_count = 0
        errors = []

        for old_path, new_path in rename_map.items():
            try:
                # 跳过相同路径
                if old_path == new_path:
                    continue

                # 检查新路径是否已存在
                if new_path.exists():
                    errors.append(f"目标已存在: {new_path.name}")
                    continue

                # 执行重命名
                old_path.rename(new_path)
                success_count += 1

            except PermissionError:
                errors.append(f"权限不足: {old_path.name}")
            except Exception as e:
                errors.append(f"{old_path.name}: {e!s}")

        return success_count, errors

    def get_file_info(self, file_path: Path) -> dict:
        """获取文件信息(委托给通用工具,保持单一实现)。"""
        return get_file_info(file_path)

