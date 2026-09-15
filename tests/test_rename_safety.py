"""#78:真实临时文件的计划、结果、无覆盖与持久化撤销契约。"""

import errno
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from file_toolbox.cli.main import app
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core import rename_execution
from file_toolbox.core.batch_rename import FileRenameService
from file_toolbox.core.rename_execution import PlanState


def make_batch(tmp_path):
    store = JsonHistoryStore(tmp_path / "history")
    svc = FileRenameService(store)
    sources = [tmp_path / "a.txt", tmp_path / "b.txt"]
    targets = [tmp_path / "x.txt", tmp_path / "y.txt"]
    for i, source in enumerate(sources):
        source.write_text(str(i))
    result = svc.execute_rename_result(dict(zip(sources, targets, strict=True)))
    assert result.count == 2 and not result.messages
    return store, svc, sources, targets


def test_duplicate_plan_and_direct_execution_reject_all(tmp_path):
    a, b, x = (tmp_path / name for name in ("a.txt", "b.txt", "x.txt"))
    a.write_text("a")
    b.write_text("b")
    store = JsonHistoryStore(tmp_path / "history")
    svc = FileRenameService(store)
    ops = [{"type": "regex_replace", "params": {"pattern": ".+", "replace": "x"}}]
    plan = svc.plan_operations([a, b], ops)
    assert [entry.state for entry in plan.values()] == [PlanState.CONFLICT] * 2
    result = svc.execute_rename_result({a: x, b: x})
    assert result.count == 0 and len(result.errors) == 2
    assert a.read_text() == "a" and b.read_text() == "b" and not x.exists()
    assert store.get_records("rename") == []


@pytest.mark.parametrize("text", ["../x", "dir/x", "dir\\x", "/absolute", "bad\x00name"])
def test_output_path_is_not_a_filename(tmp_path, text):
    source = tmp_path / "a.txt"
    source.write_text("a")
    entry = FileRenameService().plan_operations(
        [source], [{"type": "add_prefix", "params": {"text": text}}]
    )[source]
    assert entry.state == PlanState.INVALID
    assert source.read_text() == "a"


def test_noop_does_not_enter_history(tmp_path):
    source = tmp_path / "a.txt"
    source.write_text("a")
    store = JsonHistoryStore(tmp_path / "history")
    svc = FileRenameService(store)
    assert svc.plan_operations([source], [])[source].state == PlanState.NOOP
    assert svc.execute_rename({source: source}) == (0, [])
    assert store.get_records("rename") == []


def test_partial_result_and_history_are_actual_successes(tmp_path):
    source, missing = tmp_path / "a.txt", tmp_path / "missing.txt"
    source.write_text("a")
    store = JsonHistoryStore(tmp_path / "history")
    result = FileRenameService(store).execute_rename_result(
        {source: tmp_path / "x.txt", missing: tmp_path / "y.txt"}
    )
    assert result.successful == {source: tmp_path / "x.txt"}
    assert len(result.errors) == 1 and str(missing) in result.errors[0]
    data = store.get_record("rename", 1)["data"]
    assert data["rename_map"] == {str(source): str(tmp_path / "x.txt")}
    assert set(data["file_ids"]) == {str(source)}


def test_target_created_after_plan_is_not_overwritten(tmp_path, monkeypatch):
    source, target = tmp_path / "a.txt", tmp_path / "x.txt"
    source.write_text("original")
    real = rename_execution.rename_no_replace

    def raced_move(src, dst):
        dst.write_text("other writer")
        real(src, dst)

    monkeypatch.setattr(rename_execution, "rename_no_replace", raced_move)
    result = FileRenameService().execute_rename_result({source: target})
    assert result.count == 0 and result.errors
    assert source.read_text() == "original" and target.read_text() == "other writer"


def test_history_failure_preserves_completed_result(tmp_path, monkeypatch):
    store = JsonHistoryStore(tmp_path / "history")
    source, target = tmp_path / "a.txt", tmp_path / "x.txt"
    source.write_text("a")
    monkeypatch.setattr(
        store, "add_record", lambda *args: (_ for _ in ()).throw(OSError("history unavailable"))
    )
    result = FileRenameService(store).execute_rename_result({source: target})
    assert result.successful == {source: target} and not result.errors
    assert "文件已操作 1 个,历史未保存" in result.history_error
    assert target.read_text() == "a" and not source.exists()


def test_partial_undo_retries_only_remaining_and_rejects_repeat(tmp_path):
    store, svc, sources, targets = make_batch(tmp_path)
    sources[1].write_text("collision")
    first = svc.undo_record(1)
    assert first.count == 1 and first.errors
    record = store.get_record("rename", 1)
    assert not record["undone"]
    assert record["data"]["undo_remaining"] == [str(sources[1])]
    assert sources[1].read_text() == "collision" and targets[1].read_text() == "1"
    sources[1].unlink()
    second = FileRenameService(store).undo_record(1)
    assert second.successful == {targets[1]: sources[1]}
    assert store.get_record("rename", 1)["undone"]
    third = svc.undo_record(1)
    assert third.count == 0 and "已经撤销" in third.errors[0]
    assert [p.read_text() for p in sources] == ["0", "1"]


