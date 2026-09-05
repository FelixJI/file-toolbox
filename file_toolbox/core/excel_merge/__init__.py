"""Excel 合并:多个工作簿的工作表合并为一个新工作簿(纯 openpyxl,跨平台)。"""

from file_toolbox.core.excel_merge.constants import (
    DEFAULT_OUTPUT_NAME,
    MODE_FORMULAS,
    MODE_VALUES,
    NAMING_KEEP,
    NAMING_PREFIX,
    SUPPORTED_MODES,
    SUPPORTED_NAMING,
    SUPPORTED_SUFFIXES,
)
from file_toolbox.core.excel_merge.naming import (
    SHEET_NAME_MAX_LEN,
    SheetNamer,
    compose_sheet_base,
    sanitize_sheet_name,
)
from file_toolbox.core.excel_merge.service import ExcelMergeService
from file_toolbox.core.excel_merge.types import (
    FailedSource,
    MergedSheet,
    MergeOptions,
    MergeResult,
    SheetPlan,
)

__all__ = [
    "DEFAULT_OUTPUT_NAME",
    "MODE_FORMULAS",
    "MODE_VALUES",
    "NAMING_KEEP",
    "NAMING_PREFIX",
    "SUPPORTED_MODES",
    "SUPPORTED_NAMING",
    "SUPPORTED_SUFFIXES",
    "SHEET_NAME_MAX_LEN",
    "ExcelMergeService",
    "SheetNamer",
    "compose_sheet_base",
    "sanitize_sheet_name",
    "FailedSource",
    "MergeOptions",
    "MergeResult",
    "MergedSheet",
    "SheetPlan",
]
