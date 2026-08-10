"""考勤方案存储测试。"""

import json
from pathlib import Path

import pytest

from file_toolbox.core.attendance import (
    AttendancePlan,
    AttendancePlanStore,
    CellRef,
    SourceLayout,
    TargetLayout,
)


def _plan(name: str = "市场部") -> AttendancePlan:
    return AttendancePlan(
        name=name,
        template_path=Path("template.xlsx"),
        source=SourceLayout(
            "Sheet1", CellRef.parse("A2"), CellRef.parse("C2"), CellRef.parse("G2")
        ),
        target=TargetLayout(
            "出勤明细", CellRef.parse("C7"), CellRef.parse("D7"), "考勤汇总表", CellRef.parse("C8")
        ),
    )


def test_store_save_get_list_delete(tmp_path):
    store = AttendancePlanStore(tmp_path / "plans.json")
    store.save(_plan("B"))
    store.save(_plan("A"))

    assert [plan.name for plan in store.list()] == ["A", "B"]
    assert store.get("A") == _plan("A")
    assert store.delete("A") is True
    assert store.get("A") is None
    assert store.delete("missing") is False


def test_store_requires_explicit_overwrite(tmp_path):
    store = AttendancePlanStore(tmp_path / "plans.json")
    store.save(_plan())
    with pytest.raises(ValueError, match="已存在"):
        store.save(_plan())
    store.save(_plan(), overwrite=True)


def test_store_corrupt_or_invalid_file_falls_back_empty(tmp_path):
    path = tmp_path / "plans.json"
    path.write_text("not json", encoding="utf-8")
    assert AttendancePlanStore(path).list() == []
    path.write_text(json.dumps({"schema_version": 99, "plans": {}}), encoding="utf-8")
    assert AttendancePlanStore(path).list() == []


def test_store_skips_invalid_plan_but_keeps_valid(tmp_path):
    store = AttendancePlanStore(tmp_path / "plans.json")
    store.save(_plan())
    payload = json.loads(store.config_path.read_text(encoding="utf-8"))
    payload["plans"]["bad"] = {"schema_version": 1}
    store.config_path.write_text(json.dumps(payload), encoding="utf-8")
    assert [plan.name for plan in store.list()] == ["市场部"]


def test_store_write_failure_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "plans.json"
    store = AttendancePlanStore(path)

    def fail_replace(source, target):
        raise OSError("locked")

    monkeypatch.setattr("file_toolbox.core.attendance.plan_store.os.replace", fail_replace)
    with pytest.raises(OSError, match="保存考勤方案失败"):
        store.save(_plan())
    assert not (tmp_path / ".plans.json.tmp").exists()
