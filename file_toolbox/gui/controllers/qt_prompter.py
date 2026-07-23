"""基于 QInputDialog 的 Prompter 实现(供 rename/replace View 共用)。

把 Prompter protocol 映射到 PySide6 的 QInputDialog;取消时抛 PromptCancelled。
"""

from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QWidget

from file_toolbox.gui.controllers.operation_params import PromptCancelled


class QInputDialogPrompter:
    """Prompter 的 QInputDialog 实现。parent 用于弹窗的模态父控件。"""

    def __init__(self, parent: QWidget | None = None):
        self._parent = parent

    def get_text(self, title: str, label: str, text: str = "") -> str:
        result, ok = QInputDialog.getText(self._parent, title, label, text=text)
        if not ok:
            raise PromptCancelled
        return result

    def get_int(
        self, title: str, label: str, value: int = 0, minimum: int = 0, maximum: int = 99
    ) -> int:
        result, ok = QInputDialog.getInt(
            self._parent, title, label, value=value, minimum=minimum, maximum=maximum
        )
        if not ok:
            raise PromptCancelled
        return result

    def get_item(
        self, title: str, label: str, items: list[str], current: int = 0, editable: bool = False
    ) -> str:
        result, ok = QInputDialog.getItem(
            self._parent, title, label, items, current, editable=editable
        )
        if not ok:
            raise PromptCancelled
        return result
