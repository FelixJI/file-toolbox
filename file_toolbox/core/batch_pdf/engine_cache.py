"""引擎验证结果持久缓存(带有效期)。

EngineManager.ensure_verified 的真 Dispatch 兑现要启动 Word/WPS 进程(冷启动每个
数秒),此前只存进程内类变量——跨进程无记忆,每次启动应用后的首次生成都重复付
这笔开销。本模块把兑现结果落盘到 ``.file_toolbox/settings.json``,附
``verified_at`` 时间戳;在 ENGINE_CACHE_TTL 有效期内、且与实时注册表探测一致时
(一致性比对由调用方负责),后续进程直接采信,零 Dispatch。

失败语义:读取/写入的任何异常都吞掉——缓存只加速,不承担正确性;即便采信了
过期环境下的结果,转换时 `_prog_ids_to_try` 仍逐个 ProgID 尝试回退兜底。
"""

from __future__ import annotations

import time
from typing import Any

from file_toolbox.common import settings

from .constants import ENGINE_CACHE_TTL

CACHE_KEY = "pdf_engine_cache"


def _validated(record: Any, *, now: float | None = None) -> dict[str, bool] | None:
    """校验记录结构与有效期,合法则返回 ``{"office","wps"}``,否则 None。

    - 结构:office/wps 必须是 bool,verified_at 必须是数字(JSON 里 bool 是 int
      的子类,需显式排除)。
    - 有效期:``0 <= now - verified_at < ENGINE_CACHE_TTL``。verified_at 落在
      "未来"(时钟回拨)视为不合法,避免回拨后长期采信旧记录。
    """
    if not isinstance(record, dict):
        return None
    office = record.get("office")
    wps = record.get("wps")
    verified_at = record.get("verified_at")
    if not isinstance(office, bool) or not isinstance(wps, bool):
        return None
    if isinstance(verified_at, bool) or not isinstance(verified_at, (int, float)):
        return None
    current = time.time() if now is None else now
    age = current - float(verified_at)
    if not 0 <= age < ENGINE_CACHE_TTL:
        return None
    return {"office": office, "wps": wps}


def load(*, now: float | None = None) -> dict[str, bool] | None:
    """读取有效期内的兑现结果;无记录/过期/损坏/IO 异常 → None。"""
    try:
        return _validated(settings.get(CACHE_KEY), now=now)
    except Exception:
        return None


def save(engines: dict[str, bool], *, now: float | None = None) -> bool:
    """原子写入兑现结果(附时间戳)。返回是否成功;失败只影响缓存,不抛出。"""
    try:
        settings.set(
            CACHE_KEY,
            {
                "office": engines["office"],
                "wps": engines["wps"],
                "verified_at": time.time() if now is None else now,
            },
        )
        return True
    except Exception:
        return False
