"""File Toolbox - 批量文件工具箱:重命名、建文件夹、生成 PDF、内容替换。"""

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "File Toolbox"
APP_DESCRIPTION = "批量文件工具箱"

try:
    __version__ = version("file-toolbox")
except PackageNotFoundError:  # 源码树直接运行(未安装),回退避免崩溃
    __version__ = "0.0.0+unknown"
