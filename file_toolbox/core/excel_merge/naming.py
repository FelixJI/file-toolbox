"""工作表命名:清洗非法字符、31 字符截断、大小写不敏感去重。

纯函数 + 小状态对象,不依赖 openpyxl,可独立单测。
"""

from file_toolbox.core.excel_merge.constants import NAMING_PREFIX

# Excel 工作表名硬上限(字符数)
SHEET_NAME_MAX_LEN = 31
# Excel 禁止出现在工作表名中的字符
SHEET_NAME_FORBIDDEN = set(":\\/?*[]")


def sanitize_sheet_name(name: str) -> str:
    """清洗为合法工作表名:替换非法字符、去首尾空白、截断到 31 字符。

    清洗后为空(如源标题全为非法字符)时回退为 "Sheet"。
    """
    cleaned = "".join("_" if ch in SHEET_NAME_FORBIDDEN else ch for ch in name)
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = "Sheet"
    return cleaned[:SHEET_NAME_MAX_LEN]


def compose_sheet_base(stem: str, sheet: str, naming: str) -> str:
    """按命名策略组合目标工作表名的基础文本(未做唯一化)。"""
    if naming == NAMING_PREFIX:
        return f"{stem}-{sheet}"
    return sheet


class SheetNamer:
    """按输出顺序为目标工作簿分配唯一且合法(<=31 字符)的工作表名。

    Excel 的工作表名大小写不敏感唯一("Data" 与 "DATA" 视为同名),
    故以 casefold 形式登记去重。冲突时截短基础名后追加 ~n 序号。
    """

    def __init__(self) -> None:
        self._used: set[str] = set()

    def assign(self, base: str) -> str:
        """登记并返回 base 对应的唯一合法工作表名。"""
        candidate = sanitize_sheet_name(base)
        key = candidate.casefold()
        if key not in self._used:
            self._used.add(key)
            return candidate
        n = 2
        while True:
            suffix = f"~{n}"
            room = SHEET_NAME_MAX_LEN - len(suffix)
            head = sanitize_sheet_name(base)[:room].rstrip()
            candidate = head + suffix
            key = candidate.casefold()
            if key not in self._used:
                self._used.add(key)
                return candidate
            n += 1
