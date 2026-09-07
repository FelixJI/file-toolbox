"""PDF 排序:按文字层匹配每页排序键,重排页面写出新 PDF(纯 pypdf,跨平台)。"""

from file_toolbox.core.pdf_sort.constants import (
    ORDER_ASC,
    ORDER_DESC,
    SORTED_MARKER,
    SUPPORTED_ORDERS,
    SUPPORTED_SUFFIXES,
    SUPPORTED_UNMATCHED,
    UNMATCHED_FAIL,
    UNMATCHED_FIRST,
    UNMATCHED_LAST,
)
from file_toolbox.core.pdf_sort.keys import (
    compile_pattern,
    compute_order,
    extract_key,
    natural_key,
)
from file_toolbox.core.pdf_sort.service import PdfSortService
from file_toolbox.core.pdf_sort.types import (
    FailedFile,
    FilePlan,
    PagePlan,
    SortedFile,
    SortOptions,
    SortResult,
)

__all__ = [
    "ORDER_ASC",
    "ORDER_DESC",
    "SORTED_MARKER",
    "SUPPORTED_ORDERS",
    "SUPPORTED_SUFFIXES",
    "SUPPORTED_UNMATCHED",
    "UNMATCHED_FAIL",
    "UNMATCHED_FIRST",
    "UNMATCHED_LAST",
    "PdfSortService",
    "compile_pattern",
    "compute_order",
    "extract_key",
    "natural_key",
    "FailedFile",
    "FilePlan",
    "PagePlan",
    "SortedFile",
    "SortOptions",
    "SortResult",
]
