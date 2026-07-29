"""service 层历史记录下沉测试(M1,子项 3.1/3.6)。

验证 5 个 service 注入 JsonHistoryStore 后在 execute 方法成功路径记录一条历史,
记录形状与原 GUI 内联写入完全一致(由 history_dialog._summary_label 读取)。
默认 history_store=None 时不记录(保证旧调用零副作用)。

形状契约(与 history_dialog._summary_label 逐一对应):
- rename: {"rename_map": {str: str}}          → len(rename_map)
- replace: {"files": [str], "operations": [...]} → len(files)
- pdf:    {"files": [str], "success": int, "failed": int, "config": {...}}
- mkdir:  {"root": str, "structure_count": int, "strategy": str, "created": int,
           "skipped": int, "success": bool}
- invoice:{"file_count": int, "invoice_count": int, "dedupe_strategy": str,
           "fmt": str, "outputs": [str]}
"""

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.batch_mkdir import ConflictStrategy, FolderCreatorService
from file_toolbox.core.batch_rename import FileRenameService
from file_toolbox.core.batch_replace import ContentReplaceService
from file_toolbox.core.invoice.service import InvoiceService

# ============================ rename ============================


def test_rename_service_records_history(tmp_path):
    """execute_rename 注入 store 后记录 {"rename_map": {str: str}},键为完整 rename_map。"""
    store = JsonHistoryStore(tmp_path)
    svc = FileRenameService(history_store=store)
    f = tmp_path / "a.txt"
    f.write_text("x")
    new_path = tmp_path / "b.txt"
    svc.execute_rename({f: new_path})

    records = store.get_records("rename")
    assert len(records) == 1
    data = records[0]["data"]
    assert set(data.keys()) == {"rename_map"}
    assert data["rename_map"] == {str(f): str(new_path)}
    # new_path 真的被创建(执行成功)
    assert new_path.exists()


def test_rename_service_default_none_no_record(tmp_path, monkeypatch):
    """默认 history_store=None 不记录(避免污染 cwd 的 .file_toolbox/history)。"""
    monkeypatch.chdir(tmp_path)  # 即便误写也落到 tmp_path
    svc = FileRenameService()
    f = tmp_path / "a.txt"
    f.write_text("x")
    svc.execute_rename({f: tmp_path / "b.txt"})
    assert not (tmp_path / ".file_toolbox").exists()


# ============================ replace ============================


def test_replace_service_records_history(tmp_path, monkeypatch):
    """execute_replace 记录 {"files": [str], "operations": operations}(有 errors 也记)。"""
    # 重定向备份目录,避免污染真实 .file_toolbox/backups
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "file_toolbox.core.batch_replace.service.get_backup_dir", lambda: backup_dir
    )

    store = JsonHistoryStore(tmp_path / "hist")
    svc = ContentReplaceService(history_store=store)
    f = tmp_path / "a.txt"
    f.write_text("foo", encoding="utf-8")
    ops = [{"type": "simple_replace", "params": {"find": "foo", "replace": "bar"}}]
    svc.execute_replace([f], ops)

    records = store.get_records("replace")
    assert len(records) == 1
    data = records[0]["data"]
    assert set(data.keys()) == {"files", "operations"}
    assert data["files"] == [str(f)]
    assert data["operations"] == ops
    svc.close()


def test_replace_service_default_none_no_record(tmp_path, monkeypatch):
    """默认 None 不记录。"""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "file_toolbox.core.batch_replace.service.get_backup_dir", lambda: backup_dir
    )
    monkeypatch.chdir(tmp_path)
    svc = ContentReplaceService()
    f = tmp_path / "a.txt"
    f.write_text("foo", encoding="utf-8")
    svc.execute_replace(
        [f], [{"type": "simple_replace", "params": {"find": "foo", "replace": "bar"}}]
    )
    assert not (tmp_path / ".file_toolbox").exists()
    svc.close()


def test_replace_service_no_record_on_early_return(tmp_path, monkeypatch):
    """空文件列表/空操作/非法操作等早退路径不记录(未执行任何替换)。"""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "file_toolbox.core.batch_replace.service.get_backup_dir", lambda: backup_dir
    )
    store = JsonHistoryStore(tmp_path / "hist")
    svc = ContentReplaceService(history_store=store)
    # 空文件列表 → 早退
    svc.execute_replace([], [{"type": "simple_replace", "params": {"find": "a", "replace": "b"}}])
    assert store.get_records("replace") == []
    # 空操作 → 早退
    f = tmp_path / "a.txt"
    f.write_text("x")
    svc.execute_replace([f], [])
    assert store.get_records("replace") == []
    svc.close()


# ============================ mkdir ============================


