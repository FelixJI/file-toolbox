"""PDFController 测试:纯 Python(不 import PySide6)。

校验 build_config/summarize_results/format_progress/build_history_record 与
pdf_tab._build_config / _on_generate_ok 内联逻辑完全等价。
"""

from pathlib import Path

from file_toolbox.core.batch_pdf.constants import (
    DPI_DEFAULT,
    OUTPUT_MERGE,
    OUTPUT_SEPARATE,
    PDF_TYPE_EDITABLE,
    PDF_TYPE_IMAGE,
    PRINT_MODE_DUPLEX,
    PRINT_MODE_SINGLE,
    SCALE_DEFAULT,
)
from file_toolbox.gui.controllers.pdf_controller import PDFConfigState, PDFController


def _state(**overrides) -> PDFConfigState:
    """默认 = pdf_tab 打开时的 UI 默认状态(image=False/merge=False/same_dir=True)。"""
    defaults = {
        "pdf_type": PDF_TYPE_EDITABLE,
        "dpi": DPI_DEFAULT,
        "paper_size": "auto",
        "orientation": "auto",
        "scale_mode": SCALE_DEFAULT,
        "engine": "auto",
        "output_mode": OUTPUT_SEPARATE,
        "same_as_source": True,
        "print_mode": PRINT_MODE_SINGLE,
        "merge_filename": "",
        "output_dir": "",
    }
    defaults.update(overrides)
    return PDFConfigState(**defaults)


_controller = PDFController()


# ---------- build_config ----------


def test_build_config_separate_same_dir():
    """默认(分离模式 + 同源目录):不含 output_dir 键。"""
    config = _controller.build_config(_state())
    assert config["pdf_type"] == PDF_TYPE_EDITABLE
    assert config["output_mode"] == OUTPUT_SEPARATE
    assert config["same_as_source"] is True
    assert config["dpi"] == DPI_DEFAULT
    assert config["paper_size"] == "auto"
    assert config["orientation"] == "auto"
    assert config["scale_mode"] == SCALE_DEFAULT
    assert config["engine"] == "auto"
    assert config["print_mode"] == PRINT_MODE_SINGLE
    assert config["merge_filename"] == "合并文档.pdf"
    assert "output_dir" not in config


def test_build_config_custom_dir_includes_output_dir():
    """same_as_source=False → output_dir 作为 Path 包含进 dict。"""
    config = _controller.build_config(_state(same_as_source=False, output_dir="/tmp/out"))
    assert config["same_as_source"] is False
    assert "output_dir" in config
    assert isinstance(config["output_dir"], Path)
    assert str(config["output_dir"]) == str(Path("/tmp/out"))


def test_build_config_custom_dir_strips_whitespace():
    """output_dir 空白被 strip(与 pdf_tab 原 Path(text.strip()) 行为一致)。"""
    config = _controller.build_config(_state(same_as_source=False, output_dir="  /tmp/out  "))
    assert str(config["output_dir"]) == str(Path("/tmp/out"))


def test_build_config_uses_merge_filename_default():
    """空白 merge_filename → "合并文档.pdf"(与 pdf_tab 原 strip() or 行为一致)。"""
    config = _controller.build_config(_state(merge_filename="   "))
    assert config["merge_filename"] == "合并文档.pdf"


def test_build_config_preserves_explicit_merge_filename():
    """显式非空 merge_filename 保留(并 strip 尾空白)。"""
    config = _controller.build_config(_state(merge_filename="报告.pdf"))
    assert config["merge_filename"] == "报告.pdf"


def test_build_config_image_merge_duplex_wps():
    """全选项翻转:image + merge + duplex + wps + 自定义纸张/方向/缩放/引擎。"""
    config = _controller.build_config(
        _state(
            pdf_type=PDF_TYPE_IMAGE,
            output_mode=OUTPUT_MERGE,
            print_mode=PRINT_MODE_DUPLEX,
            engine="wps",
            paper_size="A4",
            orientation="landscape",
            scale_mode="actual_size",
            dpi=600,
            merge_filename="合并.pdf",
        )
    )
    assert config["pdf_type"] == PDF_TYPE_IMAGE
    assert config["output_mode"] == OUTPUT_MERGE
    assert config["print_mode"] == PRINT_MODE_DUPLEX
    assert config["engine"] == "wps"
    assert config["paper_size"] == "A4"
    assert config["orientation"] == "landscape"
    assert config["scale_mode"] == "actual_size"
    assert config["dpi"] == 600
    assert config["merge_filename"] == "合并.pdf"


# ---------- summarize_results ----------


def test_summarize_results_mixed():
    """混合成功/失败 → (ok, fail) 计数正确。"""
    results = [
        {"success": True},
        {"success": False},
        {"success": True},
        {"success": False},
        {"success": True},
    ]
    ok, fail = _controller.summarize_results(results)
    assert ok == 3
    assert fail == 2


def test_summarize_results_empty():
    """空结果 → (0, 0)。"""
    assert _controller.summarize_results([]) == (0, 0)


def test_summarize_results_all_success():
    """全部成功 → fail=0。"""
    results = [{"success": True}, {"success": 1}, {"success": "x"}]
    ok, fail = _controller.summarize_results(results)
    assert ok == 3
    assert fail == 0


# ---------- format_progress ----------


def test_format_progress():
    """与 pdf_tab._on_progress 的 label 格式一致。"""
    assert _controller.format_progress(2, 5, "处理中") == "[2/5] 处理中"
    assert _controller.format_progress(0, 0, "") == "[0/0] "


# ---------- build_history_record ----------


def test_build_history_record_structure():
    """files 转 str 列表,config 仅保留 pdf_type/output_mode/engine/dpi 子集。"""
    files = [Path("a.docx"), Path("b/b.xlsx")]
    config = {
        "pdf_type": PDF_TYPE_IMAGE,
        "output_mode": OUTPUT_MERGE,
        "engine": "wps",
        "dpi": 600,
        "paper_size": "A4",  # 应被剔除
        "orientation": "landscape",  # 应被剔除
        "scale_mode": "fit_margin",  # 应被剔除
        "same_as_source": False,  # 应被剔除
        "print_mode": PRINT_MODE_DUPLEX,  # 应被剔除
        "merge_filename": "x.pdf",  # 应被剔除
    }
    record = _controller.build_history_record(files, ok=2, fail=1, config=config)
    assert record["files"] == [str(Path("a.docx")), str(Path("b/b.xlsx"))]
    assert record["success"] == 2
    assert record["failed"] == 1
    assert record["config"] == {
        "pdf_type": PDF_TYPE_IMAGE,
        "output_mode": OUTPUT_MERGE,
        "engine": "wps",
        "dpi": 600,
    }
    # 不应包含被剔除的键
    for excluded in ("paper_size", "orientation", "scale_mode", "print_mode", "merge_filename"):
        assert excluded not in record["config"]
