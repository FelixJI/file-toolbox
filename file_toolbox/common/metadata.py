"""应用元信息(单一数据源)。

CLI 的 --version 与 GUI About Tab 都从这里读,不各自硬编码。
"""

import sys
from pathlib import Path

from file_toolbox import __version__
from file_toolbox.common.tool_registry import TOOL_SPECS, ToolCategory

APP_NAME = "File Toolbox"
# 能力简介由统一工具登记派生(业务页 capability 按登记顺序拼接),
# 不在这里维护第二份能力清单或硬编码总数。
APP_DESCRIPTION = "批量文件工具箱:" + "、".join(
    spec.capability for spec in TOOL_SPECS if spec.category is ToolCategory.BUSINESS
)
VERSION = __version__
REPO_URL = "https://github.com/FelixJI/file-toolbox"
LICENSE = "MIT"
PYTHON_REQUIREMENT = ">=3.13"


def runtime_version() -> str:
    """当前运行的展示版本:打包态以 Velopack 安装清单为准,其余回落 importlib。

    打包产物不携带 dist-info,importlib 在该形态会得到 ``0.0.0+unknown``;
    Velopack locator 的 ``current/sq.version`` 才是更新器比对的真实身份。
    """

    from file_toolbox.updater.runtime_support import packaged_version

    sdk_version = packaged_version()
    if sdk_version:
        return sdk_version
    return VERSION


# (组件名, 说明)元组列表 —— UI 控制格式化,数据不绑死呈现方式
# 说明只写用途,不写版本(版本随依赖漂移,易过期;版本要求见"基本信息"区)
TECH_STACK: list[tuple[str, str]] = [
    ("Python", "(主语言)"),
    ("PySide6", "(GUI 框架)"),
    ("typer", "(CLI 框架)"),
    ("pypdf + pypdfium2", "(PDF 处理)"),
    ("Pillow", "(图片处理)"),
    ("openpyxl", "(Excel 读写,基础依赖)"),
    ("Pandoc + markdown-it-py", "(Markdown 转 Word/Excel)"),
    ("pdfplumber", "(发票识别,可选依赖)"),
    ("pywin32", "(Windows COM 自动化,仅 Windows)"),
    ("velopack", "(应用内自动更新)"),
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

    查找顺序(4 级回退链):
    1. 仓库根(开发环境): _repo_root_changelog_path()
    2. 便携 exe 同级:      Path(sys.executable).parent / "CHANGELOG.md"
                           (Nuitka standalone 产物;build_exe 用 --include-data-files 拷入)
    3. 当前工作目录:       Path.cwd() / "CHANGELOG.md"
    4. 都找不到 →          _fallback_changelog()(含版本号,提示完整日志见仓库)

    pip 安装的包不含 CHANGELOG.md(在仓库根,包目录外),故回退链保证不报错。
    """
    candidates = [
        _repo_root_changelog_path(),
        Path(sys.executable).parent / "CHANGELOG.md",
        Path.cwd() / "CHANGELOG.md",
    ]
    for p in candidates:
        try:
            if p.is_file():
                return p.read_text(encoding="utf-8")
        except OSError:
            continue
    return _fallback_changelog()
