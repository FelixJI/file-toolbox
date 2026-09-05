"""GUI controller 层:把 Tab 的业务编排从 Qt 依赖中抽离,可无 Qt 单测。

再导出按需解析(PEP 562 module __getattr__):导入任一子模块都会先执行本
__init__,若此处顶层导入全部控制器,则 pdf_controller(core.batch_pdf →
pypdfium2/pypdf)与 replace_controller(core.batch_replace → chardet)会随
首屏 Tab 进入启动链。类型检查仍能看到真实类(TYPE_CHECKING 导入)。
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from file_toolbox.gui.controllers.excel_merge_controller import ExcelMergeController
    from file_toolbox.gui.controllers.invoice_controller import InvoiceController
    from file_toolbox.gui.controllers.mkdir_controller import MkdirController
    from file_toolbox.gui.controllers.pdf_controller import PDFConfigState, PDFController
    from file_toolbox.gui.controllers.rename_controller import RenameController
    from file_toolbox.gui.controllers.replace_controller import ReplaceController

__all__ = [
    "ExcelMergeController",
    "InvoiceController",
    "MkdirController",
    "PDFConfigState",
    "PDFController",
    "RenameController",
    "ReplaceController",
]

# 属性名 -> (子模块名, 子模块内属性名)。
_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "ExcelMergeController": ("excel_merge_controller", "ExcelMergeController"),
    "InvoiceController": ("invoice_controller", "InvoiceController"),
    "MkdirController": ("mkdir_controller", "MkdirController"),
    "PDFConfigState": ("pdf_controller", "PDFConfigState"),
    "PDFController": ("pdf_controller", "PDFController"),
    "RenameController": ("rename_controller", "RenameController"),
    "ReplaceController": ("replace_controller", "ReplaceController"),
}


def __getattr__(name: str) -> Any:
    entry = _LAZY_ATTRS.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module_name, attr = entry
    value = getattr(import_module(f".{module_name}", __package__), attr)
    globals()[name] = value  # 缓存到模块全局,后续访问不再触发 __getattr__
    return value
