"""轻量 JSON 设置存储(.file_toolbox/settings.json)。

通用 key-value。get/set 的读-改-写事务按 settings 文件持跨进程事务锁
(进程内线程锁 + 同目录 ``.lock`` 文件),多个 CLI/GUI 进程并发写不同 key
不会互相覆盖。写为同目录唯一临时文件 + ``os.replace`` 原子替换,失败保留
旧文件并清理本次临时文件;不再使用固定名 ``settings.tmp``(并发实例会互相
拆台)。不缓存:每次 get/set 实读写文件。

文件缺失/JSON 损坏 → 视为空设置(宽松容错);权限等 IO 读取失败明确传播,
不会被误当成空设置而把旧文件覆盖掉。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from file_toolbox.common.paths import get_data_dir
from file_toolbox.common.store_lock import file_transaction_lock


def _settings_path() -> Path:
    """settings.json 路径(.file_toolbox/settings.json)。不创建目录。"""
    return get_data_dir() / "settings.json"


def _load() -> dict[str, Any]:
    """读全部设置(调用者持锁)。文件缺失/JSON 损坏 → 返回 {};IO 失败传播。"""
    p = _settings_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, Any]) -> None:
    """原子写全部设置(调用者持锁):同目录唯一临时文件 → os.replace。"""
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(data, ensure_ascii=False))
        os.replace(tmp, p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def get(key: str, default: Any = None) -> Any:
    """读设置 key,缺失/损坏返回 default。"""
    with file_transaction_lock(_settings_path()):
        return _load().get(key, default)


def set(key: str, value: Any) -> None:  # noqa: A001 (shadows builtin, 项目惯用)
    """写设置 key(读-改-原子写,保留其他 key;整个事务持锁)。"""
    with file_transaction_lock(_settings_path()):
        data = _load()
        data[key] = value
        _save(data)
