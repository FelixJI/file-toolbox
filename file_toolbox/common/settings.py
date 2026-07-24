"""轻量 JSON 设置存储(.file_toolbox/settings.json)。

通用 key-value,原子写(先 .tmp 再 os.replace,防写一半崩溃)。
不缓存:每次 get/set 实读写文件(设置访问频率低,简单优先)。
文件缺失/JSON 损坏 → 视为空设置(宽松容错,不抛)。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from file_toolbox.common.paths import get_data_dir


def _settings_path() -> Path:
    """settings.json 路径(.file_toolbox/settings.json)。不创建目录。"""
    return get_data_dir() / "settings.json"


def _load() -> dict[str, Any]:
    """读全部设置。文件缺失/损坏 → 返回 {}。"""
    p = _settings_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, Any]) -> None:
    """原子写全部设置(.tmp → os.replace)。"""
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def get(key: str, default: Any = None) -> Any:
    """读设置 key,缺失/损坏返回 default。"""
    return _load().get(key, default)


def set(key: str, value: Any) -> None:  # noqa: A001 (shadows builtin, 项目惯用)
    """写设置 key(读-改-原子写,保留其他 key)。"""
    data = _load()
    data[key] = value
    _save(data)
