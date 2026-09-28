"""更新运行态探针与数据根 policy 快照(#128 版本身份/对账支撑)。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from file_toolbox.updater import runtime_support
from file_toolbox.updater.runtime_support import (
    UpdateRuntimeState,
    packaged_version,
    probe_update_runtime,
)


class _FakeManager(SimpleNamespace): ...


def _manager(
    current: str = "0.3.5",
    portable: bool = True,
    pending: str | None = None,
) -> Any:
    return _FakeManager(
        get_current_version=lambda: current,
        get_is_portable=lambda: portable,
        get_update_pending_restart=lambda: (
            SimpleNamespace(Version=pending) if pending is not None else None
        ),
    )


def test_probe_reads_manager_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime_support, "_new_manager", lambda: _manager(current="0.3.6", pending="0.3.7")
    )

    state = probe_update_runtime()

    assert state == UpdateRuntimeState(
        available=True,
        current_version="0.3.6",
        is_portable=True,
        pending_restart_version="0.3.7",
        error="",
    )


def test_probe_maps_sdk_failure_to_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> Any:
        raise RuntimeError("This application is not properly installed")

    monkeypatch.setattr(runtime_support, "_new_manager", broken)

    state = probe_update_runtime()

    assert state.available is False
    assert state.current_version == ""
    assert "not properly installed" in state.error


def test_packaged_version_returns_none_without_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime_support,
        "probe_update_runtime",
        lambda: UpdateRuntimeState(False, "", False, None, "no manifest"),
    )

    assert packaged_version() is None


def test_packaged_version_returns_locator_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime_support,
        "probe_update_runtime",
        lambda: UpdateRuntimeState(True, "0.3.6", True, None, ""),
    )

    assert packaged_version() == "0.3.6"


def test_runtime_version_prefers_locator_then_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from file_toolbox.common import metadata

    monkeypatch.setattr("file_toolbox.updater.runtime_support.packaged_version", lambda: "9.9.9")
    assert metadata.runtime_version() == "9.9.9"

    monkeypatch.setattr("file_toolbox.updater.runtime_support.packaged_version", lambda: None)
    assert metadata.runtime_version() == metadata.VERSION


def test_current_data_root_policy_snapshot(tmp_path: Path) -> None:
    """ContextVar 不随线程继承:worker 侧须用捕获的 policy 重新进入上下文。"""
    from file_toolbox.common.paths import (
        CliDataRootPolicy,
        GuiDataRootPolicy,
        current_data_root_policy,
        use_data_root_policy,
    )

    policy = GuiDataRootPolicy(tmp_path)
    with use_data_root_policy(policy):
        assert current_data_root_policy() is policy
        # 模拟 worker 线程:捕获快照后在新上下文中恢复(无继承)
        captured = current_data_root_policy()
    with use_data_root_policy(captured):
        from file_toolbox.common.paths import current_data_root

        assert current_data_root() == tmp_path / ".file_toolbox"

    assert isinstance(current_data_root_policy(), CliDataRootPolicy)
