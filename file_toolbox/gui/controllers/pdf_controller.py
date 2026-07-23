"""PDF Tab 业务编排:把 UI→配置 dict、结果汇总、历史记录构建从 Qt 依赖中抽离。

不 import PySide6 —— PDFConfigState 由 View 从 Qt 控件读取后填入,
controller 仅做纯 Python 编排,可无 Qt 单测。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from file_toolbox.core.batch_pdf.constants import (
    DPI_DEFAULT,
    OUTPUT_SEPARATE,
    PDF_TYPE_EDITABLE,
    PRINT_MODE_SINGLE,
    SCALE_DEFAULT,
)

# merge_filename 为空(或纯空白)时的回退默认值,与 pdf_tab._build_config 原行为一致。
_MERGE_FILENAME_DEFAULT = "合并文档.pdf"


@dataclass
class PDFConfigState:
    """PDF Tab UI 控件值的纯 Python 快照。

    View 负责把每个 radio/combo/edit 的当前值映射到此 dataclass 的字段(常量字符串值),
    再交由 PDFController.build_config 转为服务层期望的 config dict。
    """

    pdf_type: str = PDF_TYPE_EDITABLE
    dpi: int = DPI_DEFAULT
    paper_size: str = "auto"  # "auto" 或纸张名(A4/A5/...)
    orientation: str = "auto"  # "auto"/"portrait"/"landscape"
    scale_mode: str = SCALE_DEFAULT
    engine: str = "auto"  # "auto"/"office"/"wps"
    output_mode: str = OUTPUT_SEPARATE  # "separate"/"merge"
    same_as_source: bool = True
    print_mode: str = PRINT_MODE_SINGLE  # "single"/"duplex"
    merge_filename: str = ""
    output_dir: str = ""


class PDFController:
    """PDF Tab 的业务编排(无 Qt 依赖)。

    - build_config:PDFConfigState -> config dict(与 pdf_tab._build_config 等价)
    - summarize_results:统计成功/失败计数
    - format_progress:格式化进度文案 "[cur/total] msg"
    - build_history_record:构建写入 JsonHistoryStore 的记录 dict
    """

    def build_config(self, state: PDFConfigState) -> dict:
        """PDFConfigState -> 服务层 config dict。

        与原 pdf_tab._build_config 完全等价:
        - merge_filename 空白时回退到 "合并文档.pdf";
        - same_as_source=True 时不包含 output_dir;
        - same_as_source=False 时 output_dir 作为 Path 包含进 dict。
        """
        config = {
            "pdf_type": state.pdf_type,
            "dpi": int(state.dpi),
            "paper_size": state.paper_size,
            "orientation": state.orientation,
            "scale_mode": state.scale_mode,
            "engine": state.engine,
            "output_mode": state.output_mode,
            "same_as_source": state.same_as_source,
            "print_mode": state.print_mode,
            "merge_filename": state.merge_filename.strip() or _MERGE_FILENAME_DEFAULT,
        }
        if not state.same_as_source:
            config["output_dir"] = Path(state.output_dir.strip())
        return config

    def summarize_results(self, results: list[dict]) -> tuple[int, int]:
        """返回 (ok_count, fail_count):ok = r["success"] 为真的数量。"""
        ok = sum(1 for r in results if r["success"])
        return ok, len(results) - ok

    def format_progress(self, cur: int, total: int, msg: str) -> str:
        """进度文案:与原 pdf_tab._on_progress 的 label 格式一致。"""
        return f"[{cur}/{total}] {msg}"

    def build_history_record(self, files: list[Path], ok: int, fail: int, config: dict) -> dict:
        """构建写入 JsonHistoryStore 的记录 dict。

        与原 pdf_tab._on_generate_ok 内联结构完全一致:files 转 str 列表,
        config 只取 pdf_type/output_mode/engine/dpi 四个键(审计/复现所需的最小子集)。
        """
        return {
            "files": [str(f) for f in files],
            "success": ok,
            "failed": fail,
            "config": {
                "pdf_type": config["pdf_type"],
                "output_mode": config["output_mode"],
                "engine": config["engine"],
                "dpi": config["dpi"],
            },
        }


__all__ = ["PDFConfigState", "PDFController", "_MERGE_FILENAME_DEFAULT"]
