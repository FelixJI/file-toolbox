"""批量文件重命名核心逻辑。支持 7 种操作组合,预览-执行两段式。"""

import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from file_toolbox.common.base_operation import BaseOperationService
from file_toolbox.common.file_utils import get_file_info
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.common.op_schema import ParamRule, validate_params
from file_toolbox.core.rename_execution import (
    PlanEntry,
    PlanState,
    RenameResult,
    execute,
    plan_mapping,
    undo_record,
)


class OperationType(Enum):
    """操作类型枚举"""

    ADD_PREFIX = "add_prefix"  # 添加前缀
    ADD_SUFFIX = "add_suffix"  # 添加后缀
    REPLACE_TEXT = "replace_text"  # 替换文本
    REGEX_REPLACE = "regex_replace"  # 正则替换
    ADD_NUMBER = "add_number"  # 添加序号
    DELETE_CHARS = "delete_chars"  # 删除字符
    ADD_DATE = "add_date"  # 添加日期


def _validate_add_number(operation: dict[str, Any], index: int) -> tuple[bool, str]:
    """add_number 的自定义校验:位数>=1、custom 格式含 {n} 占位符。"""
    params: dict[str, Any] = operation.get("params", {})
    n = index + 1
    try:
        for key, default in (("start", 1), ("digits", 3)):
            value = params.get(key, default)
            if not isinstance(value, (str, int)):
                raise TypeError("序号参数需要整数")
            params[key] = int(value)
        digits = params["digits"]
        if digits < 1:
            return False, f"操作 {n}: 序号位数必须大于0"

        if params.get("format", "bracket") == "custom":
            custom_template = params.get("custom_template", "")
            if not custom_template:
                return False, f"操作 {n}: 自定义格式模板不能为空"
            if "{n}" not in custom_template:
                return False, f"操作 {n}: 自定义格式必须包含 {{n}} 作为序号占位符"
    except (TypeError, ValueError):
        return False, f"操作 {n}: 序号参数必须是数字"
    return True, ""


# 参数校验规则表(声明式,由 FileRenameService._validate_params 复用)。
# 简单类型由通用规则覆盖;add_number 的复合校验通过 extra 委托。
RENAME_PARAM_RULES: dict[str, ParamRule] = {
    OperationType.ADD_PREFIX.value: ParamRule(
        required=("text",), empty_messages={"text": "前缀不能为空"}, string_keys=("text",)
    ),
    OperationType.ADD_SUFFIX.value: ParamRule(
        required=("text",), empty_messages={"text": "后缀不能为空"}, string_keys=("text",)
    ),
    OperationType.REPLACE_TEXT.value: ParamRule(
        required=("find",),
        empty_messages={"find": "查找文本不能为空"},
        string_keys=("find", "replace"),
        bool_keys=("case_sensitive",),
    ),
    OperationType.REGEX_REPLACE.value: ParamRule(
        required=("pattern",),
        empty_messages={"pattern": "正则表达式不能为空"},
        regex_key="pattern",
        string_keys=("pattern", "replace"),
        bool_keys=("ignore_case",),
    ),
    OperationType.ADD_NUMBER.value: ParamRule(
        string_keys=("format", "custom_template", "position"), extra=_validate_add_number
    ),
    OperationType.DELETE_CHARS.value: ParamRule(
        required=("value",), empty_messages={"value": "删除值不能为空"}, string_keys=("value",)
    ),
    OperationType.ADD_DATE.value: ParamRule(string_keys=("format", "position", "source")),
}


