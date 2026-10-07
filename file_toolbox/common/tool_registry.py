"""统一工具登记:名称、稳定 ID、分类、历史与 GUI 入口的单一事实源。

本模块必须保持纯 Python:不得导入 Qt/任何 GUI 模块,也不得触发 Office/
Pandoc 探测或网络请求——CLI、metadata 与打包脚本都在启动链上读取它。
GUI 页面只以 ``gui_module``/``gui_class`` 字符串形式登记,真正的导入延迟
到首次切页时由 ``file_toolbox.gui.tab_factory`` 执行;新增普通 GUI 工具
只需编写其功能模块并在此登记一行,主窗口/历史/打包不再各写一份清单。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ToolCategory(StrEnum):
    """工具分类:业务页参与业务锁与关闭收尾,系统页(更新/关于)保持可用。"""

    BUSINESS = "business"
    SYSTEM = "system"


# 系统页稳定 ID:主窗口导航/登记查找按 ID 定位,不依赖标签序号。
UPDATE_TOOL_ID = "update"
ABOUT_TOOL_ID = "about"


@dataclass(frozen=True)
class ToolSpec:
    """单个工具的登记项(页面、历史与 CLI 能力的唯一来源)。

    tool_id: 稳定标识;业务工具的历史键与之一致。
    label: 标签栏显示名(保持既有用户可见顺序与名称)。
    capability: 能力名(关于页简介/CLI help 的组成单元)。
    gui_module / gui_class: GUI 页模块与类名,供懒工厂 importlib 导入。
    attr: 主窗口保存页面实例的属性名(懒构造登记/业务锁/关闭收尾)。
    category: 业务/系统分类。
    history_key: 历史记录键(None = 无历史按钮)。
    cli_command: 真实 CLI 子命令名(None = 仅 GUI,如考勤汇总)。
    summary: 历史记录一行摘要的纯函数(None = 回落 str(data)[:40])。
    """

    tool_id: str
    label: str
    capability: str
    gui_module: str
    gui_class: str
    attr: str
    category: ToolCategory
    history_key: str | None = None
    cli_command: str | None = None
    summary: Callable[[Mapping[str, object]], str] | None = None


# ---------------------------------------------------------------------------
# 历史摘要纯函数:只读 JSONL 记录 data(Mapping),不导入业务服务;
# 确需 len 的值按实际容器类型窄化。
# ---------------------------------------------------------------------------


def _rename_summary(data: Mapping[str, object]) -> str:
    mapping = data.get("rename_map", {})
    n = len(mapping) if isinstance(mapping, dict) else 0
    remaining = data.get("undo_remaining")
    suffix = f", 剩余 {len(remaining)} 个待撤销" if isinstance(remaining, list) else ""
    return f"{n} 个文件" + suffix


def _replace_summary(data: Mapping[str, object]) -> str:
    files = data.get("files", [])
    return f"{len(files) if isinstance(files, list) else 0} 个文件"


def _pdf_summary(data: Mapping[str, object]) -> str:
    files = data.get("files", [])
    ok = data.get("success", 0)
    return f"{ok}/{len(files) if isinstance(files, list) else 0} 个成功"


def _mkdir_summary(data: Mapping[str, object]) -> str:
    created = data.get("created", 0)
    skipped = data.get("skipped", 0)
    strategy = data.get("strategy", "?")
    root = data.get("root", "")
    return f"新建 {created}, 跳过 {skipped} [{strategy}] {root}"


def _invoice_summary(data: Mapping[str, object]) -> str:
    inv = data.get("invoice_count", 0)
    files = data.get("file_count", 0)
    fmt = data.get("fmt", "?")
    return f"{inv} 张发票 / {files} 文件 [{fmt}]"


def _excel_merge_summary(data: Mapping[str, object]) -> str:
    sheets = data.get("sheet_count", 0)
    files = data.get("file_count", 0)
    naming = data.get("naming", "?")
    output = Path(str(data.get("output", ""))).name
    return f"{sheets} 工作表 / {files} 文件 [{naming}] → {output}"


def _attendance_summary(data: Mapping[str, object]) -> str:
    employees = data.get("employee_count", 0)
    year = data.get("year", "?")
    month = data.get("month", "?")
    output = Path(str(data.get("output", ""))).name
    return f"{year}-{month} / {employees} 人 → {output}"


def _pdf_sort_summary(data: Mapping[str, object]) -> str:
    pages = data.get("page_count", 0)
    files = data.get("file_count", 0)
    outputs = data.get("outputs", [])
    order = data.get("order", "?")
    return f"{pages} 页 / {files} 文件 [{order}] → {len(outputs) if isinstance(outputs, list) else 0} 个输出"


def _markdown_summary(data: Mapping[str, object]) -> str:
    ok = data.get("success", 0)
    files = data.get("file_count", 0)
    target = data.get("target", "?")
    mode = data.get("excel_mode")
    suffix = f" [{mode}]" if mode else ""
    return f"{ok}/{files} 个文件{suffix} → {target}"


def _plan_schedule_summary(data: Mapping[str, object]) -> str:
    items = data.get("item_count", 0)
    months = data.get("month_count", 0)
    invalid = data.get("invalid_count", 0)
    output = Path(str(data.get("output", ""))).name
    return f"{items} 项点 / {months} 月(无效 {invalid}) → {output}"


# ---------------------------------------------------------------------------
# 有序登记:生产页面顺序/名称的唯一来源(10 个业务页 + 更新 + 关于)。
# ---------------------------------------------------------------------------

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        tool_id="rename",
        label="重命名",
        capability="重命名",
        gui_module="file_toolbox.gui.dialogs.rename_tab",
        gui_class="FileRenamerDialog",
        attr="_rename_tab",
        category=ToolCategory.BUSINESS,
        history_key="rename",
        cli_command="rename",
        summary=_rename_summary,
    ),
    ToolSpec(
        tool_id="mkdir",
        label="建文件夹",
        capability="建文件夹",
        gui_module="file_toolbox.gui.dialogs.mkdir_tab",
        gui_class="BatchFolderCreatorDialog",
        attr="_mkdir_tab",
        category=ToolCategory.BUSINESS,
        history_key="mkdir",
        cli_command="mkdir",
        summary=_mkdir_summary,
    ),
    ToolSpec(
        tool_id="pdf",
        label="生成PDF",
        capability="生成 PDF",
        gui_module="file_toolbox.gui.dialogs.pdf_tab",
        gui_class="PDFGeneratorDialog",
        attr="_pdf_tab",
        category=ToolCategory.BUSINESS,
        history_key="pdf",
        cli_command="pdf",
        summary=_pdf_summary,
    ),
    ToolSpec(
        tool_id="replace",
        label="内容替换",
        capability="内容替换",
        gui_module="file_toolbox.gui.dialogs.replace_tab",
        gui_class="ContentReplaceDialog",
        attr="_replace_tab",
        category=ToolCategory.BUSINESS,
        history_key="replace",
        cli_command="replace",
        summary=_replace_summary,
    ),
    ToolSpec(
        tool_id="attendance",
        label="考勤汇总",
        capability="考勤汇总",
        gui_module="file_toolbox.gui.dialogs.attendance_tab",
        gui_class="AttendanceTab",
        attr="_attendance_tab",
        category=ToolCategory.BUSINESS,
        history_key="attendance",
        cli_command=None,  # 考勤汇总当前仅 GUI,无 CLI 子命令
        summary=_attendance_summary,
    ),
    ToolSpec(
        tool_id="invoice",
        label="发票识别",
        capability="发票识别",
        gui_module="file_toolbox.gui.dialogs.invoice_tab",
        gui_class="InvoiceTab",
        attr="_invoice_tab",
        category=ToolCategory.BUSINESS,
        history_key="invoice",
        cli_command="invoice",
        summary=_invoice_summary,
    ),
    ToolSpec(
        tool_id="excel_merge",
        label="Excel合并",
        capability="Excel 合并",
        gui_module="file_toolbox.gui.dialogs.excel_merge_tab",
        gui_class="ExcelMergeTab",
        attr="_excel_merge_tab",
        category=ToolCategory.BUSINESS,
        history_key="excel_merge",
        cli_command="excel-merge",
        summary=_excel_merge_summary,
    ),
    ToolSpec(
        tool_id="pdf_sort",
        label="PDF排序",
        capability="PDF 排序",
        gui_module="file_toolbox.gui.dialogs.pdf_sort_tab",
        gui_class="PdfSortTab",
        attr="_pdf_sort_tab",
        category=ToolCategory.BUSINESS,
        history_key="pdf_sort",
        cli_command="pdf-sort",
        summary=_pdf_sort_summary,
    ),
    ToolSpec(
        tool_id="plan_schedule",
        label="计划排布",
        capability="计划排布",
        gui_module="file_toolbox.gui.dialogs.plan_schedule_tab",
        gui_class="PlanScheduleTab",
        attr="_plan_schedule_tab",
        category=ToolCategory.BUSINESS,
        history_key="plan_schedule",
        cli_command="plan-schedule",
        summary=_plan_schedule_summary,
    ),
    ToolSpec(
        tool_id="markdown_convert",
        label="Markdown转换",
        capability="Markdown 转换",
        gui_module="file_toolbox.gui.dialogs.markdown_tab",
        gui_class="MarkdownConvertTab",
        attr="_markdown_tab",
        category=ToolCategory.BUSINESS,
        history_key="markdown_convert",
        cli_command="markdown-convert",
        summary=_markdown_summary,
    ),
    ToolSpec(
        tool_id=UPDATE_TOOL_ID,
        label="更新",
        capability="更新",
        gui_module="file_toolbox.gui.dialogs.update_tab",
        gui_class="UpdateTab",
        attr="_update_tab",
        category=ToolCategory.SYSTEM,
    ),
    ToolSpec(
        tool_id=ABOUT_TOOL_ID,
        label="关于",
        capability="关于",
        gui_module="file_toolbox.gui.dialogs.about_tab",
        gui_class="AboutTab",
        attr="_about_tab",
        category=ToolCategory.SYSTEM,
    ),
)


def spec_by_history_key(history_key: str) -> ToolSpec | None:
    """按历史键查登记项(历史对话框摘要使用;调用时读模块级 TOOL_SPECS,
    便于测试以 monkeypatch 注入 fixture 登记)。"""
    for spec in TOOL_SPECS:
        if spec.history_key == history_key:
            return spec
    return None
