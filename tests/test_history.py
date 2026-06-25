import json
from pathlib import Path

from file_toolbox.common.history import JsonHistoryStore


def test_add_and_get_record(tmp_path):
    store = JsonHistoryStore(tmp_path)
    rid = store.add_record("rename", {"rename_map": {"a": "b"}, "operations": []})
    records = store.get_records("rename")
    assert len(records) == 1
    assert records[0]["id"] == rid
    assert records[0]["data"]["rename_map"] == {"a": "b"}


def test_multiple_records_increment_id(tmp_path):
    store = JsonHistoryStore(tmp_path)
    r1 = store.add_record("rename", {"x": 1})
    r2 = store.add_record("rename", {"x": 2})
    assert r2 == r1 + 1


def test_separate_tools_separate_files(tmp_path):
    store = JsonHistoryStore(tmp_path)
    store.add_record("rename", {"a": 1})
    store.add_record("replace", {"b": 2})
    assert len(store.get_records("rename")) == 1
    assert len(store.get_records("replace")) == 1


def test_get_single_record(tmp_path):
    store = JsonHistoryStore(tmp_path)
    rid = store.add_record("rename", {"v": 9})
    rec = store.get_record("rename", rid)
    assert rec is not None
    assert rec["data"]["v"] == 9


def test_mark_undone(tmp_path):
    store = JsonHistoryStore(tmp_path)
    rid = store.add_record("rename", {"v": 1})
    store.mark_undone("rename", rid)
    rec = store.get_record("rename", rid)
    assert rec["undone"] is True


def test_clear(tmp_path):
    store = JsonHistoryStore(tmp_path)
    store.add_record("rename", {"v": 1})
    store.add_record("rename", {"v": 2})
    n = store.clear("rename")
    assert n == 2
    assert store.get_records("rename") == []


def test_limit(tmp_path):
    store = JsonHistoryStore(tmp_path)
    for i in range(5):
        store.add_record("rename", {"i": i})
    assert len(store.get_records("rename", limit=3)) == 3


def test_persists_to_jsonl(tmp_path):
    store = JsonHistoryStore(tmp_path)
    store.add_record("rename", {"v": 1})
    f = tmp_path / "rename.jsonl"
    assert f.exists()
    lines = f.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["data"]["v"] == 1


def test_default_history_dir(monkeypatch, tmp_path):
    # 不传 history_dir 时应使用 paths.get_history_dir()（cwd 下 .file_toolbox/history）
    monkeypatch.chdir(tmp_path)
    import importlib

    from file_toolbox.common import paths

    importlib.reload(paths)
    store = JsonHistoryStore()
    store.add_record("pdf", {"out": "x.pdf"})
    assert (tmp_path / ".file_toolbox" / "history" / "pdf.jsonl").exists()
