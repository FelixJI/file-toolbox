"""replace_tab 异步化回归测试:预览/执行必须在后台线程执行,不阻塞 GUI 主线程。

背景(2026-08-19 用户日志,freeze_watchdog 三次转储):Word COM 的 Dispatch/Open
单次可达 30-45s,旧实现把 preview_replace/execute_replace 同步跑在 GUI 主线程,
主线程心跳停滞触发冻结转储(45.3s/36.1s/31.9s/41.1s)。
本文件锁定:service 调用发生在非主线程、_do_refresh_preview/_execute 立即返回。
"""

import threading
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication, QMessageBox

from file_toolbox.core.batch_replace.types import ReplaceOperationType
from file_toolbox.gui.dialogs.replace_tab import ContentReplaceDialog

SIMPLE = ReplaceOperationType.SIMPLE_REPLACE.value


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _pump_until(app: QApplication, cond, timeout_s: float = 5.0) -> bool:
    """主线程泵送事件直到 cond() 为真;超时返回 False(不抛,由断言给出信息)。"""
    deadline = time.monotonic() + timeout_s
    while not cond():
        if time.monotonic() > deadline:
            return False
        app.processEvents()
        time.sleep(0.01)
    return True


class _RecordingService:
    """假 service:记录调用线程,可选阻塞;不触发真实 COM。"""

    def __init__(self, *, block: threading.Event | None = None):
        self.preview_threads: list[threading.Thread] = []
        self.execute_threads: list[threading.Thread] = []
        self.preview_calls = 0
        self.execute_calls = 0
        self.execute_kwargs: list[dict[str, Any]] = []
        self._block = block

    def validate_operations(self, operations):
        return True, ""

    def preview_replace(self, files, operations, cancel_check=None):
        self.preview_calls += 1
        self.preview_threads.append(threading.current_thread())
        if self._block is not None:
            self._block.wait(10)
        return {f: {"match_count": 1, "status": "✓ 准备就绪"} for f in files}

    def execute_replace(self, files, operations, **kwargs):
        self.execute_calls += 1
        self.execute_threads.append(threading.current_thread())
        self.execute_kwargs.append(kwargs)
        if self._block is not None:
            self._block.wait(10)
        return len(files), 1, []

    def close(self) -> None:
        pass


def _make_dlg(app, svc) -> ContentReplaceDialog:
    dlg = ContentReplaceDialog()
    dlg._svc = svc
    return dlg


def _arm(dlg, tmp_path) -> Path:
    f = tmp_path / "a.txt"
    f.write_text("hello")
    dlg.selected_files = [f]
    dlg.operations = [{"type": SIMPLE, "params": {"find": "hello", "replace": "hi"}}]
    return f


# ---------------------------------------------------------------------------
# 线程回归:service 调用必须离开 GUI 主线程
# ---------------------------------------------------------------------------


def test_preview_replace_runs_off_main_thread(app, tmp_path):
    """preview_replace 在非主线程执行,完成后预览表渲染。"""
    svc = _RecordingService()
    dlg = _make_dlg(app, svc)
    _arm(dlg, tmp_path)

    dlg._do_refresh_preview()
    rendered = _pump_until(
        app, lambda: svc.preview_calls > 0 and dlg.ui.table_preview.rowCount() == 1
    )
    assert rendered, "预览应完成并渲染表格"
    assert svc.preview_threads[0] is not threading.main_thread(), (
        "preview_replace 不得在 GUI 主线程执行(旧同步实现冻结主线程 30-45s)"
    )


def test_execute_replace_runs_off_main_thread(app, tmp_path, monkeypatch):
    """execute_replace 在非主线程执行,完成后弹完成提示。"""
    svc = _RecordingService()
    dlg = _make_dlg(app, svc)
    _arm(dlg, tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )

    dlg._execute()
    done = _pump_until(app, lambda: bool(info_calls))
    assert done, "执行完成后应弹完成提示"
    assert svc.execute_threads[0] is not threading.main_thread(), (
        "execute_replace 不得在 GUI 主线程执行(旧同步实现冻结主线程 30-45s)"
    )


def test_preview_returns_before_slow_service_finishes(app, tmp_path):
    """COM 慢调用(service 阻塞)期间,_do_refresh_preview 必须立即返回。

    用户可见症状即"主界面卡住":旧实现里该调用同步等待 service 完成。
    """
    block = threading.Event()
    svc = _RecordingService(block=block)
    dlg = _make_dlg(app, svc)
    _arm(dlg, tmp_path)

    t0 = time.monotonic()
    dlg._do_refresh_preview()
    elapsed = time.monotonic() - t0
    assert elapsed < 3.0, f"_do_refresh_preview 阻塞了主线程 {elapsed:.1f}s"
    # 主线程在 service 未完成时仍活着:能继续泵送事件
    assert app.processEvents() is None

    block.set()
    assert _pump_until(app, lambda: dlg.ui.table_preview.rowCount() == 1)


