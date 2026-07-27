"""pdf 命令端到端测试(CliRunner)。

仅传 PNG 图片,走 ImageConverter(纯 Pillow),全程不触发 Office COM,Linux CI 可跑通。
覆盖 cli/pdf_cmd.py:无文件报错、separate 模式、merge 模式。
"""

from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from file_toolbox.cli.main import app

runner = CliRunner()

pytest.importorskip("PIL")


def _png(path: Path) -> Path:
    """生成纯色 PNG(10x10)。"""
    Image.new("RGB", (10, 10), (255, 0, 0)).save(str(path))
    return path


def test_pdf_help_lists():
    """--help 输出命令说明。"""
    r = runner.invoke(app, ["pdf", "--help"])
    assert r.exit_code == 0
    assert "PDF" in r.output or "pdf" in r.output.lower()


def test_pdf_no_files_errors(tmp_path):
    """无文件 → 退出码 1 + 错误提示。"""
    r = runner.invoke(app, ["pdf"])
    assert r.exit_code == 1
    assert "文件" in r.output


def test_pdf_separate_single_png(tmp_path):
    """separate 模式(默认):1 张 PNG → 同目录生成同名 PDF。"""
    src = _png(tmp_path / "photo.png")
    r = runner.invoke(app, ["pdf", str(src)])
    assert r.exit_code == 0, r.output
    out = tmp_path / "photo.pdf"
    assert out.exists()
    # 输出是真 PDF(魔数)
    assert out.read_bytes()[:4] == b"%PDF"
    # 进度与完成提示
    assert "完成" in r.output
    assert "OK" in r.output


def test_pdf_merge_two_pngs(tmp_path):
    """merge 模式:2 张 PNG → 合并为一个 PDF(自定义合并名)。"""
    a = _png(tmp_path / "a.png")
    b = _png(tmp_path / "b.png")
    r = runner.invoke(
        app,
        [
            "pdf",
            str(a),
            str(b),
            "--output-mode",
            "merge",
            "--merge-name",
            "汇总.pdf",
        ],
    )
    assert r.exit_code == 0, r.output
    merged = tmp_path / "汇总.pdf"
    assert merged.exists()
    assert merged.read_bytes()[:4] == b"%PDF"


def test_pdf_image_type_dpi(tmp_path):
    """--pdf-type image + --dpi:图片型 PDF 生成(pypdf 转换,不依赖 COM)。"""
    src = _png(tmp_path / "scan.png")
    r = runner.invoke(
        app,
        ["pdf", str(src), "--pdf-type", "image", "--dpi", "150"],
    )
    assert r.exit_code == 0, r.output
    assert (tmp_path / "scan.pdf").exists()
