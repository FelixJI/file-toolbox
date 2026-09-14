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
    """读取跳过损坏行:有效 + 损坏 + 有效 → 返回 2 条(损坏行不进入有效记录视图)。"""
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


def test_get_record_line_missing_id_key_returns_none(tmp_path, caplog):
    """缺 'id' 键的行是无效记录:查询跳过(返回 None)而非抛 KeyError,并记诊断日志。

    旧实现把该行当普通记录读入,get_record 遍历时 rec["id"] 抛 KeyError——
    「名义上不崩、实际必然崩」的错误契约,Issue #77 更正为显式可观察:无效行
    跳过 + logger.warning(含路径/行号,不含记录内容)。
    """
    import logging

    store = JsonHistoryStore(tmp_path)
    f = tmp_path / "rename.jsonl"
    f.write_text(
        '{"no_id": true}\n',  # 合法 JSON,无 id 键
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="file_toolbox.common.history"):
        assert store.get_record("rename", 1) is None
        assert store.get_records("rename") == []
    assert "line=1" in caplog.text
    assert str(f) in caplog.text
    # 诊断日志不得回显记录内容
    assert "no_id" not in caplog.text


def test_last_id_falls_back_to_full_scan_when_last_line_corrupt(tmp_path):
    """末行损坏:max 有效 id 来自全量有效记录扫描 → add_record 返回 max+1。"""
    store = JsonHistoryStore(tmp_path)
    f = tmp_path / "rename.jsonl"
    f.write_text(
        '{"id": 5, "timestamp": "t", "data": {}, "undone": false}\n{corrupt trailing line}\n',
        encoding="utf-8",
    )
    rid = store.add_record("rename", {"v": 1})
    assert rid == 6  # max(id)=5 回退后 +1


def test_get_record_returns_none_when_id_missing(tmp_path):
    """get_record 找不到 id → None。"""
    store = JsonHistoryStore(tmp_path)
    store.add_record("rename", {"v": 1})
    assert store.get_record("rename", 999) is None


def test_read_all_returns_empty_when_file_missing(tmp_path):
    """历史文件不存在 → 读取直接返回 []。"""
    store = JsonHistoryStore(tmp_path)
    assert store.get_records("never_written") == []
    assert store.get_record("never_written", 1) is None


