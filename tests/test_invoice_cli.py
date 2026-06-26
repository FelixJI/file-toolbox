from pathlib import Path

from typer.testing import CliRunner

from file_toolbox.cli.main import app

runner = CliRunner()


def _xml(path: Path, num: str):
    path.write_text(
        f'<?xml version="1.0"?><EInvoice>'
        f"<Header><InherentLabel><GeneralOrSpecialVAT><LabelName>增值税专用发票</LabelName></GeneralOrSpecialVAT></InherentLabel></Header>"
        f"<EInvoiceData><SellerInformation><SellerName>s{num}</SellerName><SellerIdNum>sid</SellerIdNum>"
        f"<SellerAddr/><SellerTelNum/><SellerBankName/><SellerBankAccNum/></SellerInformation>"
        f"<BuyerInformation><BuyerName>b{num}</BuyerName><BuyerIdNum>bid</BuyerIdNum>"
        f"<BuyerTelNum/><BuyerAddr/><BuyerBankName/><BuyerBankAccNum/></BuyerInformation>"
        f"<BasicInformation><TotalAmWithoutTax>1.00</TotalAmWithoutTax><TotalTaxAm>0.13</TotalTaxAm>"
        f"<TotalTax-includedAmount>1.13</TotalTax-includedAmount><TotalTax-includedAmountInChinese>壹圆</TotalTax-includedAmountInChinese>"
        f"<Drawer>x</Drawer></BasicInformation></EInvoiceData>"
        f"<TaxSupervisionInfo><InvoiceNumber>{num}</InvoiceNumber><IssueTime>2026-05-19</IssueTime></TaxSupervisionInfo>"
        f"</EInvoice>",
        encoding="utf-8",
    )
    return path


def test_invoice_help_lists():
    r = runner.invoke(app, ["invoice", "--help"])
    assert r.exit_code == 0
    assert "发票" in r.output or "invoice" in r.output.lower()


def test_invoice_preview_no_write(tmp_path):
    f = _xml(tmp_path / "111.xml", "111")
    r = runner.invoke(app, ["invoice", str(f)])
    assert r.exit_code == 0
    assert "预览" in r.output or "111" in r.output
    # 未加 --yes 不写文件
    assert not (tmp_path / "发票结果.xlsx").exists()


def test_invoice_export_excel_with_yes(tmp_path):
    f = _xml(tmp_path / "222.xml", "222")
    out = tmp_path / "out.xlsx"
    r = runner.invoke(
        app, ["invoice", str(f), "--format", "excel", "--output", str(out), "--yes"]
    )
    assert r.exit_code == 0, r.output
    assert out.exists()


def test_invoice_export_json(tmp_path):
    f = _xml(tmp_path / "333.xml", "333")
    out = tmp_path / "out.json"
    r = runner.invoke(
        app, ["invoice", str(f), "--format", "json", "--output", str(out), "--yes"]
    )
    assert r.exit_code == 0
    assert out.exists()
    assert "333" in out.read_text(encoding="utf-8")


def test_invoice_no_files_errors(tmp_path):
    r = runner.invoke(app, ["invoice"])
    assert r.exit_code == 1
    assert "文件" in r.output
