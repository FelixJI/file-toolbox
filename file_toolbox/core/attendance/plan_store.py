"""考勤方案的严格、原子 JSON 存储。"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from file_toolbox.common.paths import get_data_dir
from file_toolbox.core.attendance.types import AttendancePlan, plan_from_dict, plan_to_dict


class AttendancePlanStore:
    """以方案名称为键保存 AttendancePlan。"""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or (get_data_dir() / "attendance_plans.json")

    def _load(self) -> dict[str, AttendancePlan]:
        if not self.config_path.exists():
            return {}
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, Mapping) or raw.get("schema_version") != 1:
            return {}
        plans_raw = raw.get("plans")
        if not isinstance(plans_raw, Mapping):
            return {}
        plans: dict[str, AttendancePlan] = {}
        for value in plans_raw.values():
            try:
                plan = plan_from_dict(value)
            except ValueError:
                continue
            plans[plan.name] = plan
        return plans

    def _write(self, plans: Mapping[str, AttendancePlan]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.config_path.with_name(f".{self.config_path.name}.tmp")
        payload = {
            "schema_version": 1,
            "plans": {name: plan_to_dict(plan) for name, plan in sorted(plans.items())},
        }
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temp_path, self.config_path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise OSError(f"保存考勤方案失败: {exc}") from exc

    def list(self) -> list[AttendancePlan]:
        return sorted(self._load().values(), key=lambda plan: plan.name)

    def get(self, name: str) -> AttendancePlan | None:
        return self._load().get(name)

    def save(self, plan: AttendancePlan, *, overwrite: bool = False) -> None:
        plans = self._load()
        if plan.name in plans and not overwrite:
            raise ValueError(f"方案已存在: {plan.name}")
        plans[plan.name] = plan
        self._write(plans)

    def delete(self, name: str) -> bool:
        plans = self._load()
        if name not in plans:
            return False
        del plans[name]
        self._write(plans)
        return True
