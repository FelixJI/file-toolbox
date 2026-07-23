"""MkdirController —— 把建文件夹 Tab 的结构收集、校验、历史记录从 Qt 依赖中抽离。

Controller 不 import PySide6,仅依赖 core.batch_mkdir;View 读取 QTableWidget
得到 list[list[str]] 后传入,逻辑可无 Qt 单测。
"""

from __future__ import annotations

from file_toolbox.core.batch_mkdir import ConflictStrategy, FolderCreatorService


class MkdirController:
    """建文件夹 Tab 的业务编排(纯 Python)。

    - collect_structures:从粘贴表读取的二维文本构建层级结构元组。
    - find_invalid_names:找出含非法字符的文件夹名。
    - build_history_record:构造 history 记录 dict(strategy 以 enum 名存储)。
    """

    def __init__(self, svc: FolderCreatorService | None = None):
        self._svc = svc or FolderCreatorService()

    def collect_structures(self, rows: list[list[str]]) -> list[tuple[str, ...]]:
        """从粘贴表的二维文本(每行一个 list[cell_text])构建层级结构。

        与原 mkdir_tab._collect_structures 行为一致:逐格 strip,非空才收集;
        整行无非空单元格则跳过该行。
        """
        structures: list[tuple[str, ...]] = []
        for cells in rows:
            parts: list[str] = []
            for cell in cells:
                text = cell.strip()
                if text:
                    parts.append(text)
            if parts:
                structures.append(tuple(parts))
        return structures

    def find_invalid_names(self, structures: list[tuple[str, ...]]) -> list[str]:
        """返回含非法字符的文件夹名,去重且保持顺序。"""
        invalid: list[str] = []
        for levels in structures:
            for name in levels:
                if not self._svc.validate_folder_name(name) and name not in invalid:
                    invalid.append(name)
        return invalid

    def build_history_record(
        self,
        root,
        structure_count: int,
        strategy: ConflictStrategy,
        created: int,
        skipped: int,
        success: bool,
    ) -> dict:
        """构造 mkdir 操作的历史记录 dict(与原 _create_folders 内联 dict 一致)。

        注意:strategy 以 strategy.name(枚举名字符串)存储。
        """
        return {
            "root": str(root),
            "structure_count": structure_count,
            "strategy": strategy.name,
            "created": created,
            "skipped": skipped,
            "success": success,
        }
