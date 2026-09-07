"""PDF 排序数据类型(纯数据,不依赖 pypdf/Qt,便于单测)。"""

from dataclasses import dataclass, field
from pathlib import Path

from file_toolbox.core.pdf_sort.constants import ORDER_ASC, UNMATCHED_LAST


@dataclass(frozen=True)
class SortOptions:
    """排序选项(与 CLI 参数 / GUI 控件一一对应)。"""

    pattern: str
    order: str = ORDER_ASC
    unmatched: str = UNMATCHED_LAST


@dataclass(frozen=True)
class PagePlan:
    """一页的排序计划。

    page 为 0 基原始页码;new_index 为排序后的 0 基位置,
    order 为 None(不排序)时为 -1;未匹配页 key 为空、matched=False。
    """

    page: int
    key: str
    matched: bool
    new_index: int = -1
    note: str = ""


@dataclass(frozen=True)
class FilePlan:
    """一个 PDF 的排序计划。

    order 为新页序(原页索引);None 表示不会排序
    (没有任何页匹配,或 fail 策略命中未匹配页),note 给出原因。
    """

    file: str
    pages: list[PagePlan] = field(default_factory=list)
    order: list[int] | None = None
    note: str = ""


@dataclass(frozen=True)
class SortedFile:
    """已处理的一个 PDF。

    output 为 None 表示顺序未变、未写出输出(note 说明);
    写出失败不会出现此处,而是进入 FailedFile。
    """

    file: str
    output: Path | None
    pages: list[PagePlan] = field(default_factory=list)
    note: str = ""


@dataclass(frozen=True)
class FailedFile:
    """处理失败的源文件(损坏/加密/全部未匹配/fail 策略),不中断其余文件。"""

    file: str
    error: str


@dataclass
class SortResult:
    """排序执行结果。

    至少一个文件被处理(含顺序未变)即视为 success;
    全部失败/取消时 sorted_files 为空。
    """

    sorted_files: list[SortedFile] = field(default_factory=list)
    failed: list[FailedFile] = field(default_factory=list)
    cancelled: bool = False
    error_message: str = ""

    @property
    def success(self) -> bool:
        """有文件被处理即成功(允许部分文件失败)。"""
        return bool(self.sorted_files) and not self.cancelled

    @property
    def written_count(self) -> int:
        """实际写出输出的文件数(顺序未变不计)。"""
        return sum(1 for f in self.sorted_files if f.output is not None)
