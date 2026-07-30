import json

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


def test_read_all_skips_corrupt_line(tmp_path):
    """_read_all 跳过损坏行:有效 + 损坏 + 有效 → 返回 2 条(覆盖 33-34 continue)。"""
    store = JsonHistoryStore(tmp_path)
    f = tmp_path / "rename.jsonl"
    f.write_text(
        '{"id": 1, "timestamp": "t", "data": {"a": 1}, "undone": false}\n'
        "{not json\n"
        '{"id": 2, "timestamp": "t", "data": {"a": 2}, "undone": false}\n',
        encoding="utf-8",
    )
    records = store.get_records("rename")
    assert len(records) == 2
    assert [r["id"] for r in records] == [1, 2]


def test_get_record_line_missing_id_key_does_not_crash(tmp_path):
    """合法 JSON 但缺 'id' 键的行 → get_record 查找时 rec["id"] 会 KeyError。

    锁定当前行为:_read_all 把它当普通记录读入,get_record 遍历时对该行 rec["id"]
    抛 KeyError(非静默跳过)。此为已知弱点(部分写入/损坏),记录行为使未来若改为
    「跳过无 id 行」该测试变红。
    """
    store = JsonHistoryStore(tmp_path)
    f = tmp_path / "rename.jsonl"
    f.write_text(
        '{"no_id": true}\n',  # 合法 JSON,无 id 键
        encoding="utf-8",
    )
    import pytest

    with pytest.raises(KeyError):
        store.get_record("rename", 1)


def test_last_id_falls_back_to_full_scan_when_last_line_corrupt(tmp_path):
    """末行损坏:_last_id 回退全量扫描 max id → add_record 返回 max+1(覆盖 60-62)。"""
    store = JsonHistoryStore(tmp_path)
    f = tmp_path / "rename.jsonl"
    f.write_text(
        '{"id": 5, "timestamp": "t", "data": {}, "undone": false}\n{corrupt trailing line}\n',
        encoding="utf-8",
    )
    rid = store.add_record("rename", {"v": 1})
    assert rid == 6  # max(id)=5 回退后 +1


def test_get_record_returns_none_when_id_missing(tmp_path):
    """get_record 找不到 id → None(覆盖 89)。"""
    store = JsonHistoryStore(tmp_path)
    store.add_record("rename", {"v": 1})
    assert store.get_record("rename", 999) is None


def test_read_all_returns_empty_when_file_missing(tmp_path):
    """_read_all 文件不存在 → 直接返回 [](覆盖 26)。"""
    store = JsonHistoryStore(tmp_path)
    assert store.get_records("never_written") == []
    assert store.get_record("never_written", 1) is None


def test_last_id_returns_zero_when_file_only_blank_lines(tmp_path):
    """文件存在但全是空行 → _last_id 走 last_line 为空分支返回 0(覆盖 62),
    add_record 应从 id=1 开始。"""
    store = JsonHistoryStore(tmp_path)
    f = tmp_path / "rename.jsonl"
    f.write_text("   \n\n  \n", encoding="utf-8")  # 仅空白行
    rid = store.add_record("rename", {"v": 1})
    assert rid == 1


def test_get_records_negative_limit_returns_all(tmp_path):
    """limit<=0 一律表示「全部」(docstring 承诺)。

    回归:旧实现 `records[-limit:] if limit else records` 中,`limit=0` 因 falsy
    返回全部(正确),但 `limit<0` 是 truthy → `records[-limit:]` 反向切片,
    丢掉首条记录(3 条 `limit=-1` 误返回 2 条)。负数应与 0 同等处理。
    """
    store = JsonHistoryStore(tmp_path)
    for i in range(3):
        store.add_record("rename", {"i": i})
    assert len(store.get_records("rename", limit=-1)) == 3
    assert len(store.get_records("rename", limit=-5)) == 3
    assert len(store.get_records("rename", limit=0)) == 3


def test_add_record_thread_safe_concurrent(tmp_path):
    """多线程并发 add_record 不丢记录、id 单调无重复(子项 3.2 锁验证)。

    PDF 历史在工作线程(PdfGenerateWorker)内写入;锁保证并发 append 不交错、
    id 不竞态。N 个线程各写 M 条 → 文件应有 N*M 条,且 id 唯一连续。
    """
    import threading

    store = JsonHistoryStore(tmp_path)
    n_threads = 8
    per_thread = 50
    barrier = threading.Barrier(n_threads)

    def worker(wid: int) -> None:
        barrier.wait()  # 尽量同时开始,最大化竞态
        for i in range(per_thread):
            store.add_record("pdf", {"worker": wid, "i": i})

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    records = store.get_records("pdf", limit=0)
    assert len(records) == n_threads * per_thread
    ids = [r["id"] for r in records]
    # id 从 1 开始连续无重复(锁保证 _last_id+1 的读-改-写原子)
    assert ids == list(range(1, n_threads * per_thread + 1))
