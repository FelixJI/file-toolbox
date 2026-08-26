"""File Toolbox - 批量文件工具箱(名称/描述等元信息统一见 common.metadata)。"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("file-toolbox")
except PackageNotFoundError:  # 源码树直接运行(未安装),回退避免崩溃
    __version__ = "0.0.0+unknown"
