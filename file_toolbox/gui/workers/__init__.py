"""后台工作线程(QThread)集合。

包级名称按需解析(PEP 562 ``__getattr__``):导入任一 worker 子模块或包级
名称不再连带拉起其余 worker 的依赖链(attendance→cattrs、pdf_sort→pypdf 等),
否则首个被打开的功能页要为整个集合预付冷导入成本(Issue #124)。
``from file_toolbox.gui.workers import X`` 的既有用法与静态类型(TYPE_CHECKING)
保持不变。
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .attendance_worker import AttendanceWorker
    from .excel_merge_worker import ExcelMergeWorker
    from .invoice_worker import InvoiceParseWorker
    from .pdf_sort_worker import PdfSortWorker
    from .pdf_worker import PdfGenerateWorker

__all__ = [
    "AttendanceWorker",
    "ExcelMergeWorker",
    "InvoiceParseWorker",
    "PdfGenerateWorker",
    "PdfSortWorker",
]

_WORKER_MODULES = {
    "AttendanceWorker": "attendance_worker",
    "ExcelMergeWorker": "excel_merge_worker",
    "InvoiceParseWorker": "invoice_worker",
    "PdfGenerateWorker": "pdf_worker",
    "PdfSortWorker": "pdf_sort_worker",
}


def __getattr__(name: str) -> Any:
    if name in _WORKER_MODULES:
        import importlib

        module = importlib.import_module(f".{_WORKER_MODULES[name]}", __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