def test_execute_returns_before_slow_service_finishes(app, tmp_path, monkeypatch):
    """同上,execute 路径。"""
    block = threading.Event()
    svc = _RecordingService(block=block)
    dlg = _make_dlg(app, svc)
    _arm(dlg, tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    info_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: info_calls.append(1) or QMessageBox.StandardButton.Ok,
    )

    t0 = time.monotonic()
    dlg._execute()
    elapsed = time.monotonic() - t0
    assert elapsed < 3.0, f"_execute 阻塞了主线程 {elapsed:.1f}s"

    block.set()
    # 完成回调在主线程执行(弹完成框)。注:不能等 QThread 的 is_alive——PySide6
    # 的 QThread 线程是 threading 眼中的 dummy thread,is_alive() 不会变 False。
    assert _pump_until(app, lambda: bool(info_calls))


# ---------------------------------------------------------------------------
# 忙碌守卫 / 取消 / 失败恢复 / 安全停止
# ---------------------------------------------------------------------------


def test_preview_skipped_while_busy(app, tmp_path):
    """预览 worker 运行期间,再次刷新预览被跳过(service 不被二次调用)。"""
    block = threading.Event()
    svc = _RecordingService(block=block)
    dlg = _make_dlg(app, svc)
    _arm(dlg, tmp_path)

    dlg._do_refresh_preview()
    assert _pump_until(app, lambda: svc.preview_calls == 1)
    assert not dlg.ui.btn_execute.isEnabled(), "忙碌期间操作按钮应禁用"
    assert not dlg.ui.btn_cancel.isHidden(), "忙碌期间应显示取消按钮"

    dlg._do_refresh_preview()  # 忙碌 → 跳过
    assert svc.preview_calls == 1

    block.set()
    assert _pump_until(app, lambda: dlg.ui.table_preview.rowCount() == 1)
    assert dlg.ui.btn_execute.isEnabled(), "完成后按钮应恢复"
    assert dlg.ui.btn_cancel.isHidden()


def test_execute_skipped_while_preview_busy(app, tmp_path, monkeypatch):
    """预览运行期间点执行:直接返回,不弹确认框、不启动执行 worker。"""
    block = threading.Event()
    svc = _RecordingService(block=block)
    dlg = _make_dlg(app, svc)
    _arm(dlg, tmp_path)
    question_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: question_calls.append(1) or QMessageBox.StandardButton.Yes,
    )

    dlg._do_refresh_preview()
    assert _pump_until(app, lambda: svc.preview_calls == 1)
    dlg._execute()
    assert question_calls == []
    assert svc.execute_calls == 0

    block.set()
    assert _pump_until(app, lambda: dlg.ui.table_preview.rowCount() == 1)


def test_preview_failure_shows_critical_and_restores(app, tmp_path, monkeypatch):
    """service 抛异常 → failed 信号 → critical 提示 + UI 恢复。"""

    class _FailingService(_RecordingService):
        def preview_replace(self, files, operations, cancel_check=None):
            self.preview_calls += 1
            self.preview_threads.append(threading.current_thread())
            raise RuntimeError("COM 服务器无响应")

    svc = _FailingService()
    dlg = _make_dlg(app, svc)
    _arm(dlg, tmp_path)
    critical_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *a, **k: critical_calls.append(1) or QMessageBox.StandardButton.Ok,
    )

    dlg._do_refresh_preview()
    assert _pump_until(app, lambda: critical_calls), "失败应弹 critical 提示"
    assert dlg.worker is None
    assert dlg.ui.btn_execute.isEnabled()
    assert dlg.ui.progress_bar.isHidden()
    assert "已选择" in dlg.ui.label_status.text()


def test_cancel_requests_worker_cancel(app, tmp_path):
    """_on_cancel 对当前 worker 置取消标志(下一文件前生效)。"""
    block = threading.Event()
    svc = _RecordingService(block=block)
    dlg = _make_dlg(app, svc)
    _arm(dlg, tmp_path)

    dlg._do_refresh_preview()
    assert _pump_until(app, lambda: svc.preview_calls == 1)
    worker = dlg.worker
    assert worker is not None
    dlg._on_cancel()
    assert worker._cancel is True
    assert "取消" in dlg.ui.label_status.text()

    block.set()
    assert _pump_until(app, lambda: dlg.ui.table_preview.rowCount() == 1)


def test_stop_worker_cancels_without_terminate(app, tmp_path, monkeypatch):
    """_stop_worker:协作式取消 + 超时仅告警,绝不 terminate(COM 线程强终止危险)。"""
    block = threading.Event()
    svc = _RecordingService(block=block)
    dlg = _make_dlg(app, svc)
    _arm(dlg, tmp_path)

    dlg._do_refresh_preview()
    assert _pump_until(app, lambda: svc.preview_calls == 1)
    worker = dlg.worker
    assert worker is not None
    terminated: list[int] = []
    monkeypatch.setattr(worker, "terminate", lambda: terminated.append(1))

    dlg._stop_worker(150)  # block 未放行 → wait 超时,仅告警
    assert terminated == [], "不得对 COM worker 调用 terminate"
    assert worker._cancel is True, "应先请求协作式取消"
    assert dlg.worker is None

    block.set()
    assert _pump_until(app, lambda: dlg.ui.table_preview.rowCount() == 1), (
        "释放后 worker 应正常完成"
    )