def test_last_id_returns_zero_when_file_only_blank_lines(tmp_path):
    """文件存在但全是空行 → 无有效记录、最大有效 id 为 0,
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


# =====================================================================================
# Issue #77 回归:跨进程/跨实例并发一致性、损坏行保留与显式日志、写失败保留旧文件。
# =====================================================================================
import logging  # noqa: E402
import multiprocessing  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402


def _spawn_add_child(history_dir: Path, barrier, index: int) -> None:
    """spawn 子进程:barrier 对齐后各追加一条记录(真实进程,无 monkeypatch)。"""
    store = JsonHistoryStore(history_dir)
    barrier.wait(timeout=15)
    store.add_record("rename", {"child": index})


class TestCrossProcessConsistency:
    def test_spawn_two_processes_add_add_unique_ids(self, tmp_path):
        """真实双进程 spawn 同时 add:id 必须唯一(旧实现双读旧快照得 [1,1])。"""
        ctx = multiprocessing.get_context("spawn")
        barrier = ctx.Barrier(2)
        children = [
            ctx.Process(target=_spawn_add_child, args=(tmp_path, barrier, i)) for i in range(2)
        ]
        for child in children:
            child.start()
        try:
            for child in children:
                child.join(timeout=20)
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join()
        assert [child.exitcode for child in children] == [0, 0]
        ids = sorted(r["id"] for r in JsonHistoryStore(tmp_path).get_records("rename"))
        assert ids == [1, 2]


class TestCrossInstanceConsistency:
    def test_two_instances_add_and_mark_no_lost_update(self, tmp_path, store_lock_probe):
        """mark 已读取快照但尚未替换时,另一个实例的 add 必须真实竞争同一锁。"""
        from file_toolbox.common import history

        first = JsonHistoryStore(tmp_path)
        second = JsonHistoryStore(tmp_path)
        first.add_record("rename", {"initial": True})
        reached_write = threading.Event()
        proceed = threading.Event()
        contended, progressed = store_lock_probe
        original = history._replace_file

        def gated_write(target, lines):
            reached_write.set()
            assert proceed.wait(5)
            original(target, lines)

        with (
            patch.object(history, "_replace_file", side_effect=gated_write),
            ThreadPoolExecutor(2) as pool,
        ):
            writer = pool.submit(first.mark_undone, "rename", 1)
            try:
                assert reached_write.wait(5)
                contender = pool.submit(second.add_record, "rename", {"concurrent": True})
                contender.add_done_callback(lambda _: progressed.set())
                assert progressed.wait(5), "竞争者必须到达真实锁竞争或完成事务"
                assert contended.is_set(), "mark 未提交时 add 必须被真实锁拒绝即时获取"
                assert not contender.done()
            finally:
                proceed.set()
            writer.result(timeout=5)
            assert contender.result(timeout=5) == 2
        records = second.get_records("rename")
        assert [r["id"] for r in records] == [1, 2]
        assert records[0]["undone"] is True
        assert records[1]["undone"] is False

    def test_two_instances_concurrent_add_unique_ids(self, tmp_path, store_lock_probe):
        """第一个 add 读完最大 id 尚未追加时,第二个 add 不能读取旧快照。"""
        first = JsonHistoryStore(tmp_path)
        second = JsonHistoryStore(tmp_path)
        read_id = threading.Event()
        proceed = threading.Event()
        contended, progressed = store_lock_probe
        original = first._last_id

        def gated_last_id(tool):
            rid = original(tool)
            read_id.set()
            assert proceed.wait(5)
            return rid

        with (
            patch.object(first, "_last_id", side_effect=gated_last_id),
            ThreadPoolExecutor(2) as pool,
        ):
            writer = pool.submit(first.add_record, "pdf", {"tag": "a"})
            try:
                assert read_id.wait(5)
                contender = pool.submit(second.add_record, "pdf", {"tag": "b"})
                contender.add_done_callback(lambda _: progressed.set())
                assert progressed.wait(5), "竞争者必须到达真实锁竞争或完成事务"
                assert contended.is_set(), "id 读取与追加之间必须保持事务锁"
                assert not contender.done()
            finally:
                proceed.set()
            assert writer.result(timeout=5) == 1
            assert contender.result(timeout=5) == 2
        assert [r["id"] for r in first.get_records("pdf")] == [1, 2]

    def test_relative_and_absolute_dirs_share_lock(self, tmp_path, monkeypatch):
        """相对与绝对目录表达指向同一数据根时必须共享同一把锁。"""
        monkeypatch.chdir(tmp_path)
        abs_store = JsonHistoryStore(tmp_path)
        rel_store = JsonHistoryStore(Path("."))
        barrier = threading.Barrier(2)

        def add(store: JsonHistoryStore, tag: str) -> None:
            barrier.wait(5)
            store.add_record("pdf", {"tag": tag})

        threads = [
            threading.Thread(target=add, args=(abs_store, "abs")),
            threading.Thread(target=add, args=(rel_store, "rel")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        ids = sorted(r["id"] for r in abs_store.get_records("pdf"))
        assert ids == [1, 2]

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows 大小写别名目录")
    def test_windows_case_alias_dirs_share_lock(self, tmp_path):
        """Windows 大小写别名目录表达共享同一把锁(锁身份大小写归一)。"""
        alias_dir = Path(str(tmp_path).swapcase())
        stores = [JsonHistoryStore(tmp_path), JsonHistoryStore(alias_dir)]
        barrier = threading.Barrier(2)

        def add(store: JsonHistoryStore, tag: str) -> None:
            barrier.wait(5)
            store.add_record("pdf", {"tag": tag})

        threads = [
            threading.Thread(target=add, args=(stores[0], "real")),
            threading.Thread(target=add, args=(stores[1], "alias")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        ids = sorted(r["id"] for r in stores[0].get_records("pdf"))
        assert ids == [1, 2]


class TestReaderIsolation:
    def test_reader_blocked_until_rewriter_releases(self, tmp_path, store_lock_probe):
        """读者不能进入进行中的重写事务:锁内 replace 挂起期间 get_records 阻塞,
        完成后读到完整替换结果(不再观察到截断空文件中间态)。"""
        writer = JsonHistoryStore(tmp_path)
        reader = JsonHistoryStore(tmp_path)
        writer.add_record("rename", {"v": 1})
        reached_replace = threading.Event()
        proceed = threading.Event()
        real_replace = os.replace
        contended, progressed = store_lock_probe

        def gated_replace(src, dst):
            reached_replace.set()
            assert proceed.wait(5)
            real_replace(src, dst)

        with (
            patch("file_toolbox.common.history.os.replace", side_effect=gated_replace),
            ThreadPoolExecutor(2) as pool,
        ):
            writer_future = pool.submit(writer.mark_undone, "rename", 1)
            try:
                assert reached_replace.wait(5), "写事务应到达锁内 replace 边界"
                reader_future = pool.submit(reader.get_records, "rename")
                reader_future.add_done_callback(lambda _: progressed.set())
                assert progressed.wait(5), "读者必须到达真实锁竞争或完成读取"
                assert contended.is_set(), "重写尚未提交时读者必须真实竞争事务锁"
                assert not reader_future.done()
            finally:
                proceed.set()
            records = reader_future.result(timeout=5)
            writer_future.result(timeout=5)
        assert [r["id"] for r in records] == [1]
        assert records[0]["undone"] is True


class TestCorruptLineHandling:
    @pytest.mark.parametrize(
        "payload",
        [
            '{"no_id": true}',  # 缺 id
            "[]",  # 非对象(数组)
            '"a string"',  # 非对象(字符串)
            '{"id": "bad"}',  # 字符串 id
            '{"id": true}',  # bool id(int 子类,必须排除)
            '{"id": 0}',  # 非正整数
            '{"id": -3}',  # 负整数
            "{not json",  # 损坏 JSON
        ],
    )
    def test_invalid_lines_skipped_and_logged(self, tmp_path, caplog, payload):
        """无效行查询时跳过,并记录含路径/行号的诊断日志(不回显记录内容)。"""
        f = tmp_path / "rename.jsonl"
        f.write_text(payload + "\n", encoding="utf-8")
        store = JsonHistoryStore(tmp_path)
        with caplog.at_level(logging.WARNING, logger="file_toolbox.common.history"):
            assert store.get_records("rename") == []
            assert store.get_record("rename", 1) is None
        assert "line=1" in caplog.text
        assert str(f) in caplog.text
        assert payload not in caplog.text

    def test_mark_undone_preserves_corrupt_lines_and_extra_fields(self, tmp_path):
        """mark 只重写目标行:损坏行、无换行破损尾与额外字段逐行保留。"""
        f = tmp_path / "rename.jsonl"
        f.write_text(
            '{"id": 1, "timestamp": "t", "data": {}, "undone": false, "extra": "keep"}\n'
            "{broken-middle\n"
            '{"id": 2, "timestamp": "t", "data": {"v": 2}, "undone": false}\n'
            "{broken-tail",
            encoding="utf-8",
        )
        JsonHistoryStore(tmp_path).mark_undone("rename", 2)
        lines = f.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 4
        untouched = json.loads(lines[0])
        assert untouched["extra"] == "keep"
        assert untouched["undone"] is False
        assert lines[1] == "{broken-middle"
        marked = json.loads(lines[2])
        assert marked["id"] == 2
        assert marked["undone"] is True
        assert lines[3] == "{broken-tail"

    def test_add_separates_from_unterminated_broken_tail(self, tmp_path):
        """末行破损且无换行:append 前补分隔,新记录独立成行、id 接最大有效值。"""
        f = tmp_path / "rename.jsonl"
        f.write_text(
            '{"id": 1, "timestamp": "t", "data": {}, "undone": false}\n{broken-tail',
            encoding="utf-8",
        )
        rid = JsonHistoryStore(tmp_path).add_record("rename", {"v": 1})
        assert rid == 2
        lines = f.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        assert lines[1] == "{broken-tail"
        assert json.loads(lines[2])["id"] == 2

    def test_add_after_invalid_high_id_line_uses_max_valid(self, tmp_path):
        """id 分配取最大「有效」id:字符串 id 的诱惑值不参与。"""
        f = tmp_path / "rename.jsonl"
        f.write_text(
            '{"id": 5, "timestamp": "t", "data": {}, "undone": false}\n{"id": "99"}\n',
            encoding="utf-8",
        )
        assert JsonHistoryStore(tmp_path).add_record("rename", {}) == 6

    def test_clear_counts_valid_records_and_empties_file(self, tmp_path):
        """clear 是显式清空:计数只含有效记录,清空后文件为空。"""
        f = tmp_path / "rename.jsonl"
        f.write_text(
            '{"id": 1, "timestamp": "t", "data": {}, "undone": false}\n'
            "{broken\n"
            '{"id": 2, "timestamp": "t", "data": {}, "undone": false}\n',
            encoding="utf-8",
        )
        assert JsonHistoryStore(tmp_path).clear("rename") == 2
        assert f.read_text(encoding="utf-8") == ""

    def test_mark_missing_id_leaves_file_unchanged(self, tmp_path):
        """mark 不存在的 id:不改写文件(旧实现仍会无差别全量重写)。"""
        store = JsonHistoryStore(tmp_path)
        store.add_record("rename", {"v": 1})
        f = tmp_path / "rename.jsonl"
        original = f.read_text(encoding="utf-8")
        store.mark_undone("rename", 999)
        assert f.read_text(encoding="utf-8") == original


class TestWriteFailurePreservation:
    def test_mark_serialization_failure_preserves_old_file(self, tmp_path):
        """序列化失败:异常传播,旧文件逐字保留,无临时文件残留。"""
        store = JsonHistoryStore(tmp_path)
        store.add_record("rename", {"v": 1})
        f = tmp_path / "rename.jsonl"
        original = f.read_text(encoding="utf-8")
        with (
            patch("file_toolbox.common.history.json.dumps", side_effect=OSError("injected dumps")),
            pytest.raises(OSError, match="injected dumps"),
        ):
            store.mark_undone("rename", 1)
        assert f.read_text(encoding="utf-8") == original
        assert not list(tmp_path.glob("*.tmp"))

    def test_mark_replace_failure_preserves_old_and_cleans_tmp(self, tmp_path):
        """replace 失败:异常传播,旧文件保留,本次临时文件被清理。"""
        store = JsonHistoryStore(tmp_path)
        store.add_record("rename", {"v": 1})
        f = tmp_path / "rename.jsonl"
        original = f.read_text(encoding="utf-8")
        with (
            patch(
                "file_toolbox.common.history.os.replace", side_effect=OSError("injected replace")
            ),
            pytest.raises(OSError, match="injected replace"),
        ):
            store.mark_undone("rename", 1)
        assert f.read_text(encoding="utf-8") == original
        assert not list(tmp_path.glob("*.tmp"))

    def test_add_serialization_failure_preserves_old_file(self, tmp_path):
        """append 前序列化失败:异常传播,文件保持原样。"""
        store = JsonHistoryStore(tmp_path)
        store.add_record("rename", {"v": 1})
        f = tmp_path / "rename.jsonl"
        original = f.read_text(encoding="utf-8")
        with (
            patch("file_toolbox.common.history.json.dumps", side_effect=OSError("injected dumps")),
            pytest.raises(OSError, match="injected dumps"),
        ):
            store.add_record("rename", {"v": 2})
        assert f.read_text(encoding="utf-8") == original
