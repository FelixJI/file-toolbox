"""应用元信息(单一数据源)。

CLI 的 --version 与 GUI About Tab 都从这里读,不各自硬编码。
"""

from pathlib import Path

from file_toolbox import __version__

APP_NAME = "File Toolbox"
APP_DESCRIPTION = "批量文件工具箱:重命名、建文件夹、生成 PDF、内容替换、发票识别"
VERSION = __version__
REPO_URL = "https://github.com/FelixJI/file-toolbox"
LICENSE = "MIT"
PYTHON_REQUIREMENT = ">=3.11"

# (组件名, 说明)元组列表 —— UI 控制格式化,数据不绑死呈现方式
# 说明只写用途,不写版本(版本随依赖漂移,易过期;版本要求见"基本信息"区)
TECH_STACK: list[tuple[str, str]] = [
    ("Python", "(主语言)"),
    ("PySide6", "(GUI 框架)"),
    ("typer", "(CLI 框架)"),
    ("pypdf / PyMuPDF", "(PDF 处理)"),
    ("pdfplumber + openpyxl", "(发票识别,可选)"),
    ("pywin32", "(Windows COM 自动化,仅 Windows)"),
]


def _repo_root_changelog_path() -> Path:
    """开发环境下 CHANGELOG.md 的路径(包目录上两级 = 仓库根)。"""
    # metadata.py 在 file_toolbox/common/,上两级到仓库根
    return Path(__file__).resolve().parent.parent.parent / "CHANGELOG.md"


def _fallback_changelog() -> str:
    """找不到 CHANGELOG.md 时的兜底文本。"""
    return (
        f"当前版本 {VERSION}。\n"
        "完整更新日志请见开源仓库的 CHANGELOG.md。\n"
        "(未在当前运行环境找到 CHANGELOG.md 文件)"
    )


def get_changelog() -> str:
    """读取 CHANGELOG.md,失败返回兜底文本。

    查找顺序(3 级回退链):
    1. 仓库根(开发环境): _repo_root_changelog_path()
    2. 当前工作目录:      Path.cwd() / "CHANGELOG.md"
    3. 都找不到 →         _fallback_changelog()(含版本号,提示完整日志见仓库)

    pip 安装的包不含 CHANGELOG.md(在仓库根,包目录外),故回退链保证不报错。
    """
    candidates = [
        _repo_root_changelog_path(),
        Path.cwd() / "CHANGELOG.md",
    ]
    for p in candidates:
        try:
            if p.is_file():
                return p.read_text(encoding="utf-8")
        except OSError:
            continue
    return _fallback_changelog()
