"""文件工具函数(不依赖 Qt)。"""

from datetime import datetime
from pathlib import Path
from typing import Any


def format_file_size(size: int | float) -> str:
    """格式化文件大小为人类可读格式。"""
    if size < 0:
        return "未知"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_datetime(dt: datetime | str | None = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化日期时间，返回带时区信息的字符串。"""
    if dt is None:
        dt = datetime.now().astimezone()
    elif isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.astimezone()
        except (ValueError, AttributeError):
            return str(dt)
    elif dt.tzinfo is None:
        dt = dt.astimezone()
    time_str = dt.strftime(fmt)
    offset_str = dt.strftime("%z")
    tz_info = f"UTC{offset_str}" if offset_str else "UTC"
    return f"{time_str} [{tz_info}]"


def get_file_info(file_path: Path) -> dict[str, Any]:
    """获取文件信息(存在性、大小、修改时间)。"""
    result: dict[str, Any] = {
        "exists": False,
        "size": 0,
        "size_str": "未知",
        "modified": None,
        "modified_str": "未知",
        "suffix": "",
        "is_file": False,
    }
    try:
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        if file_path.exists():
            result["exists"] = True
            result["is_file"] = file_path.is_file()
            result["suffix"] = file_path.suffix.lower()
            if file_path.is_file():
                stat = file_path.stat()
                result["size"] = stat.st_size
                result["size_str"] = format_file_size(stat.st_size)
                result["modified"] = datetime.fromtimestamp(stat.st_mtime)
                result["modified_str"] = format_datetime(result["modified"])
    except Exception as e:
        result["error"] = str(e)
    return result
