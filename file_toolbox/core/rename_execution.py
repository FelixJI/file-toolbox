"""重命名结果与可重试撤销;只对已证实成功的文件建立恢复记录。"""

import ctypes
import errno
import os
import sys
from contextlib import nullcontext
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from file_toolbox.common.history import JsonHistoryStore


class PlanState(Enum):
    READY = "✓ 准备就绪"
    NOOP = "无变化"
    CONFLICT = "⚠️ 文件名冲突"
    INVALID = "❌ 错误"


@dataclass(frozen=True)
class PlanEntry:
    target: Path
    state: PlanState
    detail: str = ""

    @property
    def message(self) -> str:
        return self.state.value + (f": {self.detail}" if self.detail else "")


@dataclass
class RenameResult:
    successful: dict[Path, Path] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    history_error: str | None = None

    @property
    def count(self) -> int:
        return len(self.successful)

    @property
    def messages(self) -> list[str]:
        return self.errors + ([self.history_error] if self.history_error else [])


def path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def plan_mapping(mapping: dict[Path, Path]) -> dict[Path, PlanEntry]:
    """只允许原目录内普通文件改名;批内重复目标全部拒绝。"""
    counts: dict[str, int] = {}
    for target in mapping.values():
        key = path_key(target)
        counts[key] = counts.get(key, 0) + 1
    result = {}
    for source, target in mapping.items():
        detail = ""
        if source == target:
            state = PlanState.NOOP
        elif (
            source.parent.resolve() != target.parent.resolve()
            or not target.name
            or any(c in target.name for c in "\\/:\x00")
            or (os.name == "nt" and os.path.isreserved(target.name))
            or source.is_symlink()
            or not source.is_file()
        ):
            state, detail = PlanState.INVALID, "仅支持同目录内普通文件的有效文件名"
        elif counts[path_key(target)] > 1 or os.path.lexists(target):
            state = PlanState.CONFLICT
            detail = "批内重复目标" if counts[path_key(target)] > 1 else "目标已存在"
        else:
            state = PlanState.READY
        result[source] = PlanEntry(target, state, detail)
    return result


def rename_no_replace(source: Path, target: Path) -> None:
    """原子拒绝已有目标;不支持排他重命名的平台/文件系统明确失败。"""
    if sys.platform == "win32":
        source.rename(target)  # Windows MoveFile 不替换已有目标。
        return
    libc = ctypes.CDLL(None, use_errno=True)
    result = -1
    if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(source), -100, os.fsencode(target), 1)
    elif sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(source), os.fsencode(target), 4)
    else:
        raise OSError(errno.ENOTSUP, "当前平台不支持排他重命名")
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))


def file_id(path: Path) -> list[int]:
    """OS 文件编号由执行方记录、撤销方消费;编号缺失或不符时拒绝恢复。"""
    stat = path.stat(follow_symlinks=False)
    if path.is_symlink() or not path.is_file() or not stat.st_ino:
        raise ValueError(f"无法确认普通文件身份: {path}")
    return [stat.st_dev, stat.st_ino]


def execute(mapping: dict[Path, Path], store: JsonHistoryStore | None) -> RenameResult:
    result = RenameResult()
    identities: dict[str, list[int]] = {}
    lock = store.operation_lock("rename") if store else nullcontext()
    with lock:
        for source, entry in plan_mapping(mapping).items():
            if entry.state == PlanState.NOOP:
                continue
            if entry.state != PlanState.READY:
                result.errors.append(f"{source}: {entry.message}")
                continue
            try:
                identity = file_id(source)
                rename_no_replace(source, entry.target)
            except PermissionError as exc:
                result.errors.append(f"权限不足: {source} → {entry.target}: {exc}")
                continue
            except (OSError, ValueError) as exc:
                result.errors.append(f"{source} → {entry.target}: {exc}")
                continue
            result.successful[source] = entry.target
            identities[str(source.absolute())] = identity
        if store and result.successful:
            try:
                store.add_record(
                    "rename",
                    {
                        "schema_version": 2,
                        "rename_map": {
                            str(a.absolute()): str(b.absolute())
                            for a, b in result.successful.items()
                        },
                        "file_ids": identities,
                    },
                )
            except (OSError, ValueError, TimeoutError) as exc:
                result.history_error = (
                    f"文件已操作 {result.count} 个,历史未保存;请勿重复执行: {exc}"
                )
    return result


