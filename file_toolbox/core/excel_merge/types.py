"""Excel 合并数据类型(纯数据,不依赖 openpyxl/Qt,便于单测)。"""

from dataclasses import dataclass, field
from pathlib import Path

from file_toolbox.core.excel_merge.constants import MODE_VALUES, NAMING_PREFIX


@dataclass(frozen=True)
class MergeOptions:
    """合并选项(与 CLI 参数 / GUI 控件一一对应)。"""

    naming: str = NAMING_PREFIX
    mode: str = MODE_VALUES
    include_hidden: bool = False


@dataclass(frozen=True)
class SheetPlan:
    """预览计划中的一行:源工作表在输出工作簿中的去向。

    included=False 表示该工作表不会进入输出(如隐藏工作表被跳过),
    此时 target_name 为空、note 给出原因。
    """

    file: str
    sheet: str
    target_name: str
    included: bool
    note: str = ""


@dataclass(frozen=True)
class MergedSheet:
    """已合并进输出工作簿的一个工作表。"""

    file: str
    sheet: str
    target_name: str


@dataclass(frozen=True)
class FailedSource:
    """读取失败的源文件(损坏/加密/不支持的格式),不中断其余文件。"""

    file: str
    error: str


@dataclass
class MergeResult:
    """合并执行结果。

    output 已写出即视为 success(允许部分源文件失败);
    全部失败/取消时 output 为 None。
    """

    output: Path | None = None
    sheets: list[MergedSheet] = field(default_factory=list)
    failed: list[FailedSource] = field(default_factory=list)
    cancelled: bool = False
    error_message: str = ""

    @property
    def success(self) -> bool:
        """已写出输出文件即成功(部分源文件失败不影响)。"""
        return self.output is not None and not self.cancelled
