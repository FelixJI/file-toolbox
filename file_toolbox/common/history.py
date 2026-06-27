"""JSON Lines 历史存储，支持撤销标记。"""

import json
from datetime import datetime
from pathlib import Path


class JsonHistoryStore:
    """每个工具一个 <dir>/<tool>.jsonl，一行一条记录。"""

    def __init__(self, history_dir: Path | None = None):
        # 延迟导入避免在模块加载时强制创建目录
        if history_dir is None:
            from file_toolbox.common.paths import get_history_dir

            history_dir = get_history_dir()
        self._dir = Path(history_dir)

    def _file(self, tool: str) -> Path:
        return self._dir / f"{tool}.jsonl"

    def _read_all(self, tool: str) -> list[dict]:
        f = self._file(tool)
        if not f.exists():
            return []
        records: list[dict] = []
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def _write_all(self, tool: str, records: list[dict]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        f = self._file(tool)
        with open(f, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _last_id(self, tool: str) -> int:
        """仅读取最后一行得到当前最大 id(O(1) append 路径使用)。

        末行损坏时回退到全量扫描的最大 id,保证 id 单调递增不冲突。
        """
        f = self._file(tool)
        if not f.exists():
            return 0
        last_line = None
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                last_line = line
        if last_line:
            try:
                return json.loads(last_line).get("id", 0)
            except json.JSONDecodeError:
                return max((r["id"] for r in self._read_all(tool)), default=0)
        return 0

    def add_record(self, tool: str, data: dict) -> int:
        """追加一条记录(O(1) append,不全量重写),返回自增 id。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        rid = self._last_id(tool) + 1
        rec = {
            "id": rid,
            "timestamp": datetime.now().isoformat(),
            "data": data,
            "undone": False,
        }
        f = self._file(tool)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rid

    def get_records(self, tool: str, limit: int = 100) -> list[dict]:
        """获取最近 limit 条记录（limit<=0 表示全部）。"""
        records = self._read_all(tool)
        return records[-limit:] if limit else records

    def get_record(self, tool: str, record_id: int) -> dict | None:
        """获取单条记录。"""
        for rec in self._read_all(tool):
            if rec["id"] == record_id:
                return rec
        return None

    def mark_undone(self, tool: str, record_id: int) -> None:
        """标记某条记录为已撤销。"""
        records = self._read_all(tool)
        for rec in records:
            if rec["id"] == record_id:
                rec["undone"] = True
                break
        self._write_all(tool, records)

    def clear(self, tool: str) -> int:
        """清空某工具的全部历史，返回清除数量。"""
        records = self._read_all(tool)
        count = len(records)
        self._write_all(tool, [])
        return count
