"""引擎检测结果持久缓存(带有效期)。

引擎检测的结论有两类可信来源:注册表探测(毫秒级)与真实转换成功后的证据
喂养(``EngineManager.record_engine_evidence``)。此前只存进程内类变量——跨进程
无记忆,每次启动应用后都要重复探测/验证。本模块把结论落盘到
``.file_toolbox/settings.json``,附 ``verified_at`` 时间戳;在 ENGINE_CACHE_TTL
有效期内、且与实时注册表探测一致时(一致性比对由调用方负责),后续进程直接
采信。

失败语义:读取/写入的任何异常都吞掉——缓存只加速,不承担正确性;即便采信了
过期环境下的结果,转换时 `_prog_ids_to_try` 仍逐个 ProgID 尝试回退兜底。
"""

from __future__ import annotations

import time
from typing import Any

from file_toolbox.common import settings

from .constants import ENGINE_CACHE_TTL

CACHE_KEY = "pdf_engine_cache"


def _structure_valid(record: Any) -> dict[str, bool] | None:
    """结构校验(不含时间):office/wps 必须是 bool,verified_at 必须是数字。

    JSON 里 bool 是 int 的子类,需显式排除。合法返回 ``{"office","wps"}``,
    否则 None。
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
    return {"office": office, "wps": wps}


def load_with_reason(*, now: float | None = None) -> tuple[dict[str, bool] | None, str]:
    """读取缓存并返回 ``(记录, 原因)``,原因可诊断 UI 回显与日志。

    原因枚举:``"hit"``(结构+时间均合法)、``"expired"``(结构合法但超 TTL)、
    ``"future"``(verified_at 落在未来,时钟回拨)、``"invalid"``(结构不合法/
    损坏)、``"missing"``(无记录)、``"io"``(读取异常)。记录为 None 时原因
    必为后五者之一。
    """
    try:
        record = settings.get(CACHE_KEY)
    except Exception:
        return None, "io"
    if record is None:
        return None, "missing"
    engines = _structure_valid(record)
    if engines is None:
        return None, "invalid"
    # 时间校验独立于结构校验,以区分 expired/future/invalid 三种失效形态。
    # 链式比较同时排除 NaN/inf 时间戳(json 可解析出它们,旧语义视为不合法)。
    current = time.time() if now is None else now
    age = current - float(record["verified_at"])
    if not 0 <= age < ENGINE_CACHE_TTL:
        return None, "future" if age < 0 else "expired"
    return engines, "hit"


def load(*, now: float | None = None) -> dict[str, bool] | None:
    """读取有效期内的缓存记录;无记录/过期/损坏/IO 异常 → None。"""
    return load_with_reason(now=now)[0]


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
