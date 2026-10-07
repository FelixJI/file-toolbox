"""重命名冻结预览/实际写入；核心继续负责原子重验和成功历史。"""

import stat
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from file_toolbox.common.file_utils import format_datetime, format_file_size
from file_toolbox.core.batch_rename import FileRenameService
from file_toolbox.gui.workers.file_scan_worker import ScannedFile


class RenamePreviewWorker(QThread):
    preview_ok = Signal(object, object)
    failed = Signal(str)

    def __init__(
        self,
        svc: FileRenameService,
        files: list[Path],
        operations: list[dict[str, Any]],
        metadata: dict[Path, ScannedFile],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.svc = svc
        self.files = list(files)
        self.operations = deepcopy(operations)
        self.metadata = dict(metadata)

    def cancel(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        try:
            valid, message = self.svc.validate_operations(self.operations)
            if not valid:
                self.failed.emit(message)
                return
            plan = self.svc.plan_operations(
                self.files, self.operations, self.isInterruptionRequested
            )
            rows: list[tuple[list[str], None]] = []
            for path, entry in plan.items():
                if self.isInterruptionRequested():
                    return
                cached = self.metadata.get(path)
                if cached is None:
                    try:
                        info = path.stat()
                        cached = (
                            ScannedFile(
                                path,
                                format_file_size(info.st_size),
                                format_datetime(datetime.fromtimestamp(info.st_mtime)),
                            )
                            if stat.S_ISREG(info.st_mode)
                            else ScannedFile(path, "未知", "未知")
                        )
                    except OSError as exc:
                        cached = ScannedFile(path, "未知", "未知", str(exc))
                    self.metadata[path] = cached
                rows.append(
                    (
                        [path.name, entry.target.name, cached.size, cached.modified, entry.message],
                        None,
                    )
                )
            if not self.isInterruptionRequested():
                self.preview_ok.emit(plan, rows)
        except Exception as exc:
            self.failed.emit(str(exc))


class RenameExecuteWorker(QThread):
    execute_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, svc: FileRenameService, mapping: dict[Path, Path], parent: QWidget) -> None:
        super().__init__(parent)
        self.svc = svc
        self.mapping = dict(mapping)

    def cancel(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        try:
            result = self.svc.execute_rename_result(self.mapping, self.isInterruptionRequested)
            self.execute_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
