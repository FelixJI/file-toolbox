"""考勤 worker 的模式分派、取消和失败信号。"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6.QtCore")

from file_toolbox.core.attendance import (  # noqa: E402
    AttendancePlan,
    AttendancePreview,
    AttendanceRequest,
    AttendanceResult,
    CellRef,
    SourceLayout,
    TargetLayout,
)
from file_toolbox.gui.workers.attendance_worker import AttendanceWorker  # noqa: E402


def _request(tmp_path):
    return AttendanceRequest(
        AttendancePlan(
            "测试",
            tmp_path / "template.xlsx",
            SourceLayout("Sheet1", CellRef.parse("A2"), CellRef.parse("C2"), CellRef.parse("G2")),
            TargetLayout(
                "出勤明细",
                CellRef.parse("C7"),
                CellRef.parse("D7"),
                "考勤汇总表",
                CellRef.parse("C8"),
            ),
        ),
        tmp_path / "source.xlsx",
        tmp_path / "out.xlsx",
        2026,
        7,
    )


def test_worker_dispatches_preview_and_forwards_cancel(tmp_path):
    service = MagicMock()
    preview = AttendancePreview(1, 31, 0, 1, {"√": 31}, ())
    service.preview.return_value = preview
    received = []
    worker = AttendanceWorker(service, _request(tmp_path), "preview")
    worker.finished_ok.connect(received.append)

    worker.cancel()
    worker.run()

    assert received == [preview]
    cancel_check = service.preview.call_args.args[1]
    assert cancel_check() is True


def test_worker_dispatches_generate(tmp_path):
    service = MagicMock()
    result = AttendanceResult(tmp_path / "out.xlsx", 1, 31, {"√": 31})
    service.generate.return_value = result
    received = []
    worker = AttendanceWorker(service, _request(tmp_path), "generate")
    worker.finished_ok.connect(received.append)

    worker.run()

    assert received == [result]
    service.generate.assert_called_once()


def test_worker_logs_traceback_and_emits_traceable_failure(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from file_toolbox.common.logging_config import configure_logging, get_log_file

    configure_logging(mode="test")
    service = MagicMock()
    raw_com_message = "(-2147352567, '发生意外。', (0, None, None, None, 0, -2147352565), None)"
    service.preview.side_effect = RuntimeError(raw_com_message)
    received = []
    worker = AttendanceWorker(service, _request(tmp_path), "preview")
    worker.failed.connect(received.append)

    worker.run()

    assert len(received) == 1
    assert "考勤预览失败" in received[0]
    assert "错误编号" in received[0]
    assert str(get_log_file()) in received[0]
    assert raw_com_message not in received[0]
    log_content = get_log_file().read_text(encoding="utf-8")
    assert raw_com_message in log_content
    assert "Traceback" in log_content
    assert str(tmp_path / "source.xlsx") in log_content
