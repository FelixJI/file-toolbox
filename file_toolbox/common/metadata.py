"""应用元信息(单一数据源)。

CLI 的 --version 与 GUI About Tab 都从这里读,不各自硬编码。
"""

from pathlib import Path

from file_toolbox import __version__

APP_NAME = "File Toolbox"
APP_DESCRIPTION = "批量文件工具箱:重命名、建文件夹、生成 PDF、内容替换、发票识别"
VERSION = __version__
REPO_URL = "https://github.com/felji/file-toolbox"  # 占位常量,后续替换为真实地址
LICENSE = "MIT"
PYTHON_REQUIREMENT = ">=3.11"

# (组件名, 说明)元组列表 —— UI 控制格式化,数据不绑死呈现方式
TECH_STACK: list[tuple[str, str]] = [
    ("Python", ">=3.11"),
    ("PySide6", ">=6.5 (GUI)"),
    ("typer", ">=0.9 (CLI)"),
    ("pypdf / PyMuPDF", "(PDF 处理)"),
    ("pdfplumber + openpyxl", "(发票识别,可选)"),
    ("pywin32", ">=306 (Windows COM 自动化,仅 Windows)"),
]
