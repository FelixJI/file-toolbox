"""FreezeWatchdog/_StallMonitor 的单元测试(注入假时钟与假转储器,不制造真冻结)。"""

import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtCore")

from PySide6.QtWidgets import QApplication

from file_toolbox.gui.freeze_watchdog import FreezeWatchdog, _StallMonitor


class _FakeClock:
    """可手动推进的单调时钟。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _make_monitor(tmp_path: Path, clock: _FakeClock, dumps: list) -> _StallMonitor:
    return _StallMonitor(
        tmp_path / "watch.log",
        threshold_s=10.0,
        clock=clock,
        dumper=lambda **kw: dumps.append(kw),
    )


def test_fresh_heartbeat_never_dumps(tmp_path: Path):
    clock, dumps = _FakeClock(), []
    m = _make_monitor(tmp_path, clock, dumps)
    for _ in range(5):
        clock.advance(2.0)
        m.beat()
        m.check()
    assert dumps == []
    assert not (tmp_path / "watch.log").exists()


def test_check_below_threshold_no_dump(tmp_path: Path):
    clock, dumps = _FakeClock(), []
    m = _make_monitor(tmp_path, clock, dumps)
    clock.advance(9.9)
    m.check()
    assert dumps == []


def test_stall_dumps_once_per_episode(tmp_path: Path):
    clock, dumps = _FakeClock(), []
    m = _make_monitor(tmp_path, clock, dumps)
    clock.advance(10.1)
    m.check()  # 超阈值 → 转储
    m.check()  # 同一冻结周期不重复
    assert len(dumps) == 1
    content = (tmp_path / "watch.log").read_text(encoding="utf-8")
    assert "GUI 主线程疑似冻结" in content
    assert "冻结线程栈转储结束" in content


def test_recovery_records_duration_and_rearms(tmp_path: Path):
    clock, dumps = _FakeClock(), []
    m = _make_monitor(tmp_path, clock, dumps)
    clock.advance(10.5)
    m.check()
    clock.advance(4.5)  # 冻结共 15s 后恢复
    m.beat()
    content = (tmp_path / "watch.log").read_text(encoding="utf-8")
    assert "恢复响应" in content
    assert "15.0s" in content
    # 恢复后进入新的冻结周期 → 再次转储
    clock.advance(10.5)
    m.check()
    assert len(dumps) == 2


def test_dump_failure_swallowed(tmp_path: Path):
    clock = _FakeClock()

    def bad_dumper(**kw) -> None:
        raise RuntimeError("boom")

    m = _StallMonitor(tmp_path / "watch.log", threshold_s=10.0, clock=clock, dumper=bad_dumper)
    clock.advance(10.1)
    m.check()  # 不应抛
    clock.advance(1.0)
    m.beat()  # 恢复路径同样不抛
    log = tmp_path / "watch.log"
    content = log.read_text(encoding="utf-8") if log.exists() else ""
    # 开始标记先落盘(冻结事实留痕),转储器抛错被吞 → 无结束标记,恢复标记仍在
    assert "GUI 主线程疑似冻结" in content
    assert "冻结线程栈转储结束" not in content
    assert "恢复响应" in content


def test_watchdog_start_feeds_heartbeat_via_timer(app, tmp_path: Path):
    wd = FreezeWatchdog(tmp_path / "watch.log", threshold_s=3600.0, heartbeat_interval_s=0.01)
    wd.start(app)
    before = wd.monitor._last_beat
    for _ in range(30):
        app.processEvents()
        time.sleep(0.005)
    assert wd.monitor._last_beat > before