def undo_record(store: JsonHistoryStore, record_id: int) -> RenameResult:
    result = RenameResult()
    with store.operation_lock("rename"):
        record = store.get_record("rename", record_id)
        if record is None or record.get("undone"):
            result.errors.append("记录不存在或已经撤销,未执行文件操作。")
            return result
        data = record.get("data")
        if not isinstance(data, dict) or data.get("schema_version") != 2:
            result.errors.append("旧格式记录无法证明实际成功与文件归属,仅可查看,请人工核对。")
            return result
        mapping = data.get("rename_map")
        identities = data.get("file_ids")
        remaining = data.get("undo_remaining", list(mapping) if isinstance(mapping, dict) else None)
        if (
            not isinstance(mapping, dict)
            or not mapping
            or not isinstance(identities, dict)
            or not isinstance(remaining, list)
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in mapping.items())
            or any(not isinstance(k, str) or k not in mapping for k in remaining)
            or len(set(remaining)) != len(remaining)
            or len({path_key(Path(v)) for v in mapping.values()}) != len(mapping)
        ):
            result.errors.append("撤销记录不完整或有重复目标,未执行文件操作。")
            return result
        for old, new in mapping.items():
            identity = identities.get(old)
            if (
                not Path(old).is_absolute()
                or not Path(new).is_absolute()
                or Path(old).parent.resolve() != Path(new).parent.resolve()
                or path_key(Path(old)) == path_key(Path(new))
                or not isinstance(identity, list)
                or len(identity) != 2
                or any(type(n) is not int for n in identity)
                or identity[1] == 0
            ):
                result.errors.append("撤销路径或文件编号无效,未执行文件操作。")
                return result
        pending = data.get("undo_pending")
        if pending is not None:
            if not isinstance(pending, str) or pending not in remaining:
                result.errors.append("撤销进度不一致,请人工核对。")
                return result
            old, new = Path(pending), Path(mapping[pending])
            try:
                if not os.path.lexists(new) and file_id(old) == identities[pending]:
                    remaining.remove(pending)
                elif not os.path.lexists(old) and file_id(new) == identities[pending]:
                    pass  # 操作尚未提交,可以继续。
                else:
                    raise ValueError("无法确认上次撤销是否完成")
            except (OSError, ValueError) as exc:
                result.errors.append(f"撤销进度不确定,请人工核对: {exc}")
                return result
        data["undo_remaining"] = remaining
        data["undo_pending"] = None
        try:
            store.update_record_data("rename", record_id, data)
            for old_str in list(remaining):
                old, new = Path(old_str), Path(mapping[old_str])
                try:
                    if file_id(new) != identities[old_str]:
                        raise ValueError("文件已被替换,拒绝撤销")
                    if os.path.lexists(old):
                        raise FileExistsError(f"原路径已存在: {old}")
                except (OSError, ValueError) as exc:
                    result.errors.append(f"{new} → {old}: {exc}")
                    continue
                data["undo_pending"] = old_str
                store.update_record_data("rename", record_id, data)
                try:
                    rename_no_replace(new, old)
                except OSError as exc:
                    result.errors.append(f"{new} → {old}: {exc}")
                else:
                    result.successful[new] = old
                    remaining.remove(old_str)
                data["undo_pending"] = None
                store.update_record_data("rename", record_id, data)
            if not remaining:
                store.mark_undone("rename", record_id)
        except (OSError, ValueError, TimeoutError) as exc:
            result.history_error = (
                f"已反向重命名 {result.count} 个,撤销进度未保存;停止后续操作,请核对或重试: {exc}"
            )
    return result
