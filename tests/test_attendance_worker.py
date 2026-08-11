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


def test_worker_emits_failure(tmp_path):
    service = MagicMock()
    service.preview.side_effect = RuntimeError("Excel 不可用")
    received = []
    worker = AttendanceWorker(service, _request(tmp_path), "preview")
    worker.failed.connect(received.append)

    worker.run()

    assert received == ["Excel 不可用"]
