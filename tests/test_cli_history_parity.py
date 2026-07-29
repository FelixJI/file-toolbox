"""CLI 历史记录 parity 测试(子项 3.3/3.6)。

验证 5 个 CLI 命令在 --yes 执行后,会把记录写入 cwd/.file_toolbox/history/<tool>.jsonl,
记录形状与 GUI 同源(history_dialog._summary_label 读取的键齐全)。
此为 CLI 与 GUI 现在走同一记录路径的证据。

隔离:monkeypatch.chdir(tmp_path) 让默认 JsonHistoryStore() 落到临时目录,
replace 另需重定向备份目录。PDF 用 PNG 图片走 ImageConverter(不触发 Office COM)。
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from file_toolbox.cli.main import app

runner = CliRunner()

pytest.importorskip("PIL")


def _history_records(tmp_path: Path, tool: str) -> list[dict]:
    """读取 chdir 到 tmp_path 后 CLI 写入的 <tool>.jsonl 全部记录。"""
    f = tmp_path / ".file_toolbox" / "history" / f"{tool}.jsonl"
    assert f.exists(), f"{tool}.jsonl 未生成(CLI 未记录历史)"
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


# ============================ rename ============================


def test_cli_rename_records_history(tmp_path, monkeypatch):
    """rename --yes 执行后 rename.jsonl 含 {"rename_map": {str: str}}。"""
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "a.txt"
    f.write_text("x")
    r = runner.invoke(app, ["rename", str(f), "--op", "add_prefix:text=P_", "--yes"])
    assert r.exit_code == 0, r.output

    records = _history_records(tmp_path, "rename")
    assert len(records) == 1
    data = records[0]["data"]
    assert "rename_map" in data
    assert data["rename_map"] == {str(f): str(tmp_path / "P_a.txt")}


# ============================ replace ============================


def test_cli_replace_records_history(tmp_path, monkeypatch):
    """replace --yes 执行后 replace.jsonl 含 {"files": [...], "operations": [...]}。"""
    monkeypatch.chdir(tmp_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "file_toolbox.core.batch_replace.service.get_backup_dir", lambda: backup_dir
    )
    f = tmp_path / "a.txt"
    f.write_text("foo", encoding="utf-8")
    r = runner.invoke(
        app, ["replace", str(f), "--op", "simple_replace:find=foo,replace=bar", "--yes"]
    )
    assert r.exit_code == 0, r.output

    records = _history_records(tmp_path, "replace")
    assert len(records) == 1
    data = records[0]["data"]
    assert data["files"] == [str(f)]
    assert data["operations"] == [
        {"type": "simple_replace", "params": {"find": "foo", "replace": "bar"}}
    ]


# ============================ pdf ============================


def test_cli_pdf_records_history(tmp_path, monkeypatch):
    """pdf 命令执行后 pdf.jsonl 含 {files/success/failed/config}(PNG 不走 COM)。"""
    from PIL import Image

    monkeypatch.chdir(tmp_path)
    src = tmp_path / "photo.png"
    Image.new("RGB", (10, 10), (255, 0, 0)).save(str(src))
    r = runner.invoke(
        app, ["pdf", str(src), "--pdf-type", "editable", "--engine", "auto", "--dpi", "150"]
    )
    assert r.exit_code == 0, r.output

    records = _history_records(tmp_path, "pdf")
    assert len(records) == 1
    data = records[0]["data"]
    assert data["files"] == [str(src)]
    assert data["success"] == 1
    assert data["failed"] == 0
    assert set(data["config"].keys()) == {"pdf_type", "output_mode", "engine", "dpi"}
    assert data["config"]["dpi"] == 150


# ============================ mkdir ============================


def test_cli_mkdir_records_history(tmp_path, monkeypatch):
    """mkdir 执行后 mkdir.jsonl 含 {root/structure_count/strategy/created/skipped/success}。"""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "root"
    r = runner.invoke(
        app, ["mkdir", "--root", str(root), "--levels", "项目A/文档", "--on-conflict", "merge"]
    )
    assert r.exit_code == 0, r.output

    records = _history_records(tmp_path, "mkdir")
    assert len(records) == 1
    data = records[0]["data"]
    assert data["root"] == str(root)
    assert data["structure_count"] == 1
    assert data["strategy"] == "MERGE"
    # "项目A/文档" 为 1 个结构 → build_folder_paths 生成 1 个叶节点 item(mkdir parents=True
    # 一并建出父级),故 created_count 计的是 item 数 = 1
    assert data["created"] == 1
    assert data["skipped"] == 0
    assert data["success"] is True


# ============================ invoice ============================


def test_cli_invoice_records_history(tmp_path, monkeypatch, ofd_sample):
    """invoice --yes 导出后 invoice.jsonl 含 {file_count/invoice_count/dedupe_strategy/fmt/outputs}。"""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "结果.xlsx"
    r = runner.invoke(
        app, ["invoice", str(ofd_sample), "--format", "excel", "--output", str(out), "--yes"]
    )
    assert r.exit_code == 0, r.output

    records = _history_records(tmp_path, "invoice")
    assert len(records) == 1
    data = records[0]["data"]
    assert data["file_count"] == 1
    assert data["invoice_count"] == 1
    assert data["dedupe_strategy"] == "keep_all"
    assert data["fmt"] == "excel"
    assert data["outputs"] == [str(out)]
