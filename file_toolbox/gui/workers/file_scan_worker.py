"""文件扫描及元数据分批交付；没有 QWidget/模型跨线程写入。"""

import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from file_toolbox.common.file_utils import format_datetime, format_file_size


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    size: str = ""
    modified: str = ""
    error: str = ""


class FileScanWorker(QThread):
    batch = Signal(int, object)
    failed = Signal(int, str)

    def __init__(
        self,
        generation: int,
        paths: list[Path],
        folder: Path | None,
        recursive: bool,
        supported: Callable[[Path], bool],
        existing: list[Path],
        resolved: bool,
        check_files: bool,
        metadata: bool,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.generation = generation
        self.paths = list(paths)
        self.folder = folder
        self.recursive = recursive
        self.supported = supported
        self.existing = list(existing)
        self.resolved = resolved
        self.check_files = check_files
        self.metadata = metadata
        self.deduplicate = True
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True
        self.requestInterruption()

    def run(self) -> None:
        pending: list[ScannedFile] = []
        try:
            seen = set()
            for path in self.existing if self.deduplicate else ():
                if self.isInterruptionRequested():
                    return
                seen.add(path.resolve() if self.resolved else path)
            candidates = (
                (self.folder.rglob("*") if self.recursive else self.folder.iterdir())
                if self.folder
                else iter(self.paths)
            )
            for path in candidates:
                if self.isInterruptionRequested():
                    break
                if not self.supported(path):
                    continue
                try:
                    key = path.resolve() if self.resolved else path
                    if self.deduplicate and key in seen:
                        continue
                    info = path.stat() if self.check_files or self.metadata or self.folder else None
                    if (
                        (self.check_files or self.folder)
                        and info
                        and not stat.S_ISREG(info.st_mode)
                    ):
                        continue
                    item = ScannedFile(
                        path,
                        format_file_size(info.st_size) if info else "",
                        format_datetime(datetime.fromtimestamp(info.st_mtime)) if info else "",
                    )
                except OSError as exc:
                    self.failed.emit(self.generation, f"{path}: {exc}")
                    if self.check_files or self.folder:
                        continue
                    item = ScannedFile(path, error=str(exc))
                if self.isInterruptionRequested():
                    break
                seen.add(key)
                pending.append(item)
                if len(pending) == 64:
                    self.batch.emit(self.generation, pending)
                    pending = []
            if pending and not self.isInterruptionRequested():
                self.batch.emit(self.generation, pending)
        except Exception as exc:
            self.failed.emit(self.generation, str(exc))
