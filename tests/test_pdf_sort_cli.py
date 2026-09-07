"""pdf-sort CLI 测试:预览默认、--yes 执行、参数校验、失败退出码。

全部基于程序化生成的虚构 PDF(reportlab 文字页),纯 Python、跨平台。
"""

from pypdf import PdfReader
from typer.testing import CliRunner

from file_toolbox.cli.main import app

runner = CliRunner()


def _texts(path) -> list[str]:
    with path.open("rb") as stream:
        return [(p.extract_text() or "").strip() for p in PdfReader(stream).pages]


def test_preview_lists_mapping_without_writing(make_text_pdf, tmp_path):
    """默认预览:列出 原页码 -> 新位置 与排序文字,不产生输出文件。"""
    src = make_text_pdf("d.pdf", ["Date: 2024-03-15", "Date: 2024-01-02"])

    r = runner.invoke(app, ["pdf-sort", str(src), "-p", r"Date:\s*([0-9-]+)"])

    assert r.exit_code == 0
    assert '第1页 -> 第2位  "2024-03-15"' in r.output
    assert '第2页 -> 第1位  "2024-01-02"' in r.output
    assert "可排序 1" in r.output
    assert "预览模式" in r.output
    assert not (tmp_path / "d_排序.pdf").exists()


def test_preview_marks_unmatched_and_failed(make_text_pdf, tmp_path):
    """预览标出未匹配页与不会排序的文件(如无文字层)。"""
    src = make_text_pdf("m.pdf", ["Date: 2024-01-01", "no marks", "Date: 2023-12-31"])
    blank = tmp_path / "blank.pdf"
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.write(blank)
    writer.close()

    r = runner.invoke(app, ["pdf-sort", str(src), str(blank), "-p", r"Date:\s*([0-9-]+)"])

    assert r.exit_code == 0
    assert "第2页" in r.output and "未匹配" in r.output
    assert "不会排序" in r.output and "文字层" in r.output
    assert "可排序 1" in r.output


def test_execute_writes_sorted_output(make_text_pdf, tmp_path):
    src = make_text_pdf("d.pdf", ["Date: 2024-03-15", "Date: 2024-01-02", "Date: 2024-02-01"])

    r = runner.invoke(app, ["pdf-sort", str(src), "-p", r"Date:\s*([0-9-]+)", "--yes"])

    assert r.exit_code == 0
    out = tmp_path / "d_排序.pdf"
    assert out.is_file()
    assert _texts(out) == ["Date: 2024-01-02", "Date: 2024-02-01", "Date: 2024-03-15"]
    assert "完成: 处理 1 个文件, 写出 1 个输出" in r.output


def test_execute_custom_output_and_order(make_text_pdf, tmp_path):
    src = make_text_pdf("d.pdf", ["Date: 2024-01-02", "Date: 2024-03-15"])
    out = tmp_path / "sub" / "out.doc"  # 非法后缀归一为 .pdf

    r = runner.invoke(
        app,
        [
            "pdf-sort",
            str(src),
            "-p",
            r"Date:\s*([0-9-]+)",
            "--order",
            "desc",
            "--yes",
            "-o",
            str(out),
        ],
    )

    assert r.exit_code == 0
    real_out = tmp_path / "sub" / "out.pdf"
    assert _texts(real_out) == ["Date: 2024-03-15", "Date: 2024-01-02"]


def test_dir_batch_each_sorted(make_text_pdf, tmp_path):
    make_text_pdf("a.pdf", ["Date: 2024-02-01", "Date: 2024-01-01"])
    make_text_pdf("b.pdf", ["Date: 2024-01-01"])
    (tmp_path / "note.txt").write_text("x")

    r = runner.invoke(
        app, ["pdf-sort", "--dir", str(tmp_path), "-p", r"Date:\s*([0-9-]+)", "--yes"]
    )

    assert r.exit_code == 0
    assert "已忽略 1 个不支持的文件" in r.output
    assert _texts(tmp_path / "a_排序.pdf") == ["Date: 2024-01-01", "Date: 2024-02-01"]
    assert (tmp_path / "b_排序.pdf").is_file() or "顺序未变" in r.output  # b 单页顺序未变


def test_no_files_errors(tmp_path):
    r = runner.invoke(app, ["pdf-sort", "-p", "Date"])
    assert r.exit_code == 1
    assert "未选择任何 PDF 文件" in r.output


def test_invalid_order_rejected(make_text_pdf):
    src = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    r = runner.invoke(app, ["pdf-sort", str(src), "-p", "Date", "--order", "bad"])
    assert r.exit_code == 1
    assert "无效的 --order" in r.output


def test_invalid_unmatched_rejected(make_text_pdf):
    src = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    r = runner.invoke(app, ["pdf-sort", str(src), "-p", "Date", "--unmatched", "bad"])
    assert r.exit_code == 1
    assert "无效的 --unmatched" in r.output


def test_invalid_pattern_friendly_error(make_text_pdf):
    src = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    r = runner.invoke(app, ["pdf-sort", str(src), "-p", "([0-9"])
    assert r.exit_code == 1
    assert "无效的匹配格式" in r.output


def test_dir_not_a_directory_errors(make_text_pdf, tmp_path):
    src = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    r = runner.invoke(app, ["pdf-sort", "--dir", str(src), "-p", "Date"])
    assert r.exit_code == 1
    assert "不是目录" in r.output


def test_output_file_with_multiple_files_rejected(make_text_pdf, tmp_path):
    a = make_text_pdf("a.pdf", ["Date: 2024-01-01"])
    b = make_text_pdf("b.pdf", ["Date: 2024-01-02"])
    r = runner.invoke(
        app, ["pdf-sort", str(a), str(b), "-p", "Date", "-o", str(tmp_path / "m.pdf")]
    )
    assert r.exit_code == 1
    assert "输出目录" in r.output


def test_execute_unmatched_fail_exits_nonzero(make_text_pdf, tmp_path):
    src = make_text_pdf("f.pdf", ["Date: 2024-01-01", "no marks"])
    r = runner.invoke(
        app, ["pdf-sort", str(src), "-p", r"Date:\s*([0-9-]+)", "--unmatched", "fail", "--yes"]
    )
    assert r.exit_code == 1
    assert "1 页未匹配" in r.output
    assert not (tmp_path / "f_排序.pdf").exists()


def test_execute_all_failed_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"nope")
    r = runner.invoke(app, ["pdf-sort", str(bad), "-p", "Date", "--yes"])
    assert r.exit_code == 1
    assert "全部源文件失败" in r.output


def test_output_auto_numbered_when_exists(make_text_pdf, tmp_path):
    src = make_text_pdf("a.pdf", ["Date: 2024-02-01", "Date: 2024-01-01"])
    out = tmp_path / "a_排序.pdf"
    out.write_text("precious")

    r = runner.invoke(app, ["pdf-sort", str(src), "-p", r"Date:\s*([0-9-]+)", "--yes"])

    assert r.exit_code == 0
    assert out.read_text(encoding="utf-8") == "precious"
    assert (tmp_path / "a_排序_1.pdf").is_file()