def test_replaced_file_is_not_moved(tmp_path):
    store, svc, sources, targets = make_batch(tmp_path)
    targets[0].rename(tmp_path / "kept-original.txt")
    targets[0].write_text("replacement")
    result = svc.undo_record(1)
    assert result.count == 1 and any("被替换" in error for error in result.errors)
    assert targets[0].read_text() == "replacement" and not sources[0].exists()
    assert not store.get_record("rename", 1)["undone"]


def test_legacy_record_is_readable_but_undo_refused(tmp_path):
    store = JsonHistoryStore(tmp_path / "history")
    source, target = tmp_path / "a.txt", tmp_path / "x.txt"
    target.write_text("unknown ownership")
    store.add_record("rename", {"rename_map": {str(source): str(target)}})
    result = FileRenameService(store).undo_record(1)
    assert result.count == 0 and "旧格式" in result.errors[0]
    assert target.read_text() == "unknown ownership" and not source.exists()
    assert not store.get_record("rename", 1)["undone"]


@pytest.mark.parametrize("failure_call, expected_count", [(1, 0), (2, 0), (3, 1)])
def test_undo_history_failure_before_and_after_move_is_recoverable(
    tmp_path, monkeypatch, failure_call, expected_count
):
    store, svc, sources, targets = make_batch(tmp_path)
    real = store.update_record_data
    calls = 0

    def failing_save(*args):
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError("checkpoint unavailable")
        real(*args)

    with monkeypatch.context() as m:
        m.setattr(store, "update_record_data", failing_save)
        result = svc.undo_record(1)
    assert result.count == expected_count and result.history_error
    assert targets[1].exists(), "保存失败必须停止后续文件操作"
    assert not store.get_record("rename", 1)["undone"]
    retried = svc.undo_record(1)
    assert retried.count == 2 - expected_count and not retried.messages
    assert [p.read_text() for p in sources] == ["0", "1"]
    assert store.get_record("rename", 1)["undone"]


def test_undo_target_race_is_no_clobber(tmp_path, monkeypatch):
    store, svc, sources, targets = make_batch(tmp_path)
    real = rename_execution.rename_no_replace

    def raced_move(src, dst):
        if dst == sources[0]:
            dst.write_text("new occupant")
        real(src, dst)

    monkeypatch.setattr(rename_execution, "rename_no_replace", raced_move)
    result = svc.undo_record(1)
    assert result.count == 1 and result.errors
    assert sources[0].read_text() == "new occupant" and targets[0].read_text() == "0"
    assert not store.get_record("rename", 1)["undone"]


def test_cli_dry_run_and_duplicate_targets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("a")
    b.write_text("b")
    args = ["rename", str(a), str(b), "--op", 'regex_replace:pattern=".+",replace=x']
    preview = CliRunner().invoke(app, args)
    assert preview.exit_code == 0 and "冲突 2" in preview.output
    actual = CliRunner().invoke(app, args + ["--yes"])
    assert "已重命名 0" in actual.output
    assert a.exists() and b.exists() and not (tmp_path / "x.txt").exists()


def test_cli_history_failure_describes_already_moved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a = tmp_path / "a.txt"
    a.write_text("a")
    with patch.object(JsonHistoryStore, "add_record", side_effect=OSError("history unavailable")):
        result = CliRunner().invoke(app, ["rename", str(a), "--op", "add_prefix:text=P_", "--yes"])
    assert "已重命名 1" in result.output and "历史未保存" in result.output
    assert (tmp_path / "P_a.txt").exists()


def test_missing_record_update_is_not_success(tmp_path):
    store = JsonHistoryStore(tmp_path)
    with pytest.raises(ValueError, match="不存在"):
        store.update_record_data("rename", 99, {})


def test_native_adapter_errors_do_not_fall_back_to_overwriting(tmp_path, monkeypatch):
    class FakeCall:
        def __call__(self, *args):
            return -1

    class FakeLib:
        renameat2 = FakeCall()
        renamex_np = FakeCall()

    monkeypatch.setattr(rename_execution.ctypes, "CDLL", lambda *a, **k: FakeLib())
    monkeypatch.setattr(rename_execution.ctypes, "get_errno", lambda: errno.EEXIST)
    for platform in ("linux", "darwin"):
        with monkeypatch.context() as m:
            m.setattr(rename_execution.sys, "platform", platform)
            with pytest.raises(FileExistsError):
                rename_execution.rename_no_replace(tmp_path / "a", tmp_path / "b")
