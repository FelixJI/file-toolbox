"""JSON Lines 历史存储,支持撤销标记。

所有读-改-写事务按目标 ``<dir>/<tool>.jsonl`` 文件持 ``file_transaction_lock``
(进程内线程锁 + 同目录 ``.lock`` 文件跨进程互斥):id 分配、append 与全量替换
都在锁域内完成,公共方法之间不嵌套取锁。重写路径(撤销/清空)先写同目录唯一
临时文件再 ``os.replace`` 原子替换,失败保留旧目标并清理本次临时文件。

损坏行(非 JSON、非对象、缺 id、非正整数 id)查询时跳过并记录含路径/行号的
诊断日志(不打印记录内容);mark_undone 只重写目标行,其余原始行逐行保留。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from file_toolbox.common.store_lock import file_transaction_lock

logger = logging.getLogger(__name__)


class JsonHistoryStore:
    """每个工具一个 <dir>/<tool>.jsonl,一行一条记录。"""

    def __init__(self, history_dir: Path | None = None):
        # 延迟导入避免在模块加载时强制创建目录
        if history_dir is None:
            from file_toolbox.common.paths import get_history_dir

            history_dir = get_history_dir()
        self._dir = Path(history_dir)

    def _file(self, tool: str) -> Path:
        return self._dir / f"{tool}.jsonl"

    # ---- 公共事务边界:以下公共方法各自完整持锁,内部 _* helper 假定调用者已持锁 ----

    def add_record(self, tool: str, data: dict[str, Any]) -> int:
        """追加一条记录,返回自增 id。

        id 取「锁域内全量有效记录的最大 id + 1」,保证跨实例、跨进程唯一;
        末行是破损无换行尾部时先补分隔,新记录独立成行。
        """
        with file_transaction_lock(self._file(tool)):
            self._dir.mkdir(parents=True, exist_ok=True)
            rid = self._last_id(tool) + 1
            rec = {
                "id": rid,
                "timestamp": datetime.now().isoformat(),
                "data": data,
                "undone": False,
            }
            f = self._file(tool)
            if f.exists():
                text = f.read_text(encoding="utf-8")
                if text and not text.endswith(("\n", "\r")):
                    with open(f, "a", encoding="utf-8") as fh:
                        fh.write("\n")
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return rid

    def get_records(self, tool: str, limit: int = 100) -> list[dict[str, Any]]:
        """获取最近 limit 条有效记录(limit<=0 表示全部)。"""
        with file_transaction_lock(self._file(tool)):
            records = self._read_valid_records(tool)
        # limit<=0 一律返回全部:0 与负数语义一致(「全部」),统一用 `limit > 0` 判定。
        if limit > 0:
            return records[-limit:]
        return records

    def get_record(self, tool: str, record_id: int) -> dict[str, Any] | None:
        """获取单条有效记录,不存在返回 None。"""
        with file_transaction_lock(self._file(tool)):
            for rec in self._read_valid_records(tool):
                if rec["id"] == record_id:
                    return rec
        return None

    def mark_undone(self, tool: str, record_id: int) -> None:
        """标记某条记录为已撤销。

        只重写目标有效记录行,其余原始行(含损坏行、额外字段行)逐行保留;
        目标 id 不存在时不改写文件。整个读-改-替换在同一锁域内完成。
        """
        with file_transaction_lock(self._file(tool)):
            self._dir.mkdir(parents=True, exist_ok=True)
            f = self._file(tool)
            if not f.exists():
                return
            new_lines: list[str] = []
            found = False
            for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
                rec = _parse_record_line(line, f, lineno)
                if rec is not None and not found and rec["id"] == record_id:
                    rec["undone"] = True
                    new_lines.append(json.dumps(rec, ensure_ascii=False))
                    found = True
                else:
                    new_lines.append(line)
            if found:
                _replace_file(f, new_lines)

    def clear(self, tool: str) -> int:
        """清空某工具的全部历史(含损坏行),返回清除的有效记录数。"""
        with file_transaction_lock(self._file(tool)):
            count = len(self._read_valid_records(tool))
            self._dir.mkdir(parents=True, exist_ok=True)
            _replace_file(self._file(tool), [])
            return count

    # ---- 锁内 helper(假定调用者已持锁) ----

    def _last_id(self, tool: str) -> int:
        """当前最大有效 id;损坏行/无效 id 行不参与,无有效记录返回 0。"""
        return max((rec["id"] for rec in self._read_valid_records(tool)), default=0)

    def _read_valid_records(self, tool: str) -> list[dict[str, Any]]:
        """读取全部有效记录;无效行跳过并记诊断日志。"""
        f = self._file(tool)
        if not f.exists():
            return []
        records: list[dict[str, Any]] = []
        for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
            rec = _parse_record_line(line, f, lineno)
            if rec is not None:
                records.append(rec)
        return records


def _parse_record_line(line: str, path: Path, lineno: int) -> dict[str, Any] | None:
    """解析一行历史记录;非对象、缺 id、非正整数 id(排除 bool)、损坏 JSON 返回 None。

    日志只含文件路径与行号,不打印记录内容。
    """
    stripped = line.strip()
    if not stripped:
        return None
    try:
        rec = json.loads(stripped)
    except json.JSONDecodeError:
        logger.warning("历史文件损坏 JSON 行已跳过: file=%s line=%d", path, lineno)
        return None
    if not isinstance(rec, dict):
        logger.warning("历史文件非对象行已跳过: file=%s line=%d", path, lineno)
        return None
    rid = rec.get("id")
    # type(...) is int 同时排除 bool(True 是 int 子类)与字符串等非整数 id
    if type(rid) is not int or rid <= 0:
        logger.warning("历史文件无效 id 行已跳过: file=%s line=%d", path, lineno)
        return None
    return rec


def _replace_file(target: Path, lines: list[str]) -> None:
    """写同目录唯一临时文件后原子替换目标;失败保留旧目标并清理本次临时文件。

    成功返回意味着替换已完成;写/替换错误向上传播,不吞。
    """
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            for line in lines:
                fh.write(line + "\n")
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