class FileRenameService(BaseOperationService):
    """文件重命名服务"""

    def __init__(self, history_store: JsonHistoryStore | None = None) -> None:
        """初始化。

        Args:
            history_store: 历史存储;传入则在 execute_rename 成功后记录一条 rename
                历史(形状与原 GUI 内联写入完全一致)。None 表示不记录(默认,
                保证无历史依赖的旧调用零副作用)。
        """
        self._history_store = history_store

    def get_operation_types(self) -> list[str]:
        """获取支持的操作类型列表"""
        return [t.value for t in OperationType]

    def _validate_params(self, operation: dict[str, Any], index: int) -> tuple[bool, str]:
        """验证操作参数(委托给共享的声明式规则表)。"""
        return validate_params(operation, index, RENAME_PARAM_RULES)

    def apply_operations(
        self, files: list[Path], operations: list[dict[str, Any]]
    ) -> dict[Path, tuple[Path, str]]:
        """
        应用重命名操作

        Args:
            files: 文件路径列表
            operations: 操作列表，格式: [{"type": "add_prefix", "params": {...}}, ...]

        Returns:
            字典: {原路径: (新路径, 状态消息)}
        """
        return {
            old: (entry.target, entry.message)
            for old, entry in self.plan_operations(files, operations).items()
        }

    def plan_operations(
        self, files: list[Path], operations: list[dict[str, Any]]
    ) -> dict[Path, PlanEntry]:
        """核心计划状态决定可执行项,中文消息只用于展示。"""
        mapping: dict[Path, Path] = {}
        errors: dict[Path, PlanEntry] = {}
        for idx, file_path in enumerate(files):
            try:
                name = file_path.stem
                for operation in operations:
                    name = self._apply_single_operation(
                        name, file_path.suffix, operation, idx, len(files), file_path
                    )
                if not name or any(c in name for c in "\\/\x00"):
                    raise ValueError("输出必须是非空文件名,不能包含路径")
                mapping[file_path] = file_path.parent / (name + file_path.suffix)
            except Exception as exc:
                errors[file_path] = PlanEntry(file_path, PlanState.INVALID, str(exc))
        plan = plan_mapping(mapping)
        plan.update(errors)
        return {path: plan[path] for path in files}

    def _apply_single_operation(
        self,
        name: str,
        extension: str,
        operation: dict[str, Any],
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
        params: dict[str, Any] = operation.get("params", {})

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

    def _add_prefix(self, name: str, params: dict[str, Any]) -> str:
        """添加前缀"""
        prefix: str = params.get("text", "")
        return prefix + name

    def _add_suffix(self, name: str, params: dict[str, Any]) -> str:
        """添加后缀"""
        suffix: str = params.get("text", "")
        return name + suffix

    def _replace_text(self, name: str, params: dict[str, Any]) -> str:
        """替换文本"""
        find_text: str = params.get("find", "")
        replace_text: str = params.get("replace", "")
        case_sensitive: bool = params.get("case_sensitive", False)

        if not find_text:
            return name

        if case_sensitive:
            return name.replace(find_text, replace_text)
        else:
            # 不区分大小写的替换。
            # 注意:不能用 pattern.sub(replace_text, name) —— re 会把 replacement 当
            # 模板解释,replace 含 \d / \1 等会抛 re.error('bad escape') 或误当反向引用,
            # 与区分大小写分支(str.replace 视为字面量)语义不一致。用 lambda 包裹使
            # replacement 作为字面文本返回,与 str.replace 行为对齐。
            pattern = re.compile(re.escape(find_text), re.IGNORECASE)
            return pattern.sub(lambda _m: replace_text, name)

    def _regex_replace(self, name: str, params: dict[str, Any]) -> str:
        """正则表达式替换"""
        pattern: str = params.get("pattern", "")
        replace: str = params.get("replace", "")
        ignore_case: bool = params.get("ignore_case", False)

        if not pattern:
            return name

        try:
            flags = re.IGNORECASE if ignore_case else 0
            return re.sub(pattern, replace, name, flags=flags)
        except re.error:
            # 正则表达式错误，返回原名
            return name

    def _add_number(self, name: str, params: dict[str, Any], index: int) -> str:
        """
        添加序号

        Args:
            name: 文件名
            params: 参数配置
            index: 当前索引
        """
        start: int = params.get("start", 1)
        digits: int = params.get("digits", 3)
        position: str = params.get("position", "end")  # start/end/before_ext
        format_type: str = params.get(
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

    def _add_date(self, name: str, params: dict[str, Any], file_path: Path | None = None) -> str:
        """添加日期"""
        date_format: str = params.get("format", "%Y%m%d")
        position: str = params.get("position", "end")
        source: str = params.get("source", "current")

        date_str = datetime.now().strftime(date_format)
        if source == "file" and file_path:
            # exists()/stat() 均可能抛异常(竞态:文件被删/无权限/网络盘抖动),
            # 任何异常都回退到 now()。与 file_utils.get_file_info 同款 try 包裹。
            try:
                if file_path.exists():
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    date_str = mtime.strftime(date_format)
            except Exception:
                pass  # date_str 已是 now(),保持回退

        if position == "start":
            return date_str + name
        else:
            return name + date_str

    def _delete_chars(self, name: str, params: dict[str, Any]) -> str:
        """删除字符"""
        delete_type: str = params.get("delete_type", "prefix")  # prefix/suffix/text
        value: str = params.get("value", "")

        if delete_type == "prefix":
            # 删除前N个字符
            try:
                count = int(value)
                # 负数对「删除前 N 个字符」无意义:name[count:] 对负数会反向取尾部,
                # 语义反转("ABCDE" 删 -2 误返回 "DE")。与 suffix 分支一致,负数视为无效。
                if count < 0:
                    return name
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

    def execute_rename_result(self, rename_map: dict[Path, Path]) -> RenameResult:
        """返回实际成功映射、逐项错误和独立的历史保存错误。"""
        return execute(rename_map, self._history_store)

    def execute_rename(self, rename_map: dict[Path, Path]) -> tuple[int, list[str]]:
        """旧接口薄适配;计数只包含真实成功操作。"""
        result = self.execute_rename_result(rename_map)
        return result.count, result.messages

    def undo_record(self, record_id: int) -> RenameResult:
        """由核心校验记录并恢复;GUI 不自行反转映射或标记成功。"""
        if self._history_store is None:
            return RenameResult(errors=["未配置历史存储"])
        try:
            return undo_record(self._history_store, record_id)
        except (OSError, ValueError, TimeoutError) as exc:
            return RenameResult(errors=[f"未能读取/锁定撤销记录: {exc}"])

    def get_file_info(self, file_path: Path) -> dict[str, Any]:
        """获取文件信息(委托给通用工具,保持单一实现)。"""
        return get_file_info(file_path)
