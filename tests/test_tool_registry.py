"""统一工具登记(tool_registry)契约:纯度、顺序、历史/CLI/GUI 单一来源。

Issue #138:登记是名称、稳定 ID、分类、history_key/summary、cli_command 与
GUI 模块/类名的唯一来源;纯登记/metadata/CLI 导入不得拉入 Qt/GUI(AC3),
也不得让登记/metadata 触碰 Office/Pandoc 等重依赖(AC6)。
"""

import subprocess
import sys

from file_toolbox.common import metadata, tool_registry
from file_toolbox.common.tool_registry import TOOL_SPECS, ToolCategory


def test_registry_and_metadata_imports_stay_pure():
    """纯导入契约:登记与 metadata 不得拉入 Qt/GUI/Office/Pandoc 等重依赖(AC3/AC6)。

    子进程隔离验证,避免本会话已导入模块干扰。
    """
    code = (
        "import sys\n"
        "import file_toolbox.common.tool_registry\n"
        "import file_toolbox.common.metadata\n"
        "banned = ('PySide6', 'shiboken6', 'pypandoc', 'pypdfium2', 'pypdf',\n"
        "          'win32com', 'openpyxl', 'requests', 'httpx', 'urllib3')\n"
        "leaked = [m for m in sys.modules\n"
        "          if m.split('.')[0] in banned or m.startswith('file_toolbox.gui')]\n"
        "print(','.join(sorted(leaked)))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == "", f"登记导入链被污染: {proc.stdout.strip()}"


def test_cli_imports_stay_qt_and_gui_free():
    """CLI 导入同样不得触碰 Qt/GUI;其自身正常库导入(typer/core 等)不算违规(AC3)。"""
    code = (
        "import sys\n"
        "import file_toolbox.cli.main\n"
        "leaked = [m for m in sys.modules\n"
        "          if m.split('.')[0] in {'PySide6', 'shiboken6'}\n"
        "          or m.startswith('file_toolbox.gui')]\n"
        "print(','.join(sorted(leaked)))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == "", f"CLI 导入链被污染: {proc.stdout.strip()}"


def test_production_order_and_labels():
    """生产页面顺序与名称的唯一回归锚点(保持当前 10 业务 + 更新 + 关于)。"""
    assert [(spec.tool_id, spec.label) for spec in TOOL_SPECS] == [
        ("rename", "重命名"),
        ("mkdir", "建文件夹"),
        ("pdf", "生成PDF"),
        ("replace", "内容替换"),
        ("attendance", "考勤汇总"),
        ("invoice", "发票识别"),
        ("excel_merge", "Excel合并"),
        ("pdf_sort", "PDF排序"),
        ("plan_schedule", "计划排布"),
        ("markdown_convert", "Markdown转换"),
        ("update", "更新"),
        ("about", "关于"),
    ]


def test_categories_history_keys_and_summaries():
    business = [spec for spec in TOOL_SPECS if spec.category is ToolCategory.BUSINESS]
    assert business and all(spec.history_key == spec.tool_id for spec in business)
    assert all(spec.summary is not None for spec in business)
    system = [spec for spec in TOOL_SPECS if spec.category is ToolCategory.SYSTEM]
    assert {spec.tool_id for spec in system} == {"update", "about"}
    assert all(spec.history_key is None and spec.cli_command is None for spec in system)


def test_cli_commands_match_real_cli_surface():
    """登记 cli_command 与 Typer 实际注册命令一致:九项业务,attendance 仅 GUI(AC6)。"""
    from file_toolbox.cli import main as cli_main

    def _resolved_name(command: object) -> str:
        # Typer 未显式命名时在编译期才从回调函数名解析,此处按同一规则求值
        name = getattr(command, "name", None)
        callback = getattr(command, "callback", None)
        return str(name) if name else callback.__name__.replace("_", "-")

    declared = {spec.cli_command for spec in TOOL_SPECS if spec.cli_command}
    assert declared == {
        "rename",
        "mkdir",
        "pdf",
        "pdf-sort",
        "replace",
        "invoice",
        "excel-merge",
        "plan-schedule",
        "markdown-convert",
    }
    registered = {_resolved_name(command) for command in cli_main.app.registered_commands}
    assert declared <= registered, "登记的 CLI 命令必须真实注册"
    assert registered - declared == {"gui"}, "除 gui 启动入口外不得有登记之外的业务命令"


def test_unique_ids_attrs_and_gui_entries():
    ids = [spec.tool_id for spec in TOOL_SPECS]
    attrs = [spec.attr for spec in TOOL_SPECS]
    gui_entries = [(spec.gui_module, spec.gui_class) for spec in TOOL_SPECS]
    assert len(set(ids)) == len(ids)
    assert len(set(attrs)) == len(attrs)
    assert len(set(gui_entries)) == len(gui_entries)


def test_history_key_lookup():
    markdown = tool_registry.spec_by_history_key("markdown_convert")
    assert markdown is not None and markdown.cli_command == "markdown-convert"
    assert tool_registry.spec_by_history_key("update") is None  # 系统页无历史键
    assert tool_registry.spec_by_history_key("no-such-tool") is None


def test_history_summary_callbacks_match_legacy_payloads():
    """摘要回调与既有 JSONL 记录负载兼容(历史键/格式不变,AC2)。"""
    rename = tool_registry.spec_by_history_key("rename")
    assert rename is not None and rename.summary is not None
    assert (
        rename.summary({"rename_map": {"a": "b", "c": "d"}, "undo_remaining": ["c"]})
        == "2 个文件, 剩余 1 个待撤销"
    )
    markdown = tool_registry.spec_by_history_key("markdown_convert")
    assert markdown is not None and markdown.summary is not None
    assert (
        markdown.summary({"success": 2, "file_count": 3, "target": "xlsx", "excel_mode": "tables"})
        == "2/3 个文件 [tables] → xlsx"
    )


def test_metadata_description_derived_from_registry():
    expected = "批量文件工具箱:" + "、".join(
        spec.capability for spec in TOOL_SPECS if spec.category is ToolCategory.BUSINESS
    )
    assert expected == metadata.APP_DESCRIPTION
    assert "考勤汇总" in metadata.APP_DESCRIPTION  # GUI-only 能力同样属于应用简介


def test_cli_help_derived_from_registry():
    """CLI help 只覆盖真实子命令能力:九项业务含发票识别,不含 GUI-only 考勤。"""
    from file_toolbox.cli.main import app as cli_app

    expected = "批量文件工具箱:" + "、".join(
        spec.capability for spec in TOOL_SPECS if spec.cli_command
    )
    assert cli_app.info.help == expected
    assert "发票识别" in expected and "考勤汇总" not in expected
