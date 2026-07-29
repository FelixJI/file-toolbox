"""批量创建文件夹核心逻辑。解析 Excel 表格数据(Tab 分隔)、构建层级、处理冲突。"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import ClassVar

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.common.loggable import LoggableMixin


class ConflictStrategy(Enum):
    """冲突处理策略"""

    SKIP = "skip"  # 跳过已存在
    MERGE = "merge"  # 合并(保留现有内容)
    CONFIRM = "confirm"  # 逐个确认


@dataclass
class FolderStructureItem:
    """文件夹结构项"""

    path: Path  # 完整路径
    levels: tuple[str, ...]  # 层级元组 (一级, 二级, 三级)
    exists: bool = False  # 是否已存在


@dataclass
class CreateResult:
    """创建结果"""

    created_count: int  # 成功创建数量
    skipped_count: int  # 跳过数量
    total_count: int  # 总数量
    success: bool  # 是否成功
    error_message: str = ""  # 错误信息


@dataclass
class ValidationResult:
    """验证结果"""

    valid: bool  # 是否有效
    folder_structure: list[tuple[str, ...]]  # 文件夹结构
    invalid_folders: list[tuple[int, str]]  # 无效文件夹 (行号, 名称)
    error_message: str = ""  # 错误信息


class FolderCreatorService(LoggableMixin):
    """文件夹创建服务"""

    # Windows不允许的文件名字符
    INVALID_CHARS: ClassVar[set[str]] = set('\\/:*?"<>|')

    def __init__(self, history_store: JsonHistoryStore | None = None) -> None:
        """初始化服务。

        Args:
            history_store: 历史存储;传入则在 create_folders 完成后记录一条 mkdir
                历史(形状与原 GUI 内联写入一致)。None 表示不记录(默认)。
        """
        self._history_store = history_store
        self.logger.info("FolderCreatorService 初始化完成")

    # ==================== 数据解析 ====================

    def parse_excel_table_data(self, text: str) -> ValidationResult:
        """
        解析Excel表格数据

        Args:
            text: 从Excel粘贴的文本(Tab分隔)

        Returns:
            ValidationResult: 验证结果
        """
        try:
            # 验证格式
            if not text.strip():
                return ValidationResult(
                    valid=False,
                    folder_structure=[],
                    invalid_folders=[],
                    error_message="请粘贴从Excel复制的表格数据",
                )

            if "\t" not in text:
                return ValidationResult(
                    valid=False,
                    folder_structure=[],
                    invalid_folders=[],
                    error_message="粘贴的内容不是有效的Excel表格数据（缺少Tab分隔符）",
                )

            # 解析数据
            lines = text.strip().split("\n")
            folder_structure = []
            invalid_folders = []
            prev_row: list[str] = []  # 上一行的非空值

            for line_num, line in enumerate(lines, start=1):
                if not line.strip():
                    continue

                # 按Tab分隔
                cells = line.split("\t")
                current_row = []

                # 处理每个单元格
                for i, cell in enumerate(cells):
                    cell = cell.strip()
                    if cell:
                        # 检查特殊字符
                        if any(char in self.INVALID_CHARS for char in cell):
                            invalid_folders.append((line_num, cell))
                        current_row.append(cell)
                    else:
                        # 空单元格，继承上一行
                        if i < len(prev_row):
                            current_row.append(prev_row[i])
                        else:
                            # 如果上一行也没有值，则停止
                            break

                # 保存当前行作为下一行的参考
                if current_row:
                    folder_structure.append(tuple(current_row))
                    prev_row = current_row

            # 验证结果
            if not folder_structure:  # pragma: no cover
                # 防御性兜底:text.strip() 非空 → 至少一行非空 → 至少首单元格非空
                # → current_row 非空 → folder_structure 非空。此分支理论不可达。
                return ValidationResult(
                    valid=False,
                    folder_structure=[],
                    invalid_folders=invalid_folders,
                    error_message="未找到有效的文件夹结构数据",
                )

            return ValidationResult(
                valid=True,
                folder_structure=folder_structure,
                invalid_folders=invalid_folders,
                error_message="",
            )

        except Exception as e:
            self.logger.error(f"解析表格数据失败: {e}")
            return ValidationResult(
                valid=False,
                folder_structure=[],
                invalid_folders=[],
                error_message=f"解析表格数据时出错: {e!s}",
            )

    # ==================== 路径构建 ====================

    def build_folder_paths(
        self, root_path: Path, folder_structure: list[tuple[str, ...]]
    ) -> list[FolderStructureItem]:
        """
        根据文件夹结构构建完整的文件夹路径列表

        Args:
            root_path: 根目录
            folder_structure: 文件夹结构列表

        Returns:
            文件夹结构项列表
        """
        if not root_path or not folder_structure:
            return []

        items = []
        for structure in folder_structure:
            path = root_path
            for folder_name in structure:
                path = path / folder_name

            items.append(FolderStructureItem(path=path, levels=structure, exists=path.exists()))

        return items

    # ==================== 文件夹检查 ====================

    def check_existing_folders(self, items: list[FolderStructureItem]) -> set[Path]:
        """
        检查已存在的文件夹

        Args:
            items: 文件夹结构项列表

        Returns:
            已存在的文件夹路径集合
        """
        existing = set()
        for item in items:
            if item.exists:
                existing.add(item.path)
        return existing

    def count_existing_folders(self, items: list[FolderStructureItem]) -> int:
        """
        统计已存在的文件夹数量

        Args:
            items: 文件夹结构项列表

        Returns:
            已存在的文件夹数量
        """
        return sum(1 for item in items if item.exists)

    # ==================== 特殊字符处理 ====================

    def replace_special_chars(self, text: str, replacement: str = "_") -> str:
        """
        替换特殊字符

        Args:
            text: 原文本
            replacement: 替换字符(默认为下划线)

        Returns:
            替换后的文本
        """
        result = text
        for char in self.INVALID_CHARS:
            result = result.replace(char, replacement)
        return result

    def remove_special_chars(self, text: str) -> str:
        """
        删除特殊字符

        Args:
            text: 原文本

        Returns:
            删除特殊字符后的文本
        """
        result = text
        for char in self.INVALID_CHARS:
            result = result.replace(char, "")
        return result

    def validate_folder_name(self, name: str) -> bool:
        """
        验证文件夹名称是否有效

        Args:
            name: 文件夹名称

        Returns:
            是否有效
        """
        if not name or not name.strip():
            return False
        return not any(char in self.INVALID_CHARS for char in name)

    # ==================== 文件夹创建 ====================

    def create_folders(
        self,
        items: list[FolderStructureItem],
        strategy: ConflictStrategy = ConflictStrategy.MERGE,
        skip_callback: Callable[[FolderStructureItem], bool] | None = None,
        root: str | None = None,
        structure_count: int | None = None,
    ) -> CreateResult:
        """
        批量创建文件夹

        Args:
            items: 文件夹结构项列表
            strategy: 冲突处理策略
            skip_callback: 跳过回调函数(用于逐个确认), 返回True表示跳过
            root: 根目录(仅历史记录用;None 时记空串,保持旧调用兼容)
            structure_count: 结构数量(仅历史记录用;None 时记 0,保持旧调用兼容)

        Returns:
            创建结果
        """
        created_count = 0
        skipped_count = 0
        total_count = len(items)

        try:
            for item in items:
                if item.exists:
                    # 文件夹已存在
                    if strategy == ConflictStrategy.SKIP:
                        skipped_count += 1
                        self.logger.info(f"跳过已存在文件夹: {item.path}")
                    elif strategy == ConflictStrategy.CONFIRM and skip_callback:
                        # 逐个确认
                        if skip_callback(item):
                            skipped_count += 1
                        self.logger.info(f"确认处理已存在文件夹: {item.path}")
                    # strategy == MERGE: 不做任何操作
                else:
                    # 创建新文件夹
                    try:
                        item.path.mkdir(parents=True, exist_ok=True)
                        created_count += 1
                        self.logger.info(f"创建文件夹: {item.path}")
                    except Exception as e:
                        self.logger.error(f"创建文件夹失败: {item.path}, {e}")
                        result = CreateResult(
                            created_count=created_count,
                            skipped_count=skipped_count,
                            total_count=total_count,
                            success=False,
                            error_message=f"创建文件夹失败: {item.path}\n{e!s}",
                        )
                        self._record_history(root, structure_count, strategy, result)
                        return result

            result = CreateResult(
                created_count=created_count,
                skipped_count=skipped_count,
                total_count=total_count,
                success=True,
            )
            self._record_history(root, structure_count, strategy, result)
            return result

        except Exception as e:
            self.logger.error(f"批量创建文件夹失败: {e}")
            result = CreateResult(
                created_count=created_count,
                skipped_count=skipped_count,
                total_count=total_count,
                success=False,
                error_message=f"批量创建文件夹时出错: {e!s}",
            )
            self._record_history(root, structure_count, strategy, result)
            return result

    def _record_history(
        self,
        root: str | None,
        structure_count: int | None,
        strategy: ConflictStrategy,
        result: CreateResult,
    ) -> None:
        """记录 mkdir 历史(若注入了 history_store)。形状与原 GUI 内联写入 /
        MkdirController.build_history_record 完全一致(strategy 以 enum 名存储)。
        """
        if self._history_store is None:
            return
        self._history_store.add_record(
            "mkdir",
            {
                "root": str(root) if root is not None else "",
                "structure_count": structure_count if structure_count is not None else 0,
                "strategy": strategy.name,
                "created": result.created_count,
                "skipped": result.skipped_count,
                "success": result.success,
            },
        )
