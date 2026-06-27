"""工具箱数据路径管理。数据跟程序走(运行目录下 .file_toolbox/)。

路径在每次调用时基于当前工作目录计算,而非在模块导入时固定 ——
避免导入后用户/程序切换 cwd 导致备份、历史写到错误位置。
"""

from pathlib import Path

_DIR_NAME = ".file_toolbox"


def _data_dir() -> Path:
    """数据根目录(运行目录下 .file_toolbox/)。不创建,供其它函数组合。"""
    return Path.cwd() / _DIR_NAME


def get_data_dir() -> Path:
    """获取(并创建)数据根目录。供模板等持久化文件落位。"""
    d = _data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_backup_dir() -> Path:
    """获取(并创建)备份目录。"""
    d = _data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_history_dir() -> Path:
    """获取(并创建)历史目录。"""
    d = _data_dir() / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d
