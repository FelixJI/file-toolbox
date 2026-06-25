"""
文本文件内容替换处理器

负责纯文本文件（.txt, .md）的读取和内容替换操作。
"""

import re
import unicodedata
from pathlib import Path

from file_toolbox.core.batch_replace.types import ReplaceOperationType


class TextHandler:
    """文本文件处理器"""

    def read_content(self, file_path: Path) -> str:
        """
        读取文本文件内容

        Args:
            file_path: 文件路径

        Returns:
            文件文本内容
        """
        # 尝试多种编码
        encodings = ["utf-8", "gbk", "gb2312", "utf-16", "latin-1"]

        for encoding in encodings:
            try:
                with open(file_path, encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue

        # 使用 chardet 检测编码
        try:
            import chardet

            with open(file_path, "rb") as f:
                raw_data = f.read()
            detected = chardet.detect(raw_data)
            encoding = detected.get("encoding", "utf-8")
            if encoding:
                return raw_data.decode(encoding)
        except Exception:
            pass

        # 最后尝试 utf-8 忽略错误
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            return f.read()

    def replace_file(self, file_path: Path, operations: list[dict]) -> int:
        """
        替换文本文件内容

        Args:
            file_path: 文件路径
            operations: 操作列表

        Returns:
            替换次数
        """
        content = self.read_content(file_path)
        original_content = content

        total_replacements = 0

        for operation in operations:
            content, count = self._apply_operation(content, operation)
            total_replacements += count

        if content != original_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        return total_replacements

    def count_matches(self, content: str, operations: list[dict]) -> int:
        """
        统计匹配数量

        Args:
            content: 文本内容
            operations: 操作列表

        Returns:
            匹配总数
        """
        from file_toolbox.core.batch_replace.types import ReplaceOperationType

        total_count = 0
        for operation in operations:
            op_type = operation.get("type")
            params = operation.get("params", {})

            if op_type == ReplaceOperationType.SIMPLE_REPLACE.value:
                find_text = params.get("find", "")
                case_sensitive = params.get("case_sensitive", False)

                if not find_text:
                    continue

                if case_sensitive:
                    total_count += content.count(find_text)
                else:
                    total_count += content.lower().count(find_text.lower())

            elif op_type == ReplaceOperationType.REGEX_REPLACE.value:
                pattern = params.get("pattern", "")
                ignore_case = params.get("ignore_case", False)

                if not pattern:
                    continue

                try:
                    flags = re.IGNORECASE if ignore_case else 0
                    matches = list(re.finditer(pattern, content, flags))
                    total_count += len(matches)
                except re.error:
                    pass

        return total_count

    def _apply_operation(self, text: str, operation: dict) -> tuple[str, int]:
        """
        应用单个操作

        Args:
            text: 原始文本
            operation: 操作配置

        Returns:
            (新文本, 替换次数)
        """
        from file_toolbox.core.batch_replace.types import ReplaceOperationType

        op_type = operation.get("type")
        params = operation.get("params", {})

        if op_type == ReplaceOperationType.SIMPLE_REPLACE.value:
            find_text = params.get("find", "")
            replace_text = params.get("replace", "")
            case_sensitive = params.get("case_sensitive", False)

            if not find_text:
                return text, 0

            if case_sensitive:
                count = text.count(find_text)
                new_text = text.replace(find_text, replace_text)
            else:
                pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                matches = pattern.findall(text)
                count = len(matches)
                new_text = pattern.sub(replace_text, text)

            return new_text, count

        elif op_type == ReplaceOperationType.REGEX_REPLACE.value:
            pattern_str = params.get("pattern", "")
            replace_text = params.get("replace", "")
            ignore_case = params.get("ignore_case", False)

            if not pattern_str:
                return text, 0

            try:
                flags = re.IGNORECASE if ignore_case else 0
                pattern = re.compile(pattern_str, flags)
                new_text, count = pattern.subn(replace_text, text)
                return new_text, count
            except re.error:
                return text, 0

        return text, 0

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        标准化文本，移除不可见的 Unicode 字符

        Args:
            text: 原始文本

        Returns:
            标准化后的文本
        """
        if not text:
            return text

        # Unicode 标准化 (NFC 格式)
        text = unicodedata.normalize("NFC", text)

        # 移除零宽字符和其他不可见控制字符
        invisible_chars = [
            "\u200b",  # 零宽空格
            "\u200c",  # 零宽非连接符
            "\u200d",  # 零宽连接符
            "\u200e",  # 从左到右标记
            "\u200f",  # 从右到左标记
            "\ufeff",  # 零宽非断空格 (BOM)
            "\u00ad",  # 软连字符
            "\u2060",  # 词组连接符
        ]

        for char in invisible_chars:
            text = text.replace(char, "")

        return text
