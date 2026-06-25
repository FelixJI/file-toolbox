"""工具箱数据路径管理。数据跟程序走(运行目录下 .file_toolbox/)。"""

from pathlib import Path

DATA_DIR = Path.cwd() / ".file_toolbox"
BACKUP_DIR = DATA_DIR / "backups"
HISTORY_DIR = DATA_DIR / "history"


def get_backup_dir() -> Path:
    """获取(并创建)备份目录。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def get_history_dir() -> Path:
    """获取(并创建)历史目录。"""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR
