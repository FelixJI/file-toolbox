"""GUI 对话框/Tab。

再导出按需解析(PEP 562 module __getattr__):导入任一子模块都会先执行本
__init__,若此处顶层导入全部 Tab,则 dialogs 包的重依赖(pypdfium2/pypdf/
chardet/cattrs,~440ms dev)会随首个被导入的 Tab 进入启动链。类型检查仍能
看到真实类(TYPE_CHECKING 导入),运行时首次访问属性才加载对应子模块。
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .about_tab import AboutTab
    from .attendance_tab import AttendanceTab
    from .history_dialog import HistoryDialog
    from .invoice_tab import InvoiceTab
    from .mkdir_tab import BatchFolderCreatorDialog
    from .pdf_tab import PDFGeneratorDialog
    from .rename_tab import FileRenamerDialog
    from .replace_tab import ContentReplaceDialog

__all__ = [
    "FileRenamerDialog",
    "BatchFolderCreatorDialog",
    "PDFGeneratorDialog",
    "ContentReplaceDialog",
    "HistoryDialog",
    "InvoiceTab",
    "AboutTab",
    "AttendanceTab",
]

# 属性名 -> 子模块名(不含包前缀)。
_LAZY_ATTRS: dict[str, str] = {
    "AboutTab": "about_tab",
    "AttendanceTab": "attendance_tab",
    "HistoryDialog": "history_dialog",
    "InvoiceTab": "invoice_tab",
    "BatchFolderCreatorDialog": "mkdir_tab",
    "PDFGeneratorDialog": "pdf_tab",
    "FileRenamerDialog": "rename_tab",
    "ContentReplaceDialog": "replace_tab",
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY_ATTRS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(f".{module_name}", __package__), name)
    globals()[name] = value  # 缓存到模块全局,后续访问不再触发 __getattr__
    return value