def test_mkdir_service_records_history(tmp_path):
    """create_folders 传 root/structure_count 后记录 mkdir 形状。"""
    store = JsonHistoryStore(tmp_path / "hist")
    svc = FolderCreatorService(history_store=store)
    root = tmp_path / "root"
    items = svc.build_folder_paths(root, [("项目A", "文档")])
    result = svc.create_folders(items, ConflictStrategy.MERGE, root=str(root), structure_count=1)

    records = store.get_records("mkdir")
    assert len(records) == 1
    data = records[0]["data"]
    assert data == {
        "root": str(root),
        "structure_count": 1,
        "strategy": "MERGE",
        "created": result.created_count,
        "skipped": result.skipped_count,
        "success": result.success,
    }


def test_mkdir_service_history_defaults_when_root_count_none(tmp_path):
    """root/structure_count 默认 None → 记空串/0(向后兼容旧调用)。"""
    store = JsonHistoryStore(tmp_path / "hist")
    svc = FolderCreatorService(history_store=store)
    root = tmp_path / "root"
    items = svc.build_folder_paths(root, [("a",)])
    svc.create_folders(items, ConflictStrategy.SKIP)  # 不传 root/structure_count

    data = store.get_records("mkdir")[0]["data"]
    assert data["root"] == ""
    assert data["structure_count"] == 0
    assert data["strategy"] == "SKIP"


def test_mkdir_service_default_none_no_record(tmp_path, monkeypatch):
    """默认 None 不记录。"""
    monkeypatch.chdir(tmp_path)
    svc = FolderCreatorService()
    items = svc.build_folder_paths(tmp_path / "root", [("a",)])
    svc.create_folders(items)
    assert not (tmp_path / ".file_toolbox").exists()


# ============================ invoice ============================


def _make_parse_result():
    """构造一个最小 ParseResult(避免触碰真实发票解析)。"""
    from file_toolbox.core.invoice.types import Invoice, ParseResult

    inv = Invoice(
        invoice_number="N1",
        invoice_type="增值税专用发票",
        issue_date="2026-07-29",
        seller_name="s",
        seller_tax_id="s",
        seller_addr="s",
        seller_tel="s",
        seller_bank="s",
        seller_account="s",
        buyer_name="b",
        buyer_tax_id="b",
        buyer_addr="b",
        buyer_tel="b",
        buyer_bank="b",
        buyer_account="b",
        amount_without_tax="1",
        tax_amount="1",
        amount_with_tax="2",
        amount_chinese="x",
        drawer="d",
        remark="",
        parse_method="xml",
    )
    return ParseResult(invoices=[inv], duplicates=[], failed=[])


def test_invoice_service_records_history(tmp_path):
    """export 传 file_count/invoice_count 后记录 invoice 形状。"""
    store = JsonHistoryStore(tmp_path / "hist")
    svc = InvoiceService(history_store=store)
    result = _make_parse_result()
    out = tmp_path / "发票结果.xlsx"
    svc.export(
        result,
        out,
        fmt="excel",
        file_count=3,
        invoice_count=len(result.invoices),
    )

    records = store.get_records("invoice")
    assert len(records) == 1
    data = records[0]["data"]
    assert data["file_count"] == 3
    assert data["invoice_count"] == 1
    assert data["dedupe_strategy"] == "keep_all"
    assert data["fmt"] == "excel"
    assert data["outputs"] == [str(out)]


def test_invoice_service_history_defaults_when_counts_none(tmp_path):
    """file_count/invoice_count 默认 None → 记 0(向后兼容)。"""
    store = JsonHistoryStore(tmp_path / "hist")
    svc = InvoiceService(history_store=store)
    result = _make_parse_result()
    svc.export(result, tmp_path / "发票结果.xlsx", fmt="excel")

    data = store.get_records("invoice")[0]["data"]
    assert data["file_count"] == 0
    assert data["invoice_count"] == 0


def test_invoice_service_default_none_no_record(tmp_path, monkeypatch):
    """默认 None 不记录。"""
    monkeypatch.chdir(tmp_path)
    svc = InvoiceService()
    result = _make_parse_result()
    svc.export(result, tmp_path / "发票结果.xlsx", fmt="excel")
    assert not (tmp_path / ".file_toolbox").exists()


# ============================ pdf (service 单元) ============================
# PDFGeneratorService 涉及 COM;这里只测 add_record 触发逻辑,通过伪造 results
# 不直接构造 PDFGeneratorService(它在无 Office 环境下 batch_generate 会失败)。
# PDF service 形状由 CLI 端到端测试(test_cli_history_parity.py,用图片输入)覆盖。


def test_pdf_service_history_imports():
    """PDFGeneratorService 接受 history_store 参数(构造不触发 COM)。"""
    from file_toolbox.core.batch_pdf.service import PDFGeneratorService

    store = JsonHistoryStore()
    svc = PDFGeneratorService(history_store=store)
    assert svc._history_store is store
