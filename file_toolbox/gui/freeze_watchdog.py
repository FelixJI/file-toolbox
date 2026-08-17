"""GUI 主线程冻结监视:心跳停滞超阈值时,把全部线程栈直接转储进日志文件。

针对"偶发打开界面卡死且日志无留存":冻结现场无法事后还原,只能让程序在冻结
发生时自己留下证据。设计要点:

- 心跳由 GUI 线程的 QTimer 喂(事件循环卡住即停跳);监视线程为 daemon,
  发现停滞后每个冻结周期只转储一次,恢复时补记冻结时长。
- 转储刻意绕过 logging(RotatingFileHandler 的锁可能正被卡住的 GUI 线程持有,
  走 logging 会连看门狗一起死锁),用独立句柄直接追加同一日志文件。
"""

from __future__ import annotations

import contextlib
import faulthandler
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

HEARTBEAT_INTERVAL_S = 1.0
CHECK_INTERVAL_S = 2.0
DEFAULT_STALL_THRESHOLD_S = 10.0


class _StallMonitor:
    """冻结判定核心(时钟与转储器可注入,便于无冻结单测)。"""

    def __init__(
        self,
        log_file: Path,
        *,
        threshold_s: float = DEFAULT_STALL_THRESHOLD_S,
        clock: Callable[[], float] = time.monotonic,
        dumper: Callable[..., None] = faulthandler.dump_traceback,
    ) -> None:
        self._log_file = Path(log_file)
        self._threshold_s = threshold_s
        self._clock = clock
        self._dumper = dumper
        self._lock = threading.Lock()
        self._last_beat = clock()
        # 非 None 表示处于已转储的冻结周期中,值为其起始(最后一次心跳)时刻。
        self._stall_started: float | None = None

    def beat(self) -> None:
        """GUI 线程心跳(由 QTimer 周期触发)。"""
        with self._lock:
            now = self._clock()
            if self._stall_started is not None:
                self._append_marker(
                    f"===== GUI 线程恢复响应:本次冻结约 {now - self._stall_started:.1f}s ====="
                )
                self._stall_started = None
            self._last_beat = now

    def check(self) -> None:
        """监视线程周期检查;停滞超阈值时每个冻结周期转储一次。"""
        with self._lock:
            if self._stall_started is not None:
                return
            if self._clock() - self._last_beat <= self._threshold_s:
                return
            self._stall_started = self._last_beat
            threshold = self._threshold_s
        self._dump(threshold)

    def _dump(self, threshold: float) -> None:
        # 看门狗自身故障不允许波及应用;唯一后果是缺一份转储。
        with (
            contextlib.suppress(Exception),
            self._log_file.open("a", encoding="utf-8") as f,
        ):
            f.write(
                f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"===== GUI 主线程疑似冻结:心跳停滞超过 {threshold:.1f}s,"
                "以下为全部线程栈 =====\n"
            )
            f.flush()
            self._dumper(file=f)
            f.write("===== 冻结线程栈转储结束;心跳恢复后将记录本次冻结时长 =====\n")

    def _append_marker(self, text: str) -> None:
        with (
            contextlib.suppress(Exception),
            self._log_file.open("a", encoding="utf-8") as f,
        ):
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")


class FreezeWatchdog:
    """组合 QTimer 心跳与后台监视线程的对外入口。"""

    def __init__(
        self,
        log_file: Path,
        *,
        threshold_s: float = DEFAULT_STALL_THRESHOLD_S,
        heartbeat_interval_s: float = HEARTBEAT_INTERVAL_S,
    ) -> None:
        self.monitor = _StallMonitor(log_file, threshold_s=threshold_s)
        self._heartbeat_interval_s = heartbeat_interval_s

    def start(self, parent: QObject) -> None:
        """启动心跳定时器与监视线程;parent 通常为 QApplication。

        监视线程为 daemon 且随进程退出,不提供停止接口(每次 GUI 进程仅启动一次)。
        """
        timer = QTimer(parent)
        timer.setInterval(int(self._heartbeat_interval_s * 1000))
        timer.timeout.connect(self.monitor.beat)
        timer.start()
        threading.Thread(target=self._watch_loop, name="freeze-watchdog", daemon=True).start()

    def _watch_loop(self) -> None:  # pragma: no cover -- 真实线程循环
        while True:
            time.sleep(CHECK_INTERVAL_S)
            self.monitor.check()
