"""invoice_cmd 未覆盖分支补充测试。

覆盖行:
- 17-20: _expand 目录(recursive / 非递归)
- 48-53: 无效 --dedupe
- 57-62: 无效 --format
- 76-78: 去重移除预览输出
- 80-82: 失败文件预览输出
- 95: fmt=both json_path
- 97: fmt=json + output.xlsx → 改后缀
- 99: fmt=excel + output.json → 改后缀
"""

from pathlib import Path

from typer.testing import CliRunner

from file_toolbox.cli.invoice_cmd import _expand
from file_toolbox.cli.main import app

runner = CliRunner()


def _xml(path: Path, num: str) -> Path:
    path.write_text(
        f'<?xml version="1.0"?><EInvoice>'
        f"<Header><InherentLabel><GeneralOrSpecialVAT><LabelName>增值税专用发票</LabelName></GeneralOrSpecialVAT></InherentLabel></Header>"
        f"<EInvoiceData><SellerInformation><SellerName>s{num}</SellerName><SellerIdNum>sid</SellerIdNum>"
        f"<SellerAddr/><SellerTelNum/><SellerBankName/><SellerBankAccNum/></SellerInformation>"
        f"<BuyerInformation><BuyerName>b{num}</BuyerName><BuyerIdNum>bid</BuyerIdNum>"
        f"<BuyerTelNum/><BuyerAddr/><BuyerBankName/><BuyerBankAccNum/></BuyerInformation>"
        f"<BasicInformation><TotalAmWithoutTax>1.00</TotalAmWithoutTax><TotalTaxAm>0.13</TotalTaxAm>"
        f"<TotalTax-includedAmount>1.13</TotalTax-includedAmount>"
        f"<TotalTax-includedAmountInChinese>壹圆</TotalTax-includedAmountInChinese>"
        f"<Drawer>x</Drawer></BasicInformation></EInvoiceData>"
        f"<TaxSupervisionInfo><InvoiceNumber>{num}</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>"
        f"</EInvoice>",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# _expand:目录递归/非递归(行 17-20)
# ---------------------------------------------------------------------------


def test_expand_directory_non_recursive(tmp_path):
    """--dir 非递归:加入目录直接子文件(行 19-20)。"""
    f1 = tmp_path / "a.xml"
    f1.write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.xml").write_text("y")
    result = _expand([], tmp_path, recursive=False)
    names = [p.name for p in result]
    assert "a.xml" in names
    assert "b.xml" not in names  # 非递归不进子目录


def test_expand_directory_recursive(tmp_path):
    """--dir --recursive:递归加入所有文件(行 17-18)。"""
    f1 = tmp_path / "a.xml"
    f1.write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.xml").write_text("y")
    result = _expand([], tmp_path, recursive=True)
    names = [p.name for p in result]
    assert "a.xml" in names
    assert "b.xml" in names


def test_expand_dedup_keeps_order(tmp_path):
    """重复文件去重,保持顺序。"""
    f1 = tmp_path / "a.xml"
    f1.write_text("x")
    result = _expand([f1, f1], None, False)
    assert len(result) == 1


def test_expand_no_directory_returns_files(tmp_path):
    """无 directory → 只返回 files。"""
    f1 = tmp_path / "a.xml"
    result = _expand([f1], None, False)
    assert result == [f1]


# ---------------------------------------------------------------------------
# invoice:无效 --dedupe(行 48-53)
# ---------------------------------------------------------------------------


def test_invoice_invalid_dedupe_errors(tmp_path):
    f = _xml(tmp_path / "1.xml", "1")
    r = runner.invoke(app, ["invoice", str(f), "--dedupe", "bogus"])
    assert r.exit_code == 1
    assert "无效的 --dedupe" in r.output


# ---------------------------------------------------------------------------
# invoice:无效 --format(行 57-62)
# ---------------------------------------------------------------------------


def test_invoice_invalid_format_errors(tmp_path):
    f = _xml(tmp_path / "1.xml", "1")
    r = runner.invoke(app, ["invoice", str(f), "--format", "bogus"])
    assert r.exit_code == 1
    assert "无效的 --format" in r.output


# ---------------------------------------------------------------------------
# invoice:去重移除预览(行 76-78)
# ---------------------------------------------------------------------------


def test_invoice_preview_shows_removed_duplicates(tmp_path):
    """dedupe 策略 + 同号文件 → 预览输出去重移除列表(行 75-78)。"""
    f1 = _xml(tmp_path / "111.xml", "111")
    f2 = _xml(tmp_path / "111b.xml", "111")  # 同号
    r = runner.invoke(app, ["invoice", str(f1), str(f2), "--dedupe", "dedupe"])
    assert r.exit_code == 0
    assert "去重移除" in r.output


# ---------------------------------------------------------------------------
# invoice:失败文件预览(行 80-82)
# ---------------------------------------------------------------------------


def test_invoice_preview_shows_failed(tmp_path):
    """含坏文件 → 预览输出失败列表(行 79-82)。"""
    f1 = _xml(tmp_path / "111.xml", "111")
    bad = tmp_path / "bad.xml"
    bad.write_text("not xml", encoding="utf-8")
    r = runner.invoke(app, ["invoice", str(f1), str(bad)])
    assert r.exit_code == 0
    assert "失败" in r.output


# ---------------------------------------------------------------------------
# invoice:fmt=both(行 95)
# ---------------------------------------------------------------------------


def test_invoice_export_both_writes_excel_and_json(tmp_path):
    f = _xml(tmp_path / "1.xml", "1")
    out = tmp_path / "out.xlsx"
    r = runner.invoke(app, ["invoice", str(f), "--format", "both", "--output", str(out), "--yes"])
    assert r.exit_code == 0, r.output
    assert out.exists()
    assert out.with_suffix(".json").exists()


# ---------------------------------------------------------------------------
# invoice:fmt=json + output.xlsx → 改后缀(行 96-97)
# ---------------------------------------------------------------------------


def test_invoice_export_json_fixes_xlsx_suffix(tmp_path):
    """--format json --output x.xlsx → 输出改 .json(行 96-97)。"""
    f = _xml(tmp_path / "1.xml", "1")
    out = tmp_path / "out.xlsx"
    r = runner.invoke(app, ["invoice", str(f), "--format", "json", "--output", str(out), "--yes"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "out.json").exists()
    assert not out.exists()


# ---------------------------------------------------------------------------
# invoice:fmt=excel + output.json → 改后缀(行 98-99)
# ---------------------------------------------------------------------------


def test_invoice_export_excel_fixes_json_suffix(tmp_path):
    """--format excel --output x.json → 输出改 .xlsx(行 98-99)。"""
    f = _xml(tmp_path / "1.xml", "1")
    out = tmp_path / "out.json"
    r = runner.invoke(app, ["invoice", str(f), "--format", "excel", "--output", str(out), "--yes"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "out.xlsx").exists()
    assert not out.exists()
