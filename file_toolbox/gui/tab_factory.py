"""GUI 懒工厂:按工具登记的模块/类名实例化页面(唯一 GUI 构造适配点)。

登记(common/tool_registry.py)只保存模块/类名字符串;真正的 GUI 导入发生
在本函数被调用(首次切页触发懒构造)时,保证纯登记/metadata/CLI 的导入链
不触碰任何 Qt/GUI 模块。新增普通工具无需在此添加分支。
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, cast

from file_toolbox.common.tool_registry import ToolSpec

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


def create_tab(spec: ToolSpec) -> QWidget:
    """按登记的 gui_module/gui_class 懒导入并构造页面实例。"""
    module = importlib.import_module(spec.gui_module)
    tab_class = cast("type[QWidget]", getattr(module, spec.gui_class))
    return tab_class()
